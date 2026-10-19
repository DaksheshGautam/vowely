# Vowely

**v0.1.0-alpha.1 — Windows prerelease**

Offline personal dictation with global push-to-talk, live speech recognition, sentence-based text cleanup, and guarded cursor insertion. Built with Python, PySide6, whisper.cpp, llama.cpp, Whisper Base/Small, optional Silero VAD, and Qwen3-1.7B Q4_K_M.

Audio and transcripts stay on your computer. No external inference APIs, telemetry, account, transcript history, or automatic downloads during dictation.

## Download and start

1. Download **vowely-0.1.0-alpha.1-windows-x64.zip** from the [prerelease](https://github.com/DaksheshGautam/vowely/releases/tag/v0.1.0-alpha.1), and extract the complete ZIP to a writable folder.
2. Run **Setup models and engines.ps1** in that folder. This is an explicit, online, one-time download of about 3.3 GB of pinned assets. Allow at least 10 GB of free disk space. The Windows package includes its Python runtime; a separate Python installation is not required.
3. Double-click **Start Vowely.vbs**. Wait for the models to be ready. Choose your microphone, click **Record a test**, speak, then click **Stop recording**. Review and copy the result.

The portable ZIP contains the app runtime and setup tools, **not the large models or inference engines**. Internet is needed for the explicit setup step. After setup, recognition and cleanup run offline. Use the published SHA256SUMS.txt to verify release assets. This is an unsigned alpha, not an installer.

For source installation or transferring an already provisioned folder to an offline PC, see [SETUP.md](SETUP.md).

## Dictation controls

- **Push-to-talk:** choose a shortcut, then click **Arm shortcut**. Focus an editor and hold the shortcut to speak; release it to finish. A conflicting shortcut leaves Vowely disarmed. There is no silent remapping.
- **Live preview:** Whisper shows provisional text while you speak. Sentence-ending punctuation must agree across two previews before the sentence is sent to Qwen. There is no required 1.2-second silence gap. Qwen cleans text; it does not decide sentence boundaries.
- **Stop:** recognises the complete recording again using the chosen final quality, reconciles changed sentences, and processes any unfinished tail. This adds final processing time.
- **Models:** choose CPU or NVIDIA CUDA for recognition and cleanup independently. **Free model memory** unloads resident workers. Cancel, Disarm, close-to-tray and Quit also stop them. Reload models before the next live recording.
- **Tray:** closing the window disarms/cancels and leaves the tray icon. Launch again or use the tray to reopen it. Quit exits fully.

## Modes

| Mode | Cleanup behavior |
|---|---|
| Natural | Removes fillers and obvious disfluencies; fixes punctuation and capitalisation while preserving meaning. |
| Developer | Conservative punctuation editing; asks Qwen to preserve identifiers, code, paths and technical terms. It never executes code. |
| Verbatim | Bypasses Qwen and keeps Whisper's recognised text. |

When cleanup is disabled, every mode returns raw recognition. Names and vocabulary are local spelling hints, not guaranteed corrections. Provisional text can change; cleanup may introduce mistakes. Review the original and cleaned panes.

## Insertion and privacy

New installations start disarmed, with auto-insertion disabled and an empty field allowlist. Insertion requires an explicitly approved executable/field identity. Password, sensitive, unknown and changed targets refuse insertion. Cleanup results require review and manual copy. Live previews are never inserted. Completion does not steal focus, and automatic insertion does not use the clipboard.

Live workers listen only on protected `127.0.0.1` endpoints and are owned by the app. They stop on cancellation/unload/exit. Conventional CLI processing and CPU fallback use temporary local files. See [PRIVACY.md](PRIVACY.md) for retention and insertion limits.

## Requirements and status

Windows x64, a microphone supporting 16 kHz mono PCM16, and sufficient RAM/storage for the selected models. Development measurements used a Ryzen 5 3550H, 16 GB RAM and GTX 1650 4 GB. CPU works without CUDA; GPU performance and compatibility depend on the driver/build. See [PERFORMANCE.md](PERFORMANCE.md) for measured public-sample results, not latency promises.

The alpha includes source, tests, setup and packaging scripts, and a pinned asset manifest. Broad accent/noise accuracy scoring, signed distribution, broad target-app compatibility and Android support remain unfinished.

See [ARCHITECTURE.md](ARCHITECTURE.md), [DEVELOPMENT.md](DEVELOPMENT.md), and [THIRD_PARTY.md](THIRD_PARTY.md). The internal Python package remains `localflow` for compatibility; the product and repository are Vowely.
