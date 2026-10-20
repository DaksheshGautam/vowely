# Vowely

**v0.1.0-alpha.1 — Windows prerelease**

The main branch also contains **0.1.0-alpha.10 development changes** for a redesigned dark desktop, guided first-run setup, draft-based spelling learning, final-result typing and a voice-reactive indicator. These changes are not included in the published alpha.1 ZIP.

Offline personal dictation with global push-to-talk, live speech recognition, sentence-based text cleanup, and guarded cursor insertion. Built with Python, PySide6, whisper.cpp, llama.cpp, Whisper Base/Small, optional Silero VAD, and Qwen3-1.7B Q4_K_M.

Audio and transcripts stay on your computer. No external inference APIs, telemetry, account, transcript history, or automatic downloads during dictation.

## Download and start

1. Download **vowely-0.1.0-alpha.1-windows-x64.zip** from the [prerelease](https://github.com/DaksheshGautam/vowely/releases/tag/v0.1.0-alpha.1), and extract the complete ZIP to a writable folder.
2. Run **Setup models and engines.ps1** in that folder. This is an explicit, online, one-time download of about 3.3 GB of pinned assets. Allow at least 10 GB of free disk space. The Windows package includes its Python runtime; a separate Python installation is not required.
3. Double-click **Start Vowely.vbs**. Wait for the models to be ready. Choose your microphone, click **Record a test**, speak, then click **Stop recording**. Review and copy the result.

The portable ZIP contains the app runtime and setup tools, **not the large models or inference engines**. Internet is needed for the explicit setup step. After setup, recognition and cleanup run offline. Use the published SHA256SUMS.txt to verify release assets. This is an unsigned alpha, not an installer.

For source installation or transferring an already provisioned folder to an offline PC, see [SETUP.md](SETUP.md).

## Dictation controls

### Desktop navigation (alpha.10 development)

Home shows the current state, shortcut, mode/model/language and latest transcription. **Dictation** holds the editable current result and original recognition; nothing is saved as transcript history. **Vocabulary** manages manual hints and searchable learned words. **Models** contains recognition/cleanup backends, live mode, decoding quality, load/unload, real last-dictation timings and asynchronous local file/dependency checks. **Settings** groups audio, dictation, performance limits and privacy denylists. **Help** holds preview recording/WAV tests, diagnostics, setup guidance and access to the local application folder.

Use Alt+1 through Alt+6 to navigate. Pages scroll, the sidebar collapses in narrow windows, and settings pages keep a visible Save bar. Pause before editing configuration; Save changes preserves existing model paths and other configuration values. Resume applies the chosen configuration and reloads live models when needed. Changing the Live checkbox alone does not start model operations; use Save, Load or Resume. Model startup/shutdown and diagnostics run in workers.

New installations open a four-step setup flow: welcome, real three-second microphone test, local model checks, then shortcut selection and a real sample dictation. Microphone tests discard captured audio. Missing models show actionable local setup guidance; no download starts automatically. Setup can be skipped or revisited in Help. Existing installations keep their configuration and go directly to normal startup. Only setup-completion metadata is stored in ui-state.json. Closing the window preserves dictation in the tray; its menu links to every page and includes pause, cancel, free memory and quit.

- **Push-to-talk:** launch Vowely and wait for Ready. It registers your shortcut and loads models automatically. Focus an editor and hold the shortcut to speak; release to finish. No field approval is needed. A conflicting shortcut shows an error; there is no silent remapping.
- **Live preview:** Whisper shows provisional text while you speak. Sentence-ending punctuation must agree across two previews before the sentence is sent to Qwen. There is no required 1.2-second silence gap. Qwen cleans text; it does not decide sentence boundaries.
- **Stop:** recognises the complete recording again using the chosen final quality, reconciles changed sentences, and processes any unfinished tail. This adds final processing time.
- **Models:** choose CPU or NVIDIA CUDA for recognition and cleanup independently. **Free model memory**, Cancel, Pause and Quit stop resident workers. Resume reloads models automatically. Closing settings keeps the shortcut and models active.
- **Background:** Vowely starts in the tray automatically. No background button is needed. Use the tray's **Show Vowely** for settings, **Pause dictation** to stop the shortcut and current work, or **Quit** to exit. Resume automatically reloads models. Closing settings keeps dictation active.
- **Indicator:** holding the shortcut shows a click-through circle that grows with voice loudness. Quiet input is gated visually; the circle settles to a small, completely still state during silence. This lightweight level gate does not change recorded audio or provide semantic speech detection. Releasing the shortcut changes the circle to a loading ring during final recognition/cleanup. It reports completion or a preview-only result without taking keyboard focus. The ring is an activity indicator, not a percentage estimate.

## Type the final result into another app (alpha.5 development)

Automatic final typing is enabled by default. Open Vowely, wait for model loading, click the intended text box and hold your shortcut while speaking. No arming or field approval is needed. Password/sensitive/unknown controls remain blocked.

Release the shortcut and stay in the same field while the loading ring runs. Vowely types the final validated Qwen result once, including list line breaks. Provisional text is never typed or replaced. No text is sent until the final result is ready, and neither insertion nor the indicator activates the settings window.

If cleanup is rejected or unavailable, the unchanged recognized wording is used for those portions and final typing can continue; the indicator reports the source fallback. Rejected Qwen rewrites are never typed. Changed focus, held keys, cancellation, unknown fields and incomplete final recognition still prevent typing and show a specific reason. Manual recording and WAV tests remain preview-only. Automatic typing can replace selected text just like ordinary typing; cleanup can still make mistakes even when validation passes.

## Learn from spelling corrections (alpha.9 development)

After Vowely types a result, edit any number of words in that box and continue typing normally. When the box clears (as commonly happens after Send), you leave the field, or you start another dictation, Vowely compares the latest available draft with its original text. **No typing pause is required.** A small, click-through popup lists newly added spellings without taking focus. It dismisses after eight seconds. Only corrected spellings are saved locally and supplied to future Whisper/Qwen requests as hints. Models are not retrained and hints cannot guarantee recognition.

Learning is on by default. **Learned words** in settings lets you inspect/remove entries. Pause dictation and uncheck **Learn spelling corrections after dictation** to stop new learning. Existing hints remain until removed. Manual vocabulary has priority within the 32-hint request limit; the newest learned words fill remaining slots. At most 128 words are retained.

The watcher uses the edited draft, without scanning sent-message history or identifying particular Send buttons. It can learn multiple replacements, including similar split/merged spellings. Pure additions/deletions, numbers, case/punctuation-only edits and address/path components are ignored. Changes outside the originally dictated portion are excluded. Existing/newly typed context is used only in RAM for alignment. Clear, Cancel, Pause, Quit, expiry or accessibility/security failures discard the watch. Record-a-test/WAV previews do not learn.

Windows has no universal submission event. Compatible UI Automation TextPattern support and a complete field of at most 2,000 characters are required. UIA text/value events retain edits between polls; providers that omit/coalesce events can miss edits made immediately before clearing/leaving. The fallback checks every 150 ms. Unsupported or oversized fields skip learning without blocking dictation. Watches expire after ten minutes. Leaving or clearing an unsent draft also finalizes spelling hints; this is edit completion detection, not proof that a server received a message. See [PRIVACY.md](PRIVACY.md).

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

New installations activate the shortcut and automatic final typing on launch, with the microphone closed until you hold the shortcut. There is no field allowlist. Insertion requires a known editable focused control with a runtime identity. Password, sensitive, unknown and changed targets refuse insertion. Validated cleanup or an exact local fallback to source words can be inserted after recognition completes. Live previews are never inserted. Completion does not steal focus, and automatic insertion does not use the clipboard.

Live workers listen only on protected `127.0.0.1` endpoints and are owned by the app. They stop on cancellation/unload/exit. Conventional CLI processing and CPU fallback use temporary local files. See [PRIVACY.md](PRIVACY.md) for retention and insertion limits.

## Requirements and status

Windows x64, a microphone supporting 16 kHz mono PCM16, and sufficient RAM/storage for the selected models. Development measurements used a Ryzen 5 3550H, 16 GB RAM and GTX 1650 4 GB. CPU works without CUDA; GPU performance and compatibility depend on the driver/build. See [PERFORMANCE.md](PERFORMANCE.md) for measured public-sample results, not latency promises.

The alpha includes source, tests, setup and packaging scripts, and a pinned asset manifest. Broad accent/noise accuracy scoring, signed distribution, broad target-app compatibility and Android support remain unfinished.

See [ARCHITECTURE.md](ARCHITECTURE.md), [DEVELOPMENT.md](DEVELOPMENT.md), and [THIRD_PARTY.md](THIRD_PARTY.md). The internal Python package remains `localflow` for compatibility; the product and repository are Vowely.
