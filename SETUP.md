# Vowely setup

## Windows portable prerelease

Extract the full Windows x64 release ZIP. Keep `app/Vowely`, its `_internal` folder, the setup script and launch script together. Run **Setup models and engines.ps1** from the extracted folder. It explicitly downloads the pinned assets in assets-manifest.json, checks SHA-256, preserves differing existing files, and copies matching CUDA runtime DLLs beside their engines. It never opens the microphone or uploads audio/text. A setup failure is recorded in setup-downloads.log; retry after correcting the cause. Verified files and partial downloads are reused.

Setup downloads about 3.3 GB; allow at least 10 GB of free disk space for archives, engines, models and runtime. After setup, double-click **Start Vowely.vbs**. No administrator rights or separate Python installation are required. The executable is unsigned. Keep the folder outside cloud-synchronised storage if strict local storage is required.

To provision an offline machine, run setup on an online Windows x64 machine, then transfer the complete extracted/provisioned folder through trusted media. No external inference is used after setup.

## Install from source

Use Windows x64 and Python 3.11–3.13 x64; the tested source environment uses Python 3.12. Keep installation inside this project:

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -c constraints-windows-py312.txt -e .
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe scripts/provision.py
if (-not (Test-Path config.json)) { Copy-Item config.example.json config.json }
.venv/Scripts/python.exe -m localflow.doctor --root .
.venv/Scripts/python.exe -m localflow.launcher --root .
```

Provisioning is explicitly online. Ordinary launch never downloads models. The source checkout excludes models, native executables, recordings, local settings, cached downloads and the Python environment. The public WAV benchmark fixture is also fetched from its pinned upstream revision during provisioning; personal recordings are never included.

For dependency installation without internet, prepare compatible x64 wheels on an online Windows machine using the same Python version:

```powershell
py -3.12 -m pip wheel --wheel-dir wheelhouse -c constraints-windows-py312.txt .
py -3.12 -m pip download --dest wheelhouse setuptools wheel
# Transfer source, wheelhouse and already verified model/engine assets.
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install --no-index --find-links wheelhouse -e .
```

## Configuration

Copy config.example.json only when config.json is absent. The example enables live Small recognition and local cleanup on CPU, with auto-insertion off, no permitted fields and no personal vocabulary. CPU is the portable baseline. Choose GPU explicitly after testing your hardware. Settings are saved locally when preparing models, starting a test or arming the shortcut.

Live CUDA paths use Whisper b5454 CUDA 11.8 under vendor/whisper-cuda/Release and llama.cpp b11734 CUDA 12.4 under vendor/llama-cuda. Their DLL sets are deliberately separate; do not mix them or modify system PATH. CPU counterparts stay under vendor/whisper/Release and vendor/llama. GPU startup failure can retry the local CPU engine. Live recognition failure processes the whole recording locally after Stop and requires review.

Select a currently connected microphone supporting 16 kHz mono PCM16. The basic list combines duplicate driver routes; advanced view exposes raw inputs. The app never silently changes the selected microphone. Check Windows microphone permissions yourself if recording cannot open.

## Build a Windows app

Install the tested PyInstaller version and run the packaging script while its destination app is stopped:

```powershell
.venv/Scripts/python.exe -m pip install pyinstaller==6.22.3
./scripts/package.ps1 -Destination app
```

This creates app/Vowely/Vowely.exe with its runtime. scripts/fix_bundle.py is required for compatibility with the tested Python/Qt runtime. Windows file/product version resources and the UI use the release identifier in src/localflow/version.py. Run scripts/build_release.py after packaging to create the portable ZIP; it excludes personal configuration and includes a clean example-based release configuration.

Use the packaged --self-test-report option to check startup without recording. Real microphone, insertion and hardware benchmarks are explicit opt-in operations. See DEVELOPMENT.md and PRIVACY.md.
