"""Overlap independent local Whisper/Qwen jobs and record NVIDIA/Windows GPU counters.

No microphone, app setting writes or external requests. This is a concurrency
and memory test, not same-utterance dictation latency: Qwen uses synthetic text.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import wave

from localflow.config import Config
from localflow.engines import cleanup_prompt, validate_cleanup, EngineError
from benchmark_pipeline_gpu import sha


RAW = ('um I want to improve this offline dictation application without uploading recordings '
       'please check that the microphone receives speech before starting recognition and show '
       'the original transcript alongside the cleaned result so that I can review the changes '
       'the first test should preserve version 2 and the appointment at 4 pm. '
       'For the next task please explain how the shortcut works and how to reopen the main window '
       'after it has been hidden in the tray I would like a clear status while recording and a '
       'separate message while the speech model is working then show another message during text '
       'cleanup and preserve the correct spelling of technical terms. '
       'Also describe how the processor and graphics card share the work the speech recognition '
       'model receives audio whereas the cleanup model receives text please do not invent any '
       'additional facts or change the meaning of these instructions. '
       'Finally mention that the test recording and this paragraph are separate inputs for a '
       'simultaneous hardware experiment the real cleanup of a new utterance must wait for its '
       'transcript to become available please keep this distinction clear when reporting the '
       'results and include both the time spent working and any startup delay.')
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def nvidia(pids):
    row = {'elapsed': None}
    query = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,power.draw,pstate',
                            '--format=csv,noheader,nounits'], capture_output=True,timeout=4,creationflags=FLAGS)
    values = query.stdout.decode(errors='replace').splitlines()
    if values:
        fields = [x.strip() for x in values[0].split(',')]
        for key, value in zip(['gpu_percent','memory_mib','power_watts','pstate'], fields):
            try: row[key] = float(value)
            except ValueError: row[key] = value
    query = subprocess.run(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],
                           capture_output=True,timeout=4,creationflags=FLAGS)
    seen = set(re.findall(r'^\s*(\d+)\s*$',query.stdout.decode(errors='replace'),re.M))
    row['benchmark_compute_pids'] = [pid for pid in pids if str(pid) in seen]
    return row


def launch(name,args,folder,started):
    out = (folder/(name+'.out')).open('wb')
    err = (folder/(name+'.err')).open('wb')
    proc = subprocess.Popen(list(map(str,args)),stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=FLAGS)
    return dict(name=name,proc=proc,handles=[out,err],start=time.perf_counter()-started)


def run_round(kind,whisper_args,qwen_args,folder,timeout):
    started = time.perf_counter()
    jobs = [launch('whisper',whisper_args,folder,started)]
    if kind=='concurrent': jobs.append(launch('qwen',qwen_args,folder,started))
    samples = []
    stop = folder/'stop-monitor'
    perf_file = folder/'windows-counters.json'
    monitor = None
    try:
        while True:
            for job in jobs:
                if job['proc'].poll() is not None and 'end' not in job:
                    job['end'] = time.perf_counter()-started
            if kind=='sequential' and len(jobs)==1 and 'end' in jobs[0]:
                jobs.append(launch('qwen',qwen_args,folder,started))
            if len(jobs)==2 and monitor is None:
                monitor = subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive',
                    '-File',str(Path(__file__).with_name('monitor_gpu_engines.ps1')),
                    '-TargetPids',','.join(str(x['proc'].pid) for x in jobs),
                    '-StopPath',str(stop),'-OutputPath',str(perf_file)],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=FLAGS)
            if len(jobs)==2 and all('end' in x for x in jobs): break
            if time.perf_counter()-started > timeout: raise TimeoutError('Concurrent GPU test timed out')
            try:
                sample = nvidia([x['proc'].pid for x in jobs])
                sample['elapsed'] = round(time.perf_counter()-started,3)
                samples.append(sample)
            except (OSError,subprocess.TimeoutExpired) as error:
                samples.append({'elapsed':round(time.perf_counter()-started,3),'monitor_error':type(error).__name__})
            time.sleep(.1)
        elapsed = time.perf_counter()-started
    finally:
        for job in jobs:
            if job['proc'].poll() is None:
                job['proc'].kill()
            job['proc'].wait()
            for handle in job['handles']: handle.close()
        stop.touch()
        if monitor:
            try: monitor.wait(timeout=8)
            except subprocess.TimeoutExpired:
                monitor.kill(); monitor.wait()
    result = {'kind':kind,'total_observed_seconds':round(elapsed,3),'jobs':[], 'nvidia_samples':samples}
    for job in jobs:
        name=job['name']
        item={'name':name,'pid':job['proc'].pid,'exit_code':job['proc'].returncode,
              'start_seconds':round(job['start'],3),'end_observed_seconds':round(job['end'],3),
              'seen_in_nvidia_compute_list':any(job['proc'].pid in s.get('benchmark_compute_pids',[]) for s in samples)}
        logs=(folder/(name+'.err')).read_text(encoding='utf-8',errors='replace')
        if name=='whisper':
            item['cuda_backend_confirmed']=bool(re.search(r'whisper_backend_init_gpu: using CUDA',logs))
            try:
                transcript=json.loads((folder/'asr.json').read_text(encoding='utf-8'))
                raw=''.join(x['text'] for x in transcript['transcription']).strip()
                item['nonempty_transcript']=bool(raw)
                item['output_sha256']=hashlib.sha256(raw.encode()).hexdigest()
            except (OSError,ValueError,KeyError,TypeError) as error:
                item['nonempty_transcript']=False
                item['result_error']=type(error).__name__
        else:
            text=(folder/(name+'.out')).read_text(encoding='utf-8',errors='replace')
            try:
                cleaned=validate_cleanup(RAW,text)
                item['cleanup_guardrails_passed']=True
                item['output_sha256']=hashlib.sha256(cleaned.encode()).hexdigest()
            except EngineError as error:
                item['cleanup_guardrails_passed']=False
                item['validation_error']=str(error)
        if job['proc'].returncode: item['diagnostic_tail']=logs[-2000:]
        result['jobs'].append(item)
    result['both_compute_contexts_seen_together']=any(len(s.get('benchmark_compute_pids',[]))==2 for s in samples)
    result['peak_gpu_percent']=max((s['gpu_percent'] for s in samples if isinstance(s.get('gpu_percent'),(int,float))),default=None)
    result['peak_total_gpu_memory_mib']=max((s['memory_mib'] for s in samples if isinstance(s.get('memory_mib'),(int,float))),default=None)
    result['windows_counters']=json.loads(perf_file.read_text(encoding='utf-8-sig')) if perf_file.exists() else {'error':'No counter report returned'}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--mode',choices=['comparison','concurrent'],default='comparison')
    parser.add_argument('--runs',type=int,default=2)
    args=parser.parse_args()
    if not 1 <= args.runs <= 3: parser.error('runs must be 1–3')
    root=args.root.resolve()
    output=args.output or root/'benchmarks/simultaneous-gpu-test.json'
    if output.exists(): parser.error('Existing report preserved; use a new output path')
    config_before=sha(root/'config.json')
    c=Config.load(root/'config.json')
    with wave.open(str(root/'samples/jfk.wav'),'rb') as stream:
        frames=stream.readframes(stream.getnframes())
    report={'whisper_model':c.asr_model,'beam_size':c.beam_size,'language':c.language,
            'audio_seconds':36,'synthetic_text_words':len(RAW.split()),'rounds':[],
            'notes':('Three copies of public 11-second JFK speech plus silence, and independent synthetic '
                     'text. Concurrent means both inference jobs overlap; it does not prove simultaneous '
                     'kernel execution on shared GPU cores. NVIDIA utilization/memory are GPU-wide and '
                     'include background apps. Windows counters are restricted to these benchmark PIDs. '
                     'This is not same-utterance dictation latency. No app settings or microphone access.')}
    output.parent.mkdir(parents=True,exist_ok=True)
    report['baseline_nvidia']=nvidia([])
    with tempfile.TemporaryDirectory(prefix='localflow-concurrent-') as tmp:
        temp=Path(tmp)
        wav=temp/'public-test.wav'
        with wave.open(str(wav),'wb') as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(16000)
            stream.writeframes((frames+b'\0\0'*16000)*3)
        prompt=temp/'synthetic-prompt.txt'
        prompt.write_text(cleanup_prompt(RAW,'Natural'),encoding='utf-8')
        rounds=(['sequential'] if args.mode=='comparison' else [])+['concurrent']*args.runs
        for index,kind in enumerate(rounds,1):
            folder=temp/str(index);folder.mkdir()
            model=c.resolve(root,c.base_model if c.asr_model=='base' else c.small_model)
            whisper=[root/'vendor/whisper-cuda/Release/whisper-cli.exe','-m',model,'-f',wav,
                     '-t',str(c.threads),'-l',c.language,'-bs',str(c.beam_size),'-bo',str(c.beam_size),
                     '-oj','-of',folder/'asr','-nfa']
            if c.vad_model:
                whisper+=['--vad','--vad-model',c.resolve(root,c.vad_model),'--vad-speech-pad-ms','200']
            qwen=[root/'vendor/llama-cuda/llama-completion.exe','-m',c.resolve(root,c.cleanup_model),
                  '-f',prompt,'-no-cnv','--no-display-prompt','--simple-io','-ngl','99','--device','CUDA0',
                  '-t','4','-c','4096','-n','1024','--temp','0','--seed','1','-fa','off','--fit','off',
                  '-b','2048','-ub','32','-lv','3']
            print('Starting',kind,'round',index,flush=True)
            result=run_round(kind,whisper,qwen,folder,180)
            result['round']=index
            report['rounds'].append(result)
            output.write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in result.items() if k not in ('nvidia_samples','windows_counters')}),flush=True)
    report['config_unchanged']=config_before==sha(root/'config.json')
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Metadata-only report:',output,flush=True)


if __name__=='__main__': main()
