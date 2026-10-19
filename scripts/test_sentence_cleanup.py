"""Native GPU sentence-gating test using public audio, no mic or settings writes."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import wave

from localflow.config import Config
from localflow.resident import ResidentModels
from localflow.streaming import StreamingSession


def run(root):
    c = replace(Config.load(root/'config.json'),streaming_enabled=True,gpu=True,cleanup_gpu=True,
                cleanup_enabled=True,mode='Natural',asr_model='small',beam_size=5)
    with wave.open(str(root/'samples/jfk.wav'),'rb') as audio:
        clip = audio.readframes(audio.getnframes())
    pcm = clip+bytes(48000)+clip
    runtime = ResidentModels(c,root)
    report = {'input':'bundled public JFK sample twice with a 1.5-second pause',
              'audio_seconds':len(pcm)/32000,'microphone_opened':False}
    calls,previews,finals = [],[],[]
    stopped = threading.Event()
    try:
        start = time.monotonic();runtime.start()
        report['load_seconds'] = round(time.monotonic()-start,3)
        report['whisper_gpu'] = runtime.asr.gpu_confirmed
        report['qwen_gpu'] = runtime.qwen.gpu_confirmed
        origin = time.monotonic()
        class Observed:
            def __getattr__(self,key): return getattr(runtime,key)
            def transcribe(self,audio,config,cancel,interim=False):
                result = runtime.transcribe(audio,config,cancel,interim)
                (previews if interim else finals).append(time.monotonic()-origin)
                return result
            def clean(self,text,config,cancel):
                calls.append({'seconds':round(time.monotonic()-origin,3),
                              'words':len(text.split()),'after_stop':stopped.is_set(),
                              'sentence_end':bool(re.search(r'[.!?।。！？]["”’\')\]]*$',text)),
                              'final_asr_preceded':bool(finals),
                              'sha256':hashlib.sha256(text.encode()).hexdigest()})
                return runtime.clean(text,config,cancel)
        events = []
        session = StreamingSession(Observed(),c,root,on_update=lambda p:events.append(
            {'seconds':time.monotonic()-origin,'visible':bool(p['text']),
             'both_busy':p['asr_busy'] and p['cleanup_busy']}))
        output = {}
        def execute():
            try: output['result'] = session.run()
            except Exception as error: output['error'] = type(error).__name__
        thread = threading.Thread(target=execute,daemon=True)
        thread.start()
        for offset in range(0,len(pcm),640):
            delay = origin+offset/32000-time.monotonic()
            if delay>0: time.sleep(delay)
            session.feed(pcm[offset:offset+640])
        delay = origin+len(pcm)/32000-time.monotonic()
        if delay>0: time.sleep(delay)
        stopped.set();session.finish_input(pcm)
        thread.join(c.inference_timeout*2)
        if thread.is_alive() or 'error' in output: raise RuntimeError('Native sentence test failed')
        result = output['result']
        words = lambda text:re.findall(r"[a-z]+(?:'[a-z]+)?",text.lower())
        reference = 'And so my fellow Americans ask not what your country can do for you ask what you can do for your country'
        report.update(cleanup_requests=calls,preview_requests=len(previews),final_asr_requests=len(finals),
            no_cleanup_from_previews=all(x['final_asr_preceded'] for x in calls),
            sentences_only_before_stop=all(x['sentence_end'] for x in calls if not x['after_stop']),
            cleanup_before_stop=any(not x['after_stop'] for x in calls),
            first_preview_seconds=round(next((e['seconds'] for e in events if e['visible']),0),3),
            after_stop_ms=result['tail_ms'],raw_matches_reference=words(result['raw'])==words(reference+' '+reference),
            overlap_observed=any(e['both_busy'] for e in events),cpu_fallback=result['cpu_fallback'])
        report['passed'] = bool(report['whisper_gpu'] and report['qwen_gpu'] and report['raw_matches_reference'] and
                report['no_cleanup_from_previews'] and report['sentences_only_before_stop'] and
                report['cleanup_before_stop'] and len(calls)>=2)
    finally:
        runtime.close()
    report['workers_stopped'] = all(w.proc.poll() is not None for w in (runtime.asr,runtime.qwen) if w and w.proc)
    return report


if __name__=='__main__':
    # Preserve the old pause-gated report. Runs now use the current endpoint test.
    import runpy
    runpy.run_path(str(Path(__file__).with_name('test_whisper_endpoints.py')),run_name='__main__')
