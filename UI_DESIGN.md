# Desktop interface and feature inventory

The alpha.9 engine is retained behind a new PySide6 presentation layer. The
reference artwork guides the charcoal/lavender/peach palette, rounded surfaces,
brand placement and hierarchy. It does not introduce history, downloads, cloud
features, extra models, startup registration or automatic updates.

| Destination | Existing controls and operations |
|---|---|
| Home | State, shortcut, selected mode/model/language, microphone, latest in-memory result, pause/resume, navigation to the editor |
| Dictation | Editable final/current provisional result, original recognition, explicit copy, clear and discard model context, cancel, recording meter |
| Vocabulary | Manual names/phrases, learned dictionary, remove selected words, correction-learning switch and local status |
| Models & performance | Whisper Base/Small, independent ASR/Qwen CPU/CUDA choices, beam search, cleanup and live switches, async model load/unload, installed assets, real resident backend status |
| Settings / Audio | Deduplicated microphones, advanced audio inputs, refresh, local microphone test, optional Silero VAD |
| Settings / Dictation | Natural/Developer/Verbatim, language, hotkey, auto-type, live mode explanation and sample shortcut use |
| Settings / Performance | Threads, maximum recording duration, inference timeout; all existing engine/file paths remain preserved |
| Settings / Privacy | Automatic typing policy explanation, editable process/name denylists, local retention and clipboard contract |
| Help & diagnostics | Explicit microphone test, manual preview recording, local WAV replay, async file/dependency checks, setup steps, version and offline troubleshooting |
| Onboarding | Welcome, real microphone level test, async model presence checks, shortcut validation, real sample dictation through the existing pipeline; explicit skip/revisit |
| System tray | Open Home/editor/vocabulary/models/settings/help, pause/resume, cancel, free memory, quit |
| Floating windows | Existing no-focus volume orb/loading ring and words-added popup, unchanged |

Configuration is loaded through the existing Config class and edited by cloning
the current configuration. Existing values, vocabulary and model paths survive
migration. First-run completion is separate local UI state, not a transcript
database. Existing installations bypass onboarding; setup remains revisitable.

Model startup, shutdown and asset checks must not wait on the Qt thread. Live
ASR/Qwen jobs remain in their existing workers. Explicit microphone diagnostics
use the existing Recorder in a worker, retain only level metadata, and discard
audio. The main window may close to the tray without pausing global dictation.

All pages scroll, the sidebar collapses at narrow widths, Tab focus is visible,
and Alt+1 through Alt+6 navigate pages. The current result stays only in RAM.
