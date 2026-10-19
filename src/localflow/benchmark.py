"""Opt-in local WAV benchmark; reports measurements, never transcript content."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform
import statistics
import threading
import time
import wave

from .config import Config
from .engines import pipeline


def main():
    p = argparse.ArgumentParser(description="Benchmark a local 16 kHz mono PCM16 WAV")
    p.add_argument("wav", type=Path)
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--model", choices=["base", "small"], default="base")
    p.add_argument("--gpu", action="store_true")
    p.add_argument("--cleanup", action="store_true")
    p.add_argument("--language", help="Override the configured language code")
    p.add_argument("--threads", type=int, help="Override CPU thread count")
    p.add_argument("--whisper-exe", help="Explicit engine override for reproducible backend testing")
    p.add_argument("--output", type=Path, default=Path("benchmark.json"))
    a = p.parse_args()
    if not 1 <= a.runs <= 30:
        p.error("runs must be 1–30")
    with wave.open(str(a.wav), "rb") as f:
        if (f.getnchannels(), f.getsampwidth(), f.getframerate(), f.getcomptype()) != (1, 2, 16000, "NONE"):
            p.error("WAV must be uncompressed 16 kHz, mono, PCM16")
        if not 0 < f.getnframes() <= 120 * 16000:
            p.error("WAV must contain between 0 and 120 seconds")
        seconds = f.getnframes() / 16000
        pcm = f.readframes(f.getnframes())
    c = replace(Config.load(a.root / "config.json"), asr_model=a.model, gpu=a.gpu,
                cleanup_enabled=a.cleanup, mode="Natural")
    if a.whisper_exe:
        c.whisper_exe = a.whisper_exe
    elif a.gpu:
        candidate = a.root / 'vendor/whisper-cuda/Release/whisper-cli.exe'
        if not candidate.is_file():
            p.error('No integrated CUDA engine found; provide --whisper-exe explicitly')
        c.whisper_exe = str(candidate.resolve())
    elif c.cpu_whisper_exe:
        c.whisper_exe = c.cpu_whisper_exe
    if a.language:
        c.language = a.language
    if a.threads:
        c.threads = a.threads
    c.validate()
    import psutil
    parent = psutil.Process()
    done = threading.Event()
    peak = [0]

    def sample():
        while not done.wait(0.05):
            total = 0
            for proc in [parent] + parent.children(recursive=True):
                try:
                    total += proc.memory_info().rss
                except psutil.Error:
                    pass
            peak[0] = max(peak[0], total)

    samples = []
    watcher = threading.Thread(target=sample, daemon=True)
    watcher.start()
    try:
        for index in range(a.runs):
            result = pipeline(pcm, c, a.root)
            row = {k: result[k] for k in ("asr_ms", "total_ms")}
            row["cleanup_ms"] = row["total_ms"] - row["asr_ms"]
            row["rtf"] = round(row["total_ms"] / 1000 / seconds, 3)
            row["cleanup_fallback_or_review"] = bool(result["warning"])
            row["cpu_fallback"] = result["cpu_fallback"]
            row["gpu_used"] = result["gpu_used"]
            samples.append(row)
            print(f"Run {index + 1}: {row}")
    finally:
        done.set()
        watcher.join(2)
    model = c.resolve(a.root, c.base_model if a.model == "base" else c.small_model)
    def sha256(path):
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    times = sorted(x["total_ms"] for x in samples)
    report = {"host": platform.platform(), "cpu": platform.processor(),
              "logical_cpus": psutil.cpu_count(), "ram_bytes": psutil.virtual_memory().total,
              "asr_model": a.model, "asr_model_sha256": sha256(model),
              "gpu_requested": a.gpu, "cleanup_requested": a.cleanup, "threads": c.threads,
              "language": c.language, "beam_size": c.beam_size, "vad_enabled": bool(c.vad_model),
              "clip_seconds": seconds, "peak_process_tree_rss_bytes": peak[0],
              "first_run_ms": times[0] if len(samples) == 1 else samples[0]["total_ms"],
              "median_ms": statistics.median(times),
              "p95_ms": times[max(0, __import__('math').ceil(0.95 * len(times)) - 1)],
              "samples": samples,
              "notes": "Each run launches a fresh engine and reloads models; OS file cache may warm. RSS is sampled and excludes VRAM. cpu_fallback records retries; successful GPU use still needs engine/GPU inspection. Accuracy must be scored manually."}
    with a.output.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Saved metadata only to {a.output}. No transcript was saved.")


if __name__ == "__main__":
    raise SystemExit(main())
