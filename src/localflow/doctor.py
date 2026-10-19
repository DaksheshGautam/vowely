"""Read-only dependency checks. Never opens a microphone or installs anything."""
import argparse
import importlib.util
from pathlib import Path
import platform

from .config import Config
from .engines import run_local
from .windows import parse_hotkey


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path.cwd())
    args = p.parse_args()
    c = Config.load(args.root / "config.json")
    parse_hotkey(c.hotkey)
    failed = False
    print(f"Host: {platform.system()} {platform.machine()}; Python {platform.python_version()}")
    for module in ("PySide6", "sounddevice", "comtypes", "psutil"):
        found = importlib.util.find_spec(module) is not None
        print(f"{'OK' if found else 'MISSING'} dependency: {module}")
        failed |= not found
    files = [("Whisper executable", c.whisper_exe),
             ("Selected Whisper model", c.base_model if c.asr_model == "base" else c.small_model)]
    if c.cleanup_enabled:
        files += [("Cleanup executable", c.llama_exe), ("Cleanup model", c.cleanup_model)]
    if c.vad_model:
        files.append(("VAD model", c.vad_model))
    for name, value in files:
        file = c.resolve(args.root, value)
        found = file.is_file()
        print(f"{'OK' if found else 'MISSING'} {name}: {file}")
        failed |= not found
    for value in [c.whisper_exe] + ([c.llama_exe] if c.cleanup_enabled else []):
        exe = c.resolve(args.root, value)
        if exe.is_file():
            try:
                # Help may go to stderr. This is a startup/DLL check, not flag validation.
                run_local([exe, "--help"], 15)
                print(f"OK executable starts: {exe.name}")
            except Exception as exc:
                print(f"FAIL executable startup: {type(exc).__name__}")
                failed = True
    print("No recording, focus insertion, network request or hotkey registration performed.")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
