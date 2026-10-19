"""Real GPU test: Whisper decides live cleanup without a silence endpoint."""
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
from localflow.streaming import SentenceBuffer,StreamingSession


def digest(text): return hashlib.sha256(text.encode()).hexdigest()


def run(root):
    c = replace(Config.load(root/'config.json'),streaming_enabled=True,gpu=True,cleanup_gpu=True,
                cleanup_enabled=True,mode='Natural',asr_model='small',beam_size=5)
    with wave.open(str(root/'samples/jfk.wav'),'rb') as audio:
        clip = audio.readframes(audio.getnframes())
    pcm = clip+bytes(3200)+clip
    runtime = ResidentModels(c,root)
    calls,previews,finals,events = [],[],[],[]
    stopped = threading.Event()
    report = {'input':'public JFK twice with only 0.1 seconds added between utterances',
              'audio_seconds':len(pcm)/32000,'microphone_opened':False}
    try:
        start = time.monotonic();runtime.start()
        report['load_seconds'] = round(time.monotonic()-start,3)
        report['whisper_gpu'],report['qwen_gpu'] = runtime.asr.gpu_confirmed,runtime.qwen.gpu_confirmed
        origin = time.monotonic()
        class Observed:
            def __getattr__(self,key): return getattr(runtime,key)
            def transcribe(self,audio,config,cancel,interim=False):
                raw = runtime.transcribe(audio,config,cancel,interim)
                sentences = SentenceBuffer().feed(raw)
                (previews if interim else finals).append({'seconds':time.monotonic()-origin,
                                                         'sentences':[digest(s) for s in sentences]})
                return raw
            def clean(self,text,config,cancel):
                key = digest(text)
                calls.append({'seconds':round(time.monotonic()-origin,3),'words':len(text.split()),
                              'after_stop':stopped.is_set(),
                              'last_two_previews_agree':len(previews)>=2 and all(key in p['sentences'] for p in previews[-2:]),
                              'sha256':key})
                return runtime.clean(text,config,cancel)
        session = StreamingSession(Observed(),c,root,on_update=lambda p:events.append(
            {'seconds':time.monotonic()-origin,'visible':bool(p['text']),
             'both_busy':p['asr_busy'] and p['cleanup_busy']}))
        report['silence_endpoint_disabled'] = session.segmenter.pause_frames is None
        output = {}
        def execute():
            try: output['result'] = session.run()
            except Exception as error: output['error'] = type(error).__name__
        thread = threading.Thread(target=execute,daemon=True);thread.start()
        for offset in range(0,len(pcm),640):
            delay = origin+offset/32000-time.monotonic()
            if delay>0: time.sleep(delay)
            session.feed(pcm[offset:offset+640])
        delay = origin+len(pcm)/32000-time.monotonic()
        if delay>0: time.sleep(delay)
        stopped.set();session.finish_input(pcm)
        thread.join(c.inference_timeout*2)
        if thread.is_alive() or 'error' in output: raise RuntimeError('Whisper endpoint test failed')
        result = output['result']
        words = lambda text:re.findall(r"[a-z]+(?:'[a-z]+)?",text.lower())
        reference = 'And so my fellow Americans ask not what your country can do for you ask what you can do for your country'
        report.update(cleanup_requests=calls,preview_requests=len(previews),final_full_recording_requests=len(finals),
            only_stable_sentences_before_stop=all(x['last_two_previews_agree'] for x in calls if not x['after_stop']),
            cleanup_before_stop=any(not x['after_stop'] for x in calls),
            first_preview_seconds=round(next((e['seconds'] for e in events if e['visible']),0),3),
            after_stop_ms=result['tail_ms'],raw_matches_reference=words(result['raw'])==words(reference+' '+reference),
            overlap_observed=any(e['both_busy'] for e in events),cpu_fallback=result['cpu_fallback'])
        report['passed'] = bool(report['whisper_gpu'] and report['qwen_gpu'] and report['silence_endpoint_disabled'] and
            report['raw_matches_reference'] and report['only_stable_sentences_before_stop'] and report['cleanup_before_stop'] and len(finals)==1)
    finally:
        runtime.close()
    report['workers_stopped'] = all(w.proc.poll() is not None for w in (runtime.asr,runtime.qwen) if w and w.proc)
    return report


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--output',type=Path,default=Path('benchmarks/whisper-endpoints-native.json'))
    args = parser.parse_args()
    report = run(args.root.resolve())
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['passed'] else 1)
