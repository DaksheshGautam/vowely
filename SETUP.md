# Vowely setup

## Recommended: Windows installer

Download Setup-x64.exe from the Vowely release, run it, then finish the model setup screen. No separate Python or setup script is needed. Start setup explicitly downloads missing Whisper Base/Small, Qwen3-1.7B, Silero and CPU engines. NVIDIA Whisper/Qwen support is optional and independent. Hash-matching files in the data folder are skipped; choose an existing Vowely folder to reuse models, engine files or cached archives. Downloads are resumed and verified before use; differing existing files are preserved and reported. Settings/dictionary import is optional and never overwrites an installed profile.

Internet is needed only for missing setup assets. CPU downloads are about 1.8 GB; both GPU options total about 3.3 GB. Allow up to 10 GB disk space. The installer includes the GUI runtime and app-local native runtime support; it does not install a GPU driver or modify system PATH. Dictation remains offline.

Use Start → Vowely to launch, or Start → Finish Vowely setup to repair/revisit downloads after quitting the app. Program files are installed per user under local application data / Programs / Vowely; models/configuration/dictionary/cache are under local application data / Vowely. Updates preserve them. The Windows Installed Apps uninstaller removes the program and shortcuts and deliberately keeps local data. No Windows startup entry is added.

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

Copy config.example.json only when config.json is absent. The example enables live Small recognition and local cleanup on CPU, with auto-insertion on and no personal vocabulary. CPU is the portable baseline. Choose GPU explicitly after testing your hardware. Settings are saved locally when preparing models, starting a test or arming the shortcut.

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

## Build the installer

Package `app-installer` with scripts/package.ps1. Install the verified Inno Setup 6.7.3 compiler using scripts/install_build_tools.ps1 with a new build-tools destination, or supply an existing compiler. Run scripts/build_installer.py with `--bundle app-installer/Vowely --stage build/installer/NEW_STAGE --iscc PATH_TO_ISCC --output release-assets/installer`. It requires checksum-matching upstream engine archives from explicit provisioning to create the extracted-file hash index; it never includes their contents or local model/profile data in the installer. Use a new stage for each build. The installer, checksum list and build report are emitted in the output directory. Validate silent install, packaged startup, setup reuse/download/cancel and uninstall before publication.

## Updating the installed app

Install beta.1 once using the release installer, then use Settings → Updates for future versions. Automatic checks can be disabled; downloads and installs remain explicit. Keep Include prereleases enabled to receive beta/RC releases. Review/copy the current result before restarting. Model/profile data lives outside the program directory and is preserved. The installer helper does not run model provisioning or add Windows startup tasks. If an update fails or needs a reboot, the local update-status message explains the next step. Portable/source copies use the normal installer to migrate; in-place installation targets are restricted to a recognized installed layout.
