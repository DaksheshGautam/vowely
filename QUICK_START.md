# Quick start

1. Extract the Windows release ZIP and run **Setup models and engines.ps1** once while online.
2. Open **Start Vowely.vbs** and wait for Ready. The microphone stays off during model loading.
3. Choose your microphone. Click **Record a test**, speak normally, then **Stop recording**. Review and copy.
4. For a global shortcut, choose it, click **Arm shortcut**, focus your editor, hold it to speak, and release to finish. Disarm to change settings.

Live mode uses stable Whisper sentence-ending punctuation, without a fixed silence wait. Qwen cleans recognised sentences. Stop rechecks the complete recording; wait for processing to finish before copying. Verbatim bypasses cleanup; Natural is general editing; Developer preserves technical wording conservatively.

Auto-insertion is disabled by default and needs an explicitly allowed field. Password/sensitive/unknown targets are blocked. Cleanup stays in preview for manual review. See PRIVACY.md before enabling insertion.

If no audio arrives, check the selected microphone, its connection and desktop microphone permission. The app does not switch devices for you. Free model memory, Cancel, Disarm, close-to-tray and Quit unload model context; use Load / reload models before recording again. Closing the window leaves the tray icon; Quit exits. All dictation works offline after explicit setup.
