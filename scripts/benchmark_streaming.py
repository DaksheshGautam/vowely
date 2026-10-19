"""Real-time public-audio replay through the same resident pipeline as the UI.

No microphone, downloads, application setting writes, or transcript retention.
Reports first visible text, completed phrases before Stop, overlap and tail delay.
"""
import argparse
from dataclasses import replace
import hashlib
import http.client
import json
from pathlib import Path
import re
import threading
import time
import wave

from localflow.config import Config
from localflow.resident import ResidentModels
from localflow.streaming import StreamingSession


def normalized(text): return re.findall(r"[a-z]+(?:'[a-z]+)?",text.lower())


def run(root):
    c = replace(Config.load(root/'config.json'),streaming_enabled=True,gpu=True,cleanup_gpu=True)
    with wave.open(str(root/'samples/jfk.wav'),'rb') as audio:
        sample = audio.readframes(audio.getnframes())
    # Two identical public utterances separated by a natural one-second pause.
    pcm = sample+bytes(32000)+sample
    runtime = ResidentModels(c,root)
    report = {'audio_seconds':len(pcm)/32000,'model':'small','beam_size':c.beam_size,
              'input':'public JFK sample twice, separated by one second of silence'}
    try:
        started = time.perf_counter()
        runtime.start()
        report['load_seconds'] = round(time.perf_counter()-started,3)
        report['whisper_gpu'] = runtime.asr.gpu_confirmed
        report['qwen_gpu'] = runtime.qwen.gpu_confirmed
        report['workers'] = [runtime.asr.proc.pid,runtime.qwen.proc.pid]
        # Both engines must reject inference requests without their private token.
        denied = {}
        for worker in (runtime.asr,runtime.qwen):
            conn = http.client.HTTPConnection('127.0.0.1',worker.port,timeout=3)
            path = '/inference' if worker.kind=='whisper' else '/completion'
            conn.request('POST',path,body=b'{}',headers={'Content-Type':'application/json'})
            response = conn.getresponse();response.read();conn.close()
            denied[worker.kind] = response.status in (401,403,404)
        report['unauthenticated_inference_blocked'] = denied
        origin = time.perf_counter()
        events = []
        def update(payload):
            events.append({'seconds':time.perf_counter()-origin,'has_text':bool(payload['raw']),
                           'cleaned':payload['cleaned_phrases'],
                           'both_busy':payload['asr_busy'] and payload['cleanup_busy']})
        session = StreamingSession(runtime,c,root,on_update=update)
        output = {}
        def execute():
            try: output['result'] = session.run()
            except Exception as error: output['error'] = type(error).__name__
        thread = threading.Thread(target=execute,daemon=True)
        thread.start()
        for offset in range(0,len(pcm),640):
            due = origin+offset/32000
            if due>time.perf_counter(): time.sleep(due-time.perf_counter())
            session.feed(pcm[offset:offset+640])
        due = origin+len(pcm)/32000
        if due>time.perf_counter(): time.sleep(due-time.perf_counter())
        stop = time.perf_counter()-origin
        session.finish_input(pcm)
        thread.join(c.inference_timeout*2)
        if thread.is_alive() or 'error' in output: raise RuntimeError('Live benchmark did not finish')
        result = output['result']
        report['streaming'] = {'first_text_seconds':round(next((e['seconds'] for e in events if e['has_text']),0),3),
            'phrases_cleaned_before_stop':max((e['cleaned'] for e in events if e['seconds']<stop),default=0),
            'overlap_observed':any(e['both_busy'] for e in events),
            'tail_seconds':result['tail_ms']/1000,'total_seconds':result['total_ms']/1000,
            'raw_words':len(normalized(result['raw'])),'clean_words':len(normalized(result['text'])),
            'raw_sha256':hashlib.sha256(result['raw'].encode()).hexdigest(),
            'warnings':result['warning'],'cpu_fallback':result['cpu_fallback']}
        expected = 'And so my fellow Americans ask not what your country can do for you ask what you can do for your country'
        report['streaming']['raw_matches_reference'] = normalized(result['raw'])==normalized(expected+' '+expected)
        # A fair warm comparison uses the same resident models and complete audio.
        started = time.perf_counter()
        raw = runtime.transcribe(pcm,c,threading.Event())
        after_asr = time.perf_counter()
        text,warning = runtime.clean(raw,c,threading.Event())
        report['after_stop_only_warm'] = {'asr_seconds':round(after_asr-started,3),
            'cleanup_seconds':round(time.perf_counter()-after_asr,3),
            'tail_seconds':round(time.perf_counter()-started,3),
            'raw_matches_reference':normalized(raw)==normalized(expected+' '+expected),
            'raw_words':len(normalized(raw)),'clean_words':len(normalized(text))}
        report['workers_reused'] = report['workers']==[runtime.asr.proc.pid,runtime.qwen.proc.pid]
        # Feed ahead to exercise the real backlog: Whisper must be able to work
        # on the second phrase while Qwen finishes the first, without fake text.
        overlap = []
        burst = StreamingSession(runtime,c,root,on_update=lambda p:overlap.append(p['asr_busy'] and p['cleanup_busy']))
        burst.feed(pcm);burst.finish_input(pcm)
        burst_result = burst.run()
        report['queued_phrase_test'] = {'overlap_observed':any(overlap),
            'raw_matches_reference':normalized(burst_result['raw'])==normalized(expected+' '+expected)}
        # Interrupt an actual native request and verify the workers cannot linger.
        active = threading.Event()
        cancelled = StreamingSession(runtime,c,root,on_update=lambda p:active.set() if p['asr_busy'] else None)
        cancelled.feed(pcm)
        cancelled_output = []
        def cancel_target():
            try: cancelled_output.append(cancelled.run())
            except Exception as error: cancelled_output.append(type(error).__name__)
        thread = threading.Thread(target=cancel_target,daemon=True)
        thread.start()
        if not active.wait(5): raise RuntimeError('No native recognition task started')
        started = time.perf_counter()
        cancelled.abort()
        thread.join(5)
        report['cancellation'] = {'seconds':round(time.perf_counter()-started,3),
            'finished':not thread.is_alive(),'no_partial_result':cancelled_output==['Cancelled']}
    finally:
        runtime.close()
    report['workers_stopped'] = all(w.proc.poll() is not None for w in (runtime.asr,runtime.qwen) if w and w.proc)
    return report


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--output',type=Path,default=Path('benchmarks/live-streaming.json'))
    args = parser.parse_args()
    report = run(args.root.resolve())
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
