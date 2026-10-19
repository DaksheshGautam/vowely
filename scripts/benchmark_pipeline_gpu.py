"""Offline sequential Whisper/Qwen comparison on the bundled public JFK clip.

Uses saved recognition settings without changing them. No microphone, cursor
insertion or network access. Reports measurements and hashes, never transcripts.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time
import wave

from localflow.config import Config
from localflow.engines import Whisper, cleanup_prompt
from benchmark_cleanup_gpu import measure


REFERENCE = ('And so my fellow Americans ask not what your country can do for you '
             'ask what you can do for your country')
PROFILES = {'cpu_cpu': (False, False), 'cpu_cuda': (False, True), 'cuda_cuda': (True, True)}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def word_errors(text):
    ref = re.findall(r"\w+", REFERENCE.lower())
    hyp = re.findall(r"\w+", text.lower())
    previous = list(range(len(hyp)+1))
    for i, a in enumerate(ref, 1):
        current = [i]
        for j, b in enumerate(hyp, 1):
            current.append(min(previous[j]+1, current[-1]+1, previous[j-1]+(a!=b)))
        previous = current
    return {'word_errors': previous[-1], 'reference_words': len(ref),
            'word_error_rate': round(previous[-1]/len(ref), 4)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--runs', type=int, default=2)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 1 <= args.runs <= 5 or not 30 <= args.timeout <= 300:
        parser.error('runs must be 1–5; timeout must be 30–300 seconds per engine')
    root = args.root.resolve()
    output = args.output or root/'benchmarks/pipeline-cpu-gpu-comparison.json'
    if output.exists():
        parser.error('Existing report is preserved; select a new --output path')
    c = Config.load(root/'config.json')
    config_hash_before = sha(root/'config.json')
    model = c.resolve(root, c.base_model if c.asr_model=='base' else c.small_model)
    qwen = c.resolve(root, c.cleanup_model)
    wav = root/'samples/jfk.wav'
    with wave.open(str(wav),'rb') as stream:
        if (stream.getnchannels(),stream.getsampwidth(),stream.getframerate()) != (1,2,16000):
            parser.error('Bundled sample must be 16 kHz mono PCM16')
        clip_seconds = stream.getnframes()/16000
        pcm = stream.readframes(stream.getnframes())
    engines = {'whisper_cpu':root/'vendor/whisper/Release/whisper-cli.exe',
               'whisper_cuda':root/'vendor/whisper-cuda/Release/whisper-cli.exe',
               'qwen_cpu':root/'vendor/llama/llama-completion.exe',
               'qwen_cuda':root/'vendor/llama-cuda/llama-completion.exe'}
    for path in [model,qwen,*engines.values()]:
        if not path.is_file():
            parser.error('Missing local asset: '+str(path))
    gpu_info = subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total',
                               '--format=csv,noheader'],capture_output=True,timeout=10,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    report = {'clip_seconds':clip_seconds,'clip_sha256':sha(wav),
              'whisper_model':c.asr_model,'whisper_model_sha256':sha(model),
              'qwen_model_sha256':sha(qwen),'beam_size':c.beam_size,'language':c.language,
              'threads':c.threads,'vad_enabled':bool(c.vad_model),'vad_speech_padding_ms':200,
              'personal_vocabulary_count':len(c.personal_vocabulary),'mode':'Natural',
              'device':gpu_info.stdout.decode(errors='replace').strip(),
              'config_sha256_before':config_hash_before,'samples':[],
              'qwen_cpu_ubatch':512,'qwen_cuda_ubatch':32,
              'notes':('Both models run sequentially; Whisper exits before Qwen loads, so simultaneous '
                       'model residency is not tested. Fresh engine processes for every phase; includes '
                       'model loading and diagnostic GPU PID probing. OS/driver caches may warm. '
                       'Word error rate is for one public clip only. No microphone or insertion. '
                       'The app settings are never written by this benchmark.')}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    for repeat in range(args.runs):
        order = list(PROFILES) if repeat % 2 == 0 else list(reversed(PROFILES))
        for profile in order:
            asr_gpu, qwen_gpu = PROFILES[profile]
            row = {'profile':profile,'repeat':repeat+1}
            started = time.perf_counter()
            try:
                config = replace(c, gpu=asr_gpu, inference_timeout=args.timeout,
                                 whisper_exe=str(engines['whisper_cuda' if asr_gpu else 'whisper_cpu']),
                                 cpu_whisper_exe=str(engines['whisper_cpu']))
                whisper = Whisper(config,root)
                raw = whisper.transcribe(pcm)
                row.update(asr_seconds=round(time.perf_counter()-started,3),
                           whisper_gpu_requested=asr_gpu,whisper_gpu_confirmed=whisper.gpu_used,
                           whisper_cpu_fallback=whisper.cpu_fallback,
                           raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                           **word_errors(raw))
                print(json.dumps(dict(phase='whisper_complete',**row)),flush=True)
                if not raw.strip():
                    raise RuntimeError('No transcript; cleanup was not run')
                with tempfile.TemporaryDirectory(prefix='localflow-pipeline-bench-') as tmp:
                    prompt = Path(tmp)/'prompt.txt'
                    prompt.write_text(cleanup_prompt(raw,'Natural',c.personal_vocabulary),encoding='utf-8')
                    cleanup = measure(engines['qwen_cuda' if qwen_gpu else 'qwen_cpu'],qwen,
                                      prompt,raw,qwen_gpu,args.timeout,32 if qwen_gpu else 512)
                row['cleanup'] = cleanup
                row['valid'] = (cleanup.get('exit_code')==0 and cleanup.get('cleanup_guardrails_passed')
                                and (not qwen_gpu or cleanup.get('gpu_confirmed'))
                                and (not asr_gpu or (whisper.gpu_used and not whisper.cpu_fallback)))
            except Exception as error:
                row['valid'] = False
                row['error'] = type(error).__name__+': '+str(error)
            row['total_seconds'] = round(time.perf_counter()-started,3)
            report['samples'].append(row)
            output.write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(row),flush=True)
    report['summary'] = {}
    for profile in PROFILES:
        rows = [row for row in report['samples'] if row['profile']==profile and row.get('valid')]
        report['summary'][profile] = {'valid_runs':len(rows)}
        if rows:
            report['summary'][profile].update(
                median_asr_seconds=statistics.median(row['asr_seconds'] for row in rows),
                median_cleanup_seconds=statistics.median(row['cleanup']['wall_seconds'] for row in rows),
                median_total_seconds=statistics.median(row['total_seconds'] for row in rows))
    report['config_sha256_after'] = sha(root/'config.json')
    report['config_unchanged_during_test'] = report['config_sha256_after']==config_hash_before
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Summary:',json.dumps(report['summary']),flush=True)
    print('Metadata-only report:',output,flush=True)


if __name__=='__main__':
    main()
