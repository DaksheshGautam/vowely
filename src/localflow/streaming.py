"""Bounded phrase queues: coalesced previews, ordered finals and concurrent cleanup.

Every committed audio phrase is kept. Only replaceable preview requests may be
coalesced. Forced cuts get a whole-recording check before a final result is used.
"""
from array import array
from collections import deque
from dataclasses import dataclass, replace
import math
import re
import threading
import time

from .engines import Cancelled, EngineError, cleanup_insertion_ready, pipeline
from .formatting import (comma_list_items, has_layout_cues, join_blocks,
                         preserved_cleanup, PreservedCleanupNotice,final_cleanup_blocks)


def rms(pcm):
    samples = array('h',pcm)
    return math.sqrt(sum(x*x for x in samples)/max(1,len(samples)))


@dataclass(frozen=True)
class AudioTask:
    index: int
    pcm: bytes
    final: bool


class SentenceBuffer:
    """Only stable ASR sentences enter cleanup; unfinished text stays visible.

    Punctuation is an estimate from ASR, not a grammatical completion guarantee.
    Common abbreviation dots and obvious trailing conjunctions stay buffered.
    """
    END = re.compile(r'''[.!?।。！？]+["”’')\]]*(?=\s|$)''')
    ABBREVIATIONS = {'mr','mrs','ms','dr','prof','sr','jr','st','vs','etc','e.g','i.e','a.m','p.m'}
    INCOMPLETE = {'and','or','but','because','if','although','while','to','of','with',
                  'for','the','a','an','my','your','his','her','our','their','is','are'}

    def __init__(self): self.pending = ''

    def feed(self,text):
        self.pending = ' '.join(x for x in (self.pending,text.strip()) if x)
        sentences,start = [],0
        for match in self.END.finditer(self.pending):
            candidate = self.pending[start:match.end()].strip()
            if match.group().startswith('.'):
                before = self.pending[:match.start()]
                word = before.split()[-1].strip('"“(\'').lower() if before.split() else ''
                if (word in self.ABBREVIATIONS or word in self.INCOMPLETE or
                    re.search(r'(?:\b[A-Za-z]\.)+[A-Za-z]$',before) or
                    re.fullmatch(r'[A-Z]',before.split()[-1] if before.split() else '') or
                    match.group().startswith('..')):
                    continue
            if candidate:
                sentences.append(candidate)
                start = match.end()
        self.pending = self.pending[start:].strip()
        return sentences

    def finish(self):
        tail,self.pending = self.pending,''
        return [tail] if tail else []

    def clear(self): self.pending = ''


class PhraseBuffer:
    RATE_BYTES = 32000
    FRAME_BYTES = 640  # 20 ms PCM16/16 kHz

    def __init__(self,pause_seconds=1.2,preview_seconds=2.5,max_phrase_seconds=120,threshold=48):
        self.pause_frames = round(pause_seconds/.02) if pause_seconds is not None else None
        self.preview_bytes = round(preview_seconds*self.RATE_BYTES)
        self.max_bytes = round(max_phrase_seconds*self.RATE_BYTES)
        self.threshold = threshold
        self.frames = bytearray()
        self.active = bytearray()
        self.preroll = deque(maxlen=10)
        self.last_voice = self.silence = self.last_preview = self.index = 0
        self.needs_recheck = False

    def _commit(self,forced=False):
        end = len(self.active) if forced else min(len(self.active),self.last_voice+6400)
        task = AudioTask(self.index,bytes(self.active[:end]),True)
        self.index += 1
        # An overlapping tail protects words at a forced cut. These provisional
        # chunks are replaced by a whole-recording transcription after Stop.
        carry = bytes(self.active[-12800:]) if forced else b''
        self.active = bytearray(carry)
        self.last_voice = len(carry)
        self.silence = self.last_preview = 0
        self.needs_recheck |= forced
        return task

    def feed(self,pcm):
        if len(pcm)%2: raise EngineError('Invalid live PCM16 audio frame.')
        self.frames.extend(pcm)
        finals,preview = [],None
        while len(self.frames)>=self.FRAME_BYTES:
            frame = bytes(self.frames[:self.FRAME_BYTES])
            del self.frames[:self.FRAME_BYTES]
            voice = rms(frame)>=self.threshold
            if not self.active:
                if voice:
                    self.active.extend(b''.join(self.preroll))
                    self.active.extend(frame)
                    self.last_voice = len(self.active)
                    self.preroll.clear()
                else:
                    self.preroll.append(frame)
                continue
            self.active.extend(frame)
            if voice:
                self.last_voice = len(self.active)
                self.silence = 0
            else:
                self.silence += 1
            if self.pause_frames is not None and self.silence>=self.pause_frames:
                finals.append(self._commit())
                self.preroll.append(frame)
                preview = None
            elif len(self.active)>=self.max_bytes:
                finals.append(self._commit(forced=True))
                preview = None
            elif len(self.active)-self.last_preview>=self.preview_bytes:
                preview = AudioTask(self.index,bytes(self.active),False)
                self.last_preview = len(self.active)
        return finals,preview

    def finish(self):
        if self.active:
            self.active.extend(self.frames)
            self.frames.clear()
            return [self._commit()]
        self.frames.clear()
        return []

    def clear(self):
        self.active.clear();self.frames.clear();self.preroll.clear()


class StreamingSession:
    def __init__(self,runtime,config,root,cancel=None,on_update=None,fallback=pipeline):
        self.runtime,self.c,self.root = runtime,config,root
        self.cancel = cancel or threading.Event()
        self.on_update = on_update or (lambda payload:None)
        self.fallback = fallback
        # Silence never commits audio here. Stable Whisper sentence endings
        # decide cleanup; Stop transcribes the complete recording for accuracy.
        self.segmenter = PhraseBuffer(pause_seconds=None,max_phrase_seconds=config.max_seconds)
        self._condition = threading.Condition(threading.RLock())
        self._finals = deque()
        self._preview = None
        self._cleanup = deque()
        self._raw,self._clean = {},{}
        self._clean_ready = {}
        self.sentences = SentenceBuffer()
        self._sentence_raw = {}
        self._previous_complete = []
        self._scheduled = set()
        self._recheck_done = False
        self._partial = ''
        self._input_done = self._asr_done = False
        self._asr_busy = self._clean_busy = False
        self._fatal = None
        self._full_pcm = b''
        self._revision = 0
        self._update_sequence = 0
        self._warnings = {}
        self._asr_seconds = 0
        self._started = time.monotonic()
        self._stopped = None

    def _enqueue(self,finals,preview=None):
        for task in finals:
            if len(self._finals)>=256:
                raise EngineError('Live phrase queue is full. Stop to process the complete recording.')
            self._finals.append(task)
            if self._preview and self._preview.index<=task.index: self._preview = None
        if preview: self._preview = preview
        self._condition.notify_all()

    def feed(self,pcm):
        with self._condition:
            if self.cancel.is_set() or self._input_done or self._fatal: return
            finals,preview = self.segmenter.feed(pcm)
            try:
                # Forced audio cuts are provisional and cannot enter cleanup.
                self._enqueue([],preview)
            except EngineError as error:
                self._fatal = str(error)
                self._condition.notify_all()

    def finish_input(self,full_pcm):
        with self._condition:
            if self._input_done: return
            self._full_pcm = bytes(full_pcm)
            if not self._fatal:
                self.segmenter.finish()
                self._finals.clear()
                self._enqueue([AudioTask(0,bytes(full_pcm),True)] if full_pcm else [])
            self._input_done = True
            self._preview = None
            self._stopped = time.monotonic()
            self._condition.notify_all()
        self._emit()

    def abort(self,close_runtime=True):
        self.cancel.set()
        with self._condition:
            self._condition.notify_all()
        if close_runtime: self.runtime.close()  # GUI schedules this on its lifecycle worker.

    def _snapshot(self):
        indices = sorted(self._raw)
        raw = ' '.join(self._raw[i] for i in indices if self._raw[i]).strip()
        text = join_blocks(self._clean.get(i,value) for i,value in sorted(self._sentence_raw.items()))
        if self.segmenter.needs_recheck and not self._recheck_done: text = raw
        return {'raw':' '.join(x for x in (raw,self._partial) if x),
                'text':' '.join(x for x in (text,self._partial) if x),
                'asr_busy':self._asr_busy,'cleanup_busy':self._clean_busy,
                'pending_phrases':len(self._finals)+len(self._cleanup),
                'cleaned_phrases':len(self._clean),'warning':self._fatal or '',
                'waiting_sentence':bool(self.sentences.pending),
                'completed_sentences':len(self._sentence_raw),
                'rechecking':self.segmenter.needs_recheck and self._input_done}

    def _accept_snapshot(self,raw,final=False):
        """Stable Whisper punctuation gates cleanup; final ASR can revise it."""
        splitter = SentenceBuffer()
        complete = splitter.feed(raw)
        tail = splitter.pending
        units = complete+([tail] if tail else [])
        stable = 0
        for before,after in zip(self._previous_complete,complete):
            if before!=after: break
            stable += 1
        if final: stable = len(units)
        # A list can span many sentences. Give Qwen its stable prefix as one
        # block so item order, numbering and paragraph commands retain context.
        # Growing prefixes replace stale work; unfinished text is still held.
        if self.c.cleanup_enabled and self.c.mode!='Verbatim' and final:
            units=final_cleanup_blocks(raw);stable=len(units)
        elif self.c.cleanup_enabled and self.c.mode!='Verbatim' and (has_layout_cues(raw) or comma_list_items(raw)):
            ready = raw if final else ' '.join(complete[:stable])
            waiting = '' if final else ' '.join(complete[stable:]+([tail] if tail else []))
            units = [part for part in (ready,waiting) if part]
            stable = 1 if ready else 0
        changed = any(i>=len(units) or self._sentence_raw.get(i)!=units[i] for i in self._scheduled)
        if changed:
            self._revision += 1
            self._cleanup.clear()
            self._clean = {i:text for i,text in self._clean.items()
                           if i<len(units) and self._sentence_raw.get(i)==units[i]}
            self._clean_ready = {i:ready for i,ready in self._clean_ready.items() if i in self._clean}
            self._warnings = {i:note for i,note in self._warnings.items() if i in self._clean}
            self._scheduled = set(self._clean)
        self._sentence_raw = dict(enumerate(units))
        self._previous_complete = complete
        self.sentences.pending = tail
        self._raw = {0:raw}
        self._partial = ''
        for index in range(stable):
            if index not in self._scheduled:
                self._scheduled.add(index)
                self._cleanup.append((self._revision,index,units[index]))
        self._condition.notify_all()

    def _emit(self):
        if self.cancel.is_set(): return
        with self._condition:
            payload = self._snapshot()
            self._update_sequence += 1
            payload['sequence'] = self._update_sequence
        # A closed UI must not terminate an inference worker or lose a phrase.
        try: self.on_update(payload)
        except Exception: pass

    def _recognize(self,pcm,interim=False):
        if rms(pcm)<16: return ''
        started = time.monotonic()
        text = self.runtime.transcribe(pcm,self.c,self.cancel,interim=interim)
        self._asr_seconds += time.monotonic()-started
        return text

    def _asr_loop(self):
        try:
            while not self.cancel.is_set():
                with self._condition:
                    while not (self._finals or self._preview or self._input_done or self._fatal or self.cancel.is_set()):
                        self._condition.wait(.1)
                    if self._fatal or self.cancel.is_set(): break
                    if self._finals:
                        task = self._finals.popleft()
                    elif self._preview and not self._input_done:
                        task,self._preview = self._preview,None
                    else: break
                    self._asr_busy = True
                self._emit()
                raw = self._recognize(task.pcm,interim=not task.final)
                with self._condition:
                    self._asr_busy = False
                    if task.final:
                        self._recheck_done = True
                        self._accept_snapshot(raw,final=True)
                    elif not self._input_done and not self._finals and not self.segmenter.needs_recheck:
                        self._accept_snapshot(raw)
                self._emit()
        except Cancelled:
            if not self.cancel.is_set():
                with self._condition: self._fatal = 'Live model worker stopped.'
        except Exception:
            with self._condition: self._fatal = 'Live recognition failed; the complete recording will be processed after Stop.'
            self.runtime.close()
        finally:
            with self._condition:
                self._asr_done = True
                self._asr_busy = False
                self._condition.notify_all()
            self._emit()

    def _cleanup_loop(self):
        while not self.cancel.is_set():
            with self._condition:
                while not (self._cleanup or self._asr_done or self._fatal or self.cancel.is_set()):
                    self._condition.wait(.1)
                if self.cancel.is_set() or self._fatal: break
                if not self._cleanup and self._asr_done: break
                revision,index,raw = self._cleanup.popleft()
                self._clean_busy = True
            self._emit()
            try:
                text,warning = self.runtime.clean(raw,self.c,self.cancel)
            except Cancelled:
                break
            except Exception:
                text,warning = preserved_cleanup(raw,'Cleanup unavailable; original phrase preserved.')
            with self._condition:
                self._clean_busy = False
                if revision==self._revision:
                    self._clean[index] = text
                    self._clean_ready[index] = cleanup_insertion_ready(raw,text,warning,self.c)
                    if warning: self._warnings[index] = warning
                    else: self._warnings.pop(index,None)
            self._emit()
        with self._condition: self._clean_busy = False

    def run(self):
        asr = threading.Thread(target=self._asr_loop,name='LocalFlow-ASR',daemon=True)
        cleanup = threading.Thread(target=self._cleanup_loop,name='LocalFlow-cleanup',daemon=True)
        asr.start();cleanup.start()
        try:
            with self._condition:
                while not self._input_done and not self.cancel.is_set(): self._condition.wait(.1)
            if self.cancel.is_set():
                self.runtime.close()
            asr.join();cleanup.join()
            if self.cancel.is_set(): raise Cancelled('Cancelled')
            if self._fatal:
                self.runtime.close()
                cpu = replace(self.c,gpu=False,whisper_exe='vendor/whisper/Release/whisper-cli.exe')
                result = self.fallback(self._full_pcm,cpu,self.root,self.cancel)
                result.update(review=True,insertion_ready=result.get('insertion_ready',False),cpu_fallback=True,gpu_used=False,cleanup_gpu_used=False)
                result['warning'] = 'Live mode failed; used local whole-recording CPU fallback. '+result['warning']
            else:
                payload = self._snapshot()
                result = {'raw':payload['raw'],'text':payload['text'],
                          'warning':' '.join(sorted(set(self._warnings.values()))),
                          'cleanup_fallback':any(isinstance(note,PreservedCleanupNotice) for note in self._warnings.values()),
                          'review':bool(self._warnings) or (self.c.cleanup_enabled and self.c.mode!='Verbatim'),
                          'insertion_ready':bool(payload['text'] and self._recheck_done and self._sentence_raw)
                              and all(self._clean_ready.get(i,False) for i in self._sentence_raw),
                          'asr_ms':round(self._asr_seconds*1000),
                          'cpu_fallback':self.runtime.asr_cpu_fallback,
                          'cleanup_cpu_fallback':self.runtime.qwen_cpu_fallback,
                          'gpu_used':bool(self.runtime.asr and self.runtime.asr.gpu_confirmed),
                          'cleanup_gpu_used':bool(self.runtime.qwen and self.runtime.qwen.gpu_confirmed)}
                if not result['raw']:
                    result.update(warning='No speech detected. Nothing inserted.',review=True,insertion_ready=False)
            result.update(streaming=True,total_ms=round((time.monotonic()-self._started)*1000),
                          tail_ms=round((time.monotonic()-(self._stopped or self._started))*1000))
            return result
        finally:
            with self._condition:
                self._full_pcm = b''
                self._finals.clear();self._cleanup.clear()
                self._raw.clear();self._clean.clear()
                self._clean_ready.clear()
                self._warnings.clear()
                self._sentence_raw.clear();self.sentences.clear()
                self._previous_complete.clear();self._scheduled.clear()
                self._preview = None;self._partial = ''
                self.segmenter.clear()
