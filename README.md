# Vowely

**v0.1.0-alpha.1 — Windows prerelease**

The main branch also contains **0.1.0-alpha.4 development changes** for final-result typing, a voice-reactive indicator, automatic comma lists and spoken formatting. Those changes are not included in the published alpha.1 ZIP.

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
- **Background:** arm the shortcut, then click **Run in background** or close the window to keep Vowely in the tray. The shortcut remains armed. Use the tray's **Disarm and cancel** to stop it, or **Quit** to exit. Launch again or use the tray to reopen the window.
- **Indicator:** holding the shortcut shows a click-through circle that grows with voice loudness. Quiet input is gated visually; the circle settles to a small, completely still state during silence. This lightweight level gate does not change recorded audio or provide semantic speech detection. Releasing the shortcut changes the circle to a loading ring during final recognition/cleanup. It reports completion or a preview-only result without taking keyboard focus. The ring is an activity indicator, not a percentage estimate.

## Type the final result into another app (alpha.4 development)

Enable **Automatically type final results into approved fields** and Qwen cleanup. Arm the shortcut, click your intended text box and press the shortcut once. A new field is inspected without opening the microphone. Return to Vowely, disarm, click **Allow the last inspected field**, then arm again. Approval is for the executable and field ID; password/sensitive/unknown controls remain blocked.

Click **Run in background**, focus that field, hold your shortcut while speaking, then release it. Stay in the same field while the loading ring runs. Vowely types the final validated Qwen result once, including list line breaks. Provisional text is never typed or replaced. No text is sent until the final result is ready, and neither insertion nor the indicator activates the settings window.

Changed focus, held keys, rejected/unavailable cleanup, cancellation, unknown fields and model failures keep the result in Vowely for manual copying. Manual recording and WAV tests remain preview-only. Automatic typing can replace selected text just like ordinary typing; cleanup can still make mistakes even when validation passes.

## Modes

| Mode | Cleanup behavior |
|---|---|
| Natural | Removes fillers and obvious disfluencies; fixes punctuation and capitalisation while preserving meaning. |
| Developer | Conservative punctuation editing; asks Qwen to preserve identifiers, code, paths and technical terms. It never executes code. |
| Verbatim | Bypasses Qwen and keeps Whisper's recognised text. |

When cleanup is disabled, every mode returns raw recognition. Names and vocabulary are local spelling hints, not guaranteed corrections. Provisional text can change; cleanup may introduce mistakes. Review the original and cleaned panes.

### Automatic lists and spoken formatting (alpha.3 development)

With cleanup enabled in Natural or Developer mode, **four or more delimiter commas** automatically produce bullets. For example, `milk, bread, eggs, rice, apples` becomes five bullet lines. Three commas keep prose. Commas inside numeric literals such as ₹5,000, quotes, code/parentheses and written dates such as October 20, 2026 do not count. This is a simple layout heuristic and can also turn comma-heavy prose into a list. It uses Whisper's recognised punctuation, not spoken words such as “comma”.

Qwen receives the separated items together. If it returns prose, merges item boundaries, fails or changes protected numbers, a local layout fallback retains the original items as bullets. Review both panes, since recognition and cleanup can still be inaccurate. Verbatim and disabled cleanup bypass this feature.

With cleanup enabled in Natural or Developer mode, say **“Make a bullet list. First point buy milk. Next point buy bread.”** for a two-line bullet list, or **“Make a numbered list…”** for `1.`, `2.` items. Say **“new paragraph”** for a blank line or **“new line”** for a line break within the current recording. Verbatim preserves the recognised words and bypasses these changes.

Formatting requests keep sentence context together, and Stop includes any unfinished tail. List indices are treated separately from content numbers: sequential structural markers are allowed, while changed numeric literals are rejected and the original text is preserved. Cleanup is still approximate and needs review. This does not validate every possible change of meaning or number words spelled out as text.

## Insertion and privacy

New installations start disarmed, with auto-insertion disabled and an empty field allowlist. Insertion requires an explicitly approved executable/field identity. Password, sensitive, unknown and changed targets refuse insertion. With automatic typing enabled, successfully validated final cleanup can be inserted; rejected or unavailable cleanup remains preview-only. Live previews are never inserted. Completion does not steal focus, and automatic insertion does not use the clipboard.

Live workers listen only on protected `127.0.0.1` endpoints and are owned by the app. They stop on cancellation/unload/exit. Conventional CLI processing and CPU fallback use temporary local files. See [PRIVACY.md](PRIVACY.md) for retention and insertion limits.

## Requirements and status

Windows x64, a microphone supporting 16 kHz mono PCM16, and sufficient RAM/storage for the selected models. Development measurements used a Ryzen 5 3550H, 16 GB RAM and GTX 1650 4 GB. CPU works without CUDA; GPU performance and compatibility depend on the driver/build. See [PERFORMANCE.md](PERFORMANCE.md) for measured public-sample results, not latency promises.

The alpha includes source, tests, setup and packaging scripts, and a pinned asset manifest. Broad accent/noise accuracy scoring, signed distribution, broad target-app compatibility and Android support remain unfinished.

See [ARCHITECTURE.md](ARCHITECTURE.md), [DEVELOPMENT.md](DEVELOPMENT.md), and [THIRD_PARTY.md](THIRD_PARTY.md). The internal Python package remains `localflow` for compatibility; the product and repository are Vowely.
