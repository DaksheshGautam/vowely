"""Explicit offline Qwen CPU/CUDA comparison using synthetic text, never a microphone.

Requires the separately provisioned matching llama.cpp CUDA engine/runtime.
Does not read or change app settings. Reports metadata only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import tempfile
import time
import threading
from types import SimpleNamespace

from localflow.engines import cleanup_prompt, validate_cleanup, EngineError


CASES = {
    'short': 'um I am building an offline dictation app and uh I need to test version 2 tomorrow at 4 pm',
    'long': ('um please update the documentation for the local dictation application and explain how to '
             'choose the microphone before recording then uh describe how to hold the shortcut and release '
             'it after speaking I need the instructions to mention that speech recognition happens first '
             'and text cleanup happens afterwards please preserve version 2 and the meeting time of 4 pm '
             'and do not add any information that I did not say'),
}


def measure(exe, model, prompt, raw, gpu, timeout, ubatch=512):
    args = [str(exe), '-m', str(model), '-f', str(prompt), '-no-cnv',
            '--no-display-prompt', '--simple-io', '-ngl', '99' if gpu else '0',
            '-t', '4', '-c', '4096', '-n', '1024', '--temp', '0', '--seed', '1',
            '-fa', 'off', '--fit', 'off', '-b', '2048', '-ub', str(ubatch), '-lv', '3']
    if gpu:
        args += ['--device', 'CUDA0']
    done = threading.Event()
    cuda_pid_seen = [False]
    def watch_gpu(pid):
        # WDDM may omit memory figures, but a matching CUDA compute PID proves
        # this engine process created a compute context on the NVIDIA GPU.
        while not done.is_set():
            try:
                query = subprocess.run(['nvidia-smi', '--query-compute-apps=pid',
                                        '--format=csv,noheader,nounits'], capture_output=True,
                                       timeout=3, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if str(pid) in query.stdout.decode(errors='replace').split():
                    cuda_pid_seen[0] = True
            except (OSError, subprocess.TimeoutExpired):
                pass
            done.wait(.25)
    started = time.perf_counter()
    try:
        with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)) as proc:
            watcher = threading.Thread(target=watch_gpu, args=(proc.pid,), daemon=True) if gpu else None
            if watcher:
                watcher.start()
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise
            finally:
                seconds = time.perf_counter()-started
                done.set()
                if watcher:
                    watcher.join(4)
            run = SimpleNamespace(stdout=out,stderr=err,returncode=proc.returncode)
    except subprocess.TimeoutExpired:
        return dict(wall_seconds=round(time.perf_counter()-started, 3), timeout=True)
    text = run.stdout.decode('utf-8', errors='replace')
    logs = run.stderr.decode('utf-8', errors='replace')
    offload = re.search(r'offloaded\s+(\d+)/(\d+)\s+layers to GPU', logs)
    gpu_confirmed = bool((offload and int(offload[1]) > 0 and
                         re.search(r'CUDA\d+\s+model buffer size', logs)) or cuda_pid_seen[0])
    metadata = dict(wall_seconds=round(seconds, 3), exit_code=run.returncode,
                    gpu_requested=gpu, gpu_confirmed=gpu_confirmed,
                    offloaded_layers=int(offload[1]) if offload else None,
                    available_layers=int(offload[2]) if offload else None,
                    cuda_compute_pid_seen=cuda_pid_seen[0])
    for label, pattern in [('prompt', r'prompt eval time\s*=\s*([\d.]+) ms /\s*(\d+) tokens'),
                           ('generation', r'(?<!prompt )eval time\s*=\s*([\d.]+) ms /\s*(\d+) runs')]:
        match = re.search(pattern, logs)
        if match:
            metadata[label+'_ms'] = float(match[1])
            metadata[label+'_tokens'] = int(match[2])
    buffers = re.findall(r'CUDA\d+\s+(?:model|compute|KV) buffer size\s*=\s*([\d.]+) MiB', logs)
    metadata['reported_cuda_buffers_mib'] = round(sum(map(float, buffers)), 2) if buffers else (None if gpu else 0)
    metadata['device_lines'] = [line.strip() for line in logs.splitlines()
                                if re.search(r'Device \d+: NVIDIA|using device CUDA\d+', line)][:4]
    metadata['backend_diagnostics'] = [line.strip() for line in logs.splitlines()
                                      if re.search(r'CUDA|offload|GPU|buffer size|device', line, re.I)][:60]
    try:
        cleaned = validate_cleanup(raw, text)
        metadata['cleanup_guardrails_passed'] = True
        metadata['output_characters'] = len(cleaned)
        metadata['output_sha256'] = hashlib.sha256(cleaned.encode()).hexdigest()
    except EngineError as error:
        metadata['cleanup_guardrails_passed'] = False
        metadata['validation_error'] = str(error)
    if run.returncode:
        metadata['diagnostic_tail'] = logs[-2000:]
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--runs', type=int, default=2)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--ubatch', type=int, default=512)
    parser.add_argument('--case', choices=['all', *CASES], default='all')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not 1 <= args.runs <= 5 or not 10 <= args.timeout <= 300:
        parser.error('runs must be 1–5; timeout must be 10–300 seconds')
    if not 1 <= args.ubatch <= 512:
        parser.error('ubatch must be 1–512')
    root = args.root.resolve()
    output = args.output or root/'benchmarks/qwen-cpu-vs-gpu.json'
    if output.exists():
        parser.error('Report already exists; use a new --output path to preserve it')
    model = root/'models/Qwen3-1.7B-Q4_K_M.gguf'
    engines = {'cpu': root/'vendor/llama/llama-completion.exe',
               'cuda': root/'vendor/llama-cuda/llama-completion.exe'}
    for path in [model, *engines.values()]:
        if not path.is_file():
            parser.error('Missing local model/engine: '+str(path))
    with model.open('rb') as stream:
        model_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = dict(model=model.name, model_sha256=model_hash, engine_release='b11734',
                  threads=4, context=4096, max_output_tokens=1024, temperature=0,
                  seed=1, flash_attention=False, ubatch=args.ubatch,
                  cases={k:len(v.split()) for k,v in CASES.items() if args.case in ('all',k)},
                  samples=[], notes=('Synthetic text only. Each sample starts a fresh process and reloads '
                      'the model. OS/driver caches may warm. No app settings changed. Guardrails are '
                      'not a comprehensive accuracy score; manual review is still needed. GPU runs '
                      'include a background nvidia-smi PID probe; that can add some host overhead. '
                      'Explicit CUDA0 selection is used; missing layer logs are recorded as unknown.'))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='localflow-qwen-bench-') as tmp:
        for case, raw in CASES.items():
            if args.case not in ('all', case):
                continue
            prompt = Path(tmp)/(case+'.txt')
            prompt.write_text(cleanup_prompt(raw, 'Natural'), encoding='utf-8')
            for repeat in range(args.runs):
                # Alternate order to reduce an ordering bias from caches/thermals.
                for backend in (['cpu','cuda'] if repeat % 2 == 0 else ['cuda','cpu']):
                    row = dict(case=case, backend=backend, repeat=repeat+1,
                               **measure(engines[backend], model, prompt, raw, backend=='cuda', args.timeout, args.ubatch))
                    report['samples'].append(row)
                    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
                    print(json.dumps(row), flush=True)
                    if row.get('timeout') or row.get('exit_code') != 0:
                        raise SystemExit('Engine failed; report preserved, no app settings changed.')
                    if backend == 'cuda' and not row['gpu_confirmed']:
                        raise SystemExit('GPU offload not confirmed; refusing to label CPU work a GPU result.')
    report['medians_seconds'] = {
        case: {backend: statistics.median(row['wall_seconds'] for row in report['samples']
                                          if row['case']==case and row['backend']==backend)
               for backend in engines} for case in report['cases']}
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('Saved metadata-only report:',output,flush=True)


if __name__ == '__main__':
    main()
