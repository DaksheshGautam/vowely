# Quick start

1. Extract the Windows release ZIP and run **Setup models and engines.ps1** once while online.
2. Open **Start Vowely.vbs** and wait for Ready. The microphone stays off during model loading.
3. Choose your microphone. Click **Record a test**, speak normally, then **Stop recording**. Review and copy.
4. For a global shortcut, choose it, click **Arm shortcut**, focus your editor, hold it to speak, and release to finish. Disarm to change settings.

Live mode uses stable Whisper sentence-ending punctuation, without a fixed silence wait. Qwen cleans recognised sentences. Stop rechecks the complete recording; wait for processing to finish before copying. Verbatim bypasses cleanup; Natural is general editing; Developer preserves technical wording conservatively.

Auto-insertion is disabled by default and needs an explicitly allowed field. Enable **Automatically type final results into approved fields**. Arm the shortcut, focus the intended field and press the shortcut once to inspect it. Disarm in Vowely, click **Allow the last inspected field**, then arm again. Password/sensitive/unknown targets remain blocked. See PRIVACY.md for permission scope and insertion limits.

Click **Run in background**, focus the approved field, hold the shortcut to speak and release to finish. A circle grows with microphone volume, then becomes a loading ring while recognition and Qwen finish. The final validated result types once into the original field. Stay focused there until it finishes. Failed or rejected cleanup stays in Vowely for manual copying. Test recordings and WAV replay are always preview-only.

If no audio arrives, check the selected microphone, its connection and desktop microphone permission. The app does not switch devices for you. Free model memory, Cancel, Disarm and Quit unload model context; use Load / reload models before recording again. Closing the window keeps the shortcut and models active in the tray. Use the tray's **Disarm and cancel** to stop listening/processing, or **Quit** to exit. All dictation works offline after explicit setup.
