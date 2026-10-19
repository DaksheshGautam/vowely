# Development

Vowely is a Windows-first offline dictation application. The Python package remains localflow for compatibility. Version identifiers live in src/localflow/version.py; the packaging script embeds the prerelease version in the Windows executable. Android is future work.

Run the Windows unit suite after changes:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Tests exercise mocked capture/engines, sentence stability, full-audio finalisation, stale cleanup rejection, cancellation, process ownership, CPU fallback, focus/field policy and bounded accessibility inspection. They do not establish accuracy for every voice, microphone or target application. Native insertion tests type only into their disposable fixture; never redirect those to another app.

Opt-in public-audio GPU validation after provisioning:

```powershell
.venv/Scripts/python.exe scripts/test_whisper_endpoints.py
```

This opens no microphone and writes metadata rather than transcripts. The pinned public WAV is obtained during explicit provisioning. Never commit private recordings, transcripts, vocabulary, local device lists, paths, settings, logs, credentials, engine binaries or model weights. The repository intentionally omits local benchmark reports and historical troubleshooting notes.

Preserve these boundaries: no external inference/telemetry or automatic runtime downloads; no surprise hotkey remapping, model/device switching or auto-insertion; deny rules override allowlists; changed/unknown/sensitive focus refuses insertion; no focus stealing or automatic clipboard use; cancellation invalidates jobs and stops owned workers. Qwen has no tools and never executes dictated instructions. Keep uncertainty about semantic cleanup and same-field caret changes explicit.

Provisioning is an explicit separate setup mode, including in the packaged app. Tests must verify ordinary launch cannot enter it accidentally. Keep SHA-256/revisions pinned and preserve differing existing assets. New packaging must pass the startup smoke test and be checked from the actual ZIP before publication. Release assets include checksums and required available third-party notices; large models/engines are provisioned separately.
