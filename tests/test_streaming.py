from array import array
from pathlib import Path
from types import SimpleNamespace
import threading
import unittest

from localflow.config import Config
from localflow.engines import Cancelled
from localflow.streaming import PhraseBuffer, SentenceBuffer, StreamingSession


VOICE = array('h',[1000]*16000).tobytes()
SILENCE = bytes(48000)


class Runtime:
    def __init__(self):
        self.asr = self.qwen = SimpleNamespace(gpu_confirmed=True)
        self.asr_cpu_fallback = self.qwen_cpu_fallback = False
        self.calls = []
        self.cleaned = []
        self.closed = threading.Event()

    def transcribe(self,pcm,c,cancel,interim=False):
        self.calls.append((pcm,interim))
        return 'preview' if interim else f'phrase {sum(not x[1] for x in self.calls)}'

    def clean(self,raw,c,cancel):
        self.cleaned.append(raw)
        return raw.upper(),''
    def close(self): self.closed.set()


class StreamingTests(unittest.TestCase):
    def test_live_preview_window_uses_configured_five_minute_recording_limit(self):
        session=StreamingSession(Runtime(),Config(max_seconds=300),Path('.'))
        self.assertEqual(session.segmenter.max_bytes,300*32000)

    def execute(self,session,pcm):
        output = {}
        def target():
            try: output['result'] = session.run()
            except Exception as error: output['error'] = error
        thread = threading.Thread(target=target,daemon=True)
        thread.start()
        session.feed(pcm)
        session.finish_input(pcm)
        thread.join(5)
        self.assertFalse(thread.is_alive(),'streaming worker did not finish')
        if 'error' in output: raise output['error']
        return output['result']

    def accept(self,session,text,final=False):
        with session._condition: session._accept_snapshot(text,final)

    def test_no_silence_timer_and_full_audio_on_stop(self):
        runtime = Runtime()
        session = StreamingSession(runtime,Config(cleanup_enabled=True),Path('.'))
        self.assertIsNone(session.segmenter.pause_frames)
        pcm = VOICE+SILENCE+VOICE
        result = self.execute(session,pcm)
        self.assertEqual(runtime.calls[-1],(pcm,False))
        self.assertEqual(result['raw'],'phrase 1')
        self.assertEqual(result['text'],'PHRASE 1')
        self.assertTrue(result['review'])
        self.assertEqual(session._full_pcm,b'')
        self.assertFalse(session._raw)
        self.assertFalse(session.segmenter.active)

    def test_sentence_without_silence_waits_for_agreeing_whisper_previews(self):
        session = StreamingSession(Runtime(),Config(),Path('.'))
        self.accept(session,'The app works. Next thought')
        self.assertFalse(session._cleanup)
        self.accept(session,'The app works. Next thought continues')
        self.assertEqual(list(session._cleanup),[(0,0,'The app works.')])
        self.assertEqual(session.sentences.pending,'Next thought continues')

    def test_partial_text_and_period_revision_never_trigger_cleanup(self):
        session = StreamingSession(Runtime(),Config(),Path('.'))
        self.accept(session,'My name is.')
        self.accept(session,'My name is Example')
        self.assertFalse(session._cleanup)
        self.accept(session,'My name is Example Person.')
        self.assertFalse(session._cleanup)
        self.accept(session,'My name is Example Person. I build apps')
        self.assertEqual(len(session._cleanup),1)

    def test_repeated_previews_do_not_duplicate_cleanup(self):
        session = StreamingSession(Runtime(),Config(),Path('.'))
        for _ in range(5): self.accept(session,'A complete sentence.')
        self.assertEqual(len(session._cleanup),1)
        self.accept(session,'A complete sentence.',final=True)
        self.assertEqual(len(session._cleanup),1)

    def test_final_asr_replaces_wrong_preview_and_discards_old_cleanup(self):
        session = StreamingSession(Runtime(),Config(),Path('.'))
        self.accept(session,'Wrong name.')
        self.accept(session,'Wrong name.')
        self.assertEqual(session._revision,0)
        self.accept(session,'Example Person.',final=True)
        self.assertEqual(session._revision,1)
        self.assertEqual(list(session._cleanup),[(1,0,'Example Person.')])
        self.assertEqual(session._snapshot()['raw'],'Example Person.')

    def test_growth_of_unfinished_tail_preserves_completed_cleanup(self):
        session = StreamingSession(Runtime(),Config(),Path('.'))
        self.accept(session,'First sentence. I am')
        self.accept(session,'First sentence. I am building')
        session._clean[0] = 'FIRST SENTENCE.'
        self.accept(session,'First sentence. I am building an app')
        self.assertEqual(session._revision,0)
        self.assertEqual(session._snapshot()['text'],'FIRST SENTENCE. I am building an app')

    def test_stop_flushes_unfinished_sentence_once(self):
        session = StreamingSession(Runtime(),Config(),Path('.'))
        self.accept(session,'First sentence. unfinished tail')
        self.accept(session,'First sentence. unfinished tail')
        self.accept(session,'First sentence. unfinished tail',final=True)
        self.assertEqual([item[2] for item in session._cleanup],['First sentence.','unfinished tail'])

    def test_forced_cut_never_cleans_partial_audio_and_stop_uses_whole_clip(self):
        runtime = Runtime()
        session = StreamingSession(runtime,Config(),Path('.'))
        session.segmenter = PhraseBuffer(pause_seconds=None,max_phrase_seconds=1)
        pcm = VOICE*3
        self.execute(session,pcm)
        self.assertEqual(runtime.calls,[(pcm,False)])
        self.assertEqual(runtime.cleaned,['phrase 1'])

    def test_quiet_audio_checked_and_digital_silence_skips_models(self):
        runtime = Runtime()
        quiet = array('h',[20]*16000).tobytes()
        self.execute(StreamingSession(runtime,Config(),Path('.')),quiet)
        self.assertEqual(runtime.calls,[(quiet,False)])
        runtime = Runtime()
        result = self.execute(StreamingSession(runtime,Config(),Path('.')),SILENCE)
        self.assertFalse(runtime.calls)
        self.assertEqual(result['text'],'')
        self.assertTrue(result['review'])

    def test_asr_failure_falls_back_with_whole_audio(self):
        class Broken(Runtime):
            def transcribe(self,*args,**kwargs): raise RuntimeError('private engine log')
        seen = []
        def fallback(pcm,c,root,cancel):
            seen.append((pcm,c.gpu))
            return dict(raw='full',text='full',warning='',total_ms=0)
        pcm = VOICE+SILENCE+VOICE
        result = self.execute(StreamingSession(Broken(),Config(gpu=True),Path('.'),fallback=fallback),pcm)
        self.assertEqual(seen,[(pcm,False)])
        self.assertTrue(result['cpu_fallback'])
        self.assertTrue(result['review'])
        self.assertNotIn('private',result['warning'])
        self.assertFalse(result['insertion_ready'])

    def test_revised_source_cannot_reuse_old_insertion_permission(self):
        session = StreamingSession(Runtime(),Config(cleanup_enabled=True),Path('.'))
        self.accept(session,'Meet at 4.')
        self.accept(session,'Meet at 4.')
        session._clean[0] = 'Meet at 4.'
        session._clean_ready[0] = True
        self.accept(session,'Meet at 5.',final=True)
        self.assertFalse(session._clean_ready)
        self.assertFalse(session._clean)

    def test_any_rejected_final_unit_blocks_automatic_typing(self):
        raw='First '+('word '*497)+'. Second sentence.'
        class Mixed(Runtime):
            def transcribe(self,*args,**kwargs): return raw
            def clean(self,raw,c,cancel):
                return raw,('Cleanup requires review.' if raw.startswith('First') else 'Cleanup unavailable; original preserved.')
        result = self.execute(StreamingSession(Mixed(),Config(cleanup_enabled=True),Path('.')),VOICE)
        self.assertFalse(result['insertion_ready'])
        self.assertTrue(result['review'])

    def test_safe_source_fallback_does_not_block_other_valid_qwen_units(self):
        from localflow.formatting import preserved_cleanup
        raw='First '+('word '*497)+'. Meet at 4.'
        class Mixed(Runtime):
            def transcribe(self,*args,**kwargs): return raw
            def clean(self,raw,c,cancel):
                if raw.startswith('First'): return raw,'Cleanup requires review.'
                return preserved_cleanup(raw,'Cleanup unavailable or rejected; original wording preserved.')
        result = self.execute(StreamingSession(Mixed(),Config(cleanup_enabled=True),Path('.')),VOICE)
        self.assertTrue(result['insertion_ready'])
        self.assertTrue(result['cleanup_fallback'])
        self.assertEqual(result['text'],raw)

    def test_source_revision_discards_obsolete_cleanup_warnings(self):
        session = StreamingSession(Runtime(),Config(cleanup_enabled=True),Path('.'))
        self.accept(session,'Wrong word.')
        self.accept(session,'Wrong word.')
        session._clean[0] = 'Wrong word.'
        session._warnings[0] = 'Old warning'
        self.accept(session,'Correct word.',final=True)
        self.assertFalse(session._warnings)

    def test_cancel_clears_buffer_and_never_returns_partial(self):
        runtime = Runtime()
        session = StreamingSession(runtime,Config(),Path('.'))
        session.feed(VOICE)
        self.accept(session,'Unfinished private text')
        session.abort()
        with self.assertRaises(Cancelled): session.run()
        self.assertTrue(runtime.closed.is_set())
        self.assertFalse(session.segmenter.active)
        self.assertFalse(session._previous_complete)
        self.assertFalse(session._scheduled)

    def test_previews_coalesce_across_long_silence_without_committing_audio(self):
        session = StreamingSession(Runtime(),Config(),Path('.'))
        session.feed(VOICE*3)
        first = session._preview
        session.feed(VOICE*3)
        self.assertGreater(len(session._preview.pcm),len(first.pcm))
        session.feed(SILENCE)
        self.assertFalse(session._finals)
        self.assertIsNotNone(session._preview)

    def test_closed_ui_callback_cannot_lose_transcription(self):
        def closed(payload): raise RuntimeError('UI closed')
        result = self.execute(StreamingSession(Runtime(),Config(),Path('.'),on_update=closed),VOICE)
        self.assertEqual(result['text'],'PHRASE 1')

    def test_inflight_stale_cleanup_cannot_overwrite_final_asr(self):
        entered,release = threading.Event(),threading.Event()
        class Slow(Runtime):
            def clean(self,raw,c,cancel):
                if raw=='Wrong name.':
                    entered.set()
                    release.wait(2)
                return super().clean(raw,c,cancel)
        session = StreamingSession(Slow(),Config(),Path('.'))
        self.accept(session,'Wrong name.')
        self.accept(session,'Wrong name.')
        worker = threading.Thread(target=session._cleanup_loop,daemon=True)
        worker.start()
        self.assertTrue(entered.wait(2))
        self.accept(session,'Correct name.',final=True)
        with session._condition:
            session._asr_done = True
            session._condition.notify_all()
        release.set();worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(session._snapshot()['text'],'CORRECT NAME.')

    def test_whisper_keeps_working_while_completed_sentence_is_cleaned(self):
        recognizing,cleaning,release = threading.Event(),threading.Event(),threading.Event()
        class Overlap(Runtime):
            def transcribe(self,*args,**kwargs):
                recognizing.set()
                release.wait(2)
                return 'First sentence. Next sentence.'
            def clean(self,raw,c,cancel):
                cleaning.set()
                if recognizing.wait(2): release.set()
                return super().clean(raw,c,cancel)
        session = StreamingSession(Overlap(),Config(),Path('.'))
        self.accept(session,'First sentence.')
        self.accept(session,'First sentence.')
        result = self.execute(session,VOICE)
        self.assertTrue(cleaning.is_set() and recognizing.is_set())
        self.assertEqual(result['text'],'FIRST SENTENCE. NEXT SENTENCE.')


class SentenceTests(unittest.TestCase):
    def test_completed_sentences_and_tail(self):
        buffer = SentenceBuffer()
        self.assertEqual(buffer.feed('First sentence. Second question? unfinished'),['First sentence.','Second question?'])
        self.assertEqual(buffer.pending,'unfinished')
        self.assertEqual(buffer.feed('thought'),[])
        self.assertEqual(buffer.finish(),['unfinished thought'])
        self.assertEqual(buffer.finish(),[])

    def test_abbreviations_decimals_initials_and_quotes(self):
        buffer = SentenceBuffer()
        text = 'Dr. A. Smith uses version 1.2. He said "Hello!"'
        self.assertEqual(buffer.feed(text),['Dr. A. Smith uses version 1.2.','He said "Hello!"'])
        self.assertEqual(buffer.feed('The U.S. office opens at 9 a.m. on Monday.'),['The U.S. office opens at 9 a.m. on Monday.'])

    def test_obvious_incomplete_ending_waits_for_continuation(self):
        buffer = SentenceBuffer()
        self.assertEqual(buffer.feed('My name is.'),[])
        self.assertEqual(buffer.feed('Example Person.'),['My name is. Example Person.'])

    def test_hindi_and_unicode_sentence_endings(self):
        buffer = SentenceBuffer()
        self.assertEqual(buffer.feed('नमस्ते। Next sentence！'),['नमस्ते।','Next sentence！'])


if __name__ == '__main__': unittest.main()
