# Development

Vowely is a Windows-first offline dictation application. The Python package remains localflow for compatibility. Version identifiers live in src/localflow/version.py; the packaging script embeds the prerelease version in the Windows executable. Android is future work.

Run the Windows unit suite after changes:

UI_DESIGN.md records the desktop inventory and navigation mapping. tests/test_desktop.py covers exact configuration preservation (including custom paths and intermediate beam sizes), setup progression, shared RAM-only results, keyboard/compact navigation, vocabulary removal, no-network asset checks, cancellation and model lifecycle work off the Qt thread. Worker waits in tests are synchronization only; production uses asynchronous completion. Package smoke checks verify all six pages, four setup steps and bundled icon/theme assets.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Tests exercise mocked capture/engines, sentence stability, full-audio finalisation, stale cleanup rejection, cancellation, process ownership, CPU fallback, focus/field policy and bounded accessibility inspection. They do not establish accuracy for every voice, microphone or target application. Native insertion tests type only into their disposable fixture; never redirect those to another app.

Opt-in correction learning check in a disposable native editor (click its Run button):

```powershell
.venv/Scripts/python.exe scripts/check_correction_learning.py
.venv/Scripts/python.exe scripts/check_correction_learning.py --fast
.venv/Scripts/python.exe scripts/check_correction_learning.py --leave
```

This uses real Unicode insertion and Windows UIA events/text ranges with synthetic words and an isolated temporary dictionary. It opens no microphone, uses no clipboard and never accesses user documents. It checks multiword corrections, edits outside the dictated span, appended prose, completion by clearing or focus change, immediate 15 ms submission, popup contents/focus, persistence and next-request vocabulary. Reports in ignored benchmarks/ contain only the fixture. Unit tests also cover password/changed/denied targets, provider timeouts, draft expiry, local persistence and disabled learning. Never commit personal dictionary.json or dictionary.tmp; release packaging rejects them.

Opt-in public-audio GPU validation after provisioning:

```powershell
.venv/Scripts/python.exe scripts/test_whisper_endpoints.py
```

This opens no microphone and writes metadata rather than transcripts. The pinned public WAV is obtained during explicit provisioning. Never commit private recordings, transcripts, vocabulary, local device lists, paths, settings, logs, credentials, engine binaries or model weights. The repository intentionally omits local benchmark reports and historical troubleshooting notes.

Preserve these boundaries: no external inference/telemetry or automatic runtime downloads; no surprise hotkey remapping or model/device switching; changed/unknown/sensitive focus refuses insertion; no focus stealing or automatic clipboard use; cancellation invalidates jobs and stops owned workers. Automatic shortcut registration and final typing are intentional defaults, with no field allowlist; users may pause dictation or disable automatic typing. Qwen has no tools and never executes dictated instructions. Keep uncertainty about semantic cleanup and same-field caret changes explicit.

Provisioning is an explicit separate setup mode, including in the packaged app. Tests must verify ordinary launch cannot enter it accidentally. Keep SHA-256/revisions pinned and preserve differing existing assets. New packaging must pass the startup smoke test and be checked from the actual ZIP before publication. Release assets include checksums and required available third-party notices; large models/engines are provisioned separately.

Shortcut tests exercise atomic dual registration/rollback, distinct native message IDs, full-combination release, toggle stop, disabled/conflicting settings, maximum duration, unchanged live finalization, focus policy, keyboard picking, migration and asynchronous key-release deferral. The opt-in native shortcut fixture uses synthetic PCM and fake recognition to check real global notifications and typing in its disposable editor; it opens no microphone and does not measure recognition accuracy.

Run `.venv/Scripts/python.exe scripts/check_shortcuts.py --allow-test-window --report benchmarks/native-shortcuts.json`, focus its disposable editor, press Ctrl+Alt+Shift+F8 to start and again to stop, then hold/release Ctrl+Alt+Shift+F7. The report must show both synthetic texts inserted and toggle remaining active after key release. Finish test closes the isolated fixture.
