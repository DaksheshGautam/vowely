# Quick start

1. Extract the Windows release ZIP and run **Setup models and engines.ps1** once while online.
2. Open **Start Vowely.vbs** and wait for Ready. The microphone stays off during model loading.
3. Choose your microphone. Click **Record a test**, speak normally, then **Stop recording**. Review and copy.
4. For direct typing, focus a text box, hold **Ctrl+Alt+F9** to speak, and release to finish. The shortcut starts automatically; no approval or background setup is needed. Use Pause in settings or the tray only when you want to stop dictation or change settings.

Live mode uses stable Whisper sentence-ending punctuation, without a fixed silence wait. Qwen cleans recognised sentences. Stop rechecks the complete recording; wait for processing to finish before copying. Verbatim bypasses cleanup; Natural is general editing; Developer preserves technical wording conservatively.

Automatic final typing is enabled by default. Password/sensitive/unknown targets remain blocked, and moving to another field prevents insertion. See PRIVACY.md for insertion limits.

The app starts in the tray. Focus a text box, hold the shortcut to speak and release to finish. A circle grows with microphone volume, then becomes a loading ring while recognition and Qwen finish. The final result types once into the original field. Stay focused there until it finishes. If cleanup fails or is rejected, unchanged recognized words are used for those portions; the indicator reports the fallback. Test recordings and WAV replay are always preview-only.

If no audio arrives, check the selected microphone, its connection and desktop microphone permission. The app does not switch devices for you. Free model memory, Cancel, Pause and Quit unload model context; Resume reloads models. Closing the window keeps the shortcut and models active in the tray. Use the tray's **Pause dictation** to stop listening/processing, or **Quit** to exit. All dictation works offline after explicit setup.
