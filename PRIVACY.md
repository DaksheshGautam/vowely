# Privacy and insertion contract

## Defaults

- No external APIs, telemetry, analytics, automatic downloads, transcript history or external runtime network requests. Live mode uses protected servers on this PC only; see below.
- App starts disarmed. Closing the window or Run in background hides it to the tray while preserving the armed shortcut and current operation. The nonactivating indicator shows recording/processing. The tray's Disarm and cancel stops both; Quit releases the shortcut and exits. The microphone opens only after an armed shortcut press in an eligible field or an explicit Record a test action. WAV replay never opens it. Duration is capped, and cancellation invalidates pending results.
- `auto_insert=false` and `allow_fields=[]`. The clean release configuration uses CPU Whisper Small and CPU Qwen, with selectable Silero and independent GPU choices. The microphone remains closed until a recording action. No microphone fallback to a different device if the configured capture fails.
- No automatic clipboard writes. Copy is a user action. Windows clipboard history and clipboard sync can retain or transmit copied text independently; the app does not toggle those OS settings.

## Explicit field policy

Start preview-only, focus the intended harmless field and use the shortcut to dictate. The window reports `process.exe|AutomationId`. Check its identity, disarm, click **Allow the last inspected field**, and separately enable automatic insertion. The UI saves the exact field key; it cannot bypass deny rules. You can also edit `allow_fields` in `config.json` while disarmed and restart.

Example only, not a claim about Notepad's actual AutomationId:

```json
"allow_fields": ["notepad.exe|YOUR_VERIFIED_EDITOR_AUTOMATION_ID"],
"deny_processes": ["keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe", "credentialuibroker.exe", "consent.exe", "windowsterminal.exe", "powershell.exe", "pwsh.exe", "cmd.exe"],
"deny_name_fragments": ["password", "passphrase", "secret", "token", "credit card", "cvv", "otp", "pin"]
```

Deny checks always precede allow checks. Password fields are blocked even if allowed. Default terminals are denied because dictated input can include newlines. There is no wildcard approval, force-paste, automatic focus restoration, elevation request or automatic alternate hotkey. Change configuration explicitly to change policy. Name-fragment matching is intentionally conservative and can have false positives.

Allowlist entries cover matching fields in that executable, not a specific document or browser origin. Do not allowlist general browser editors or apps handling credentials on the assumption this is a per-site permission. A field needs a nonempty stable AutomationId and runtime ID. Unknown accessibility state refuses insertion. With automatic typing enabled, successful validated final Qwen results may be inserted. Rejected, skipped or unavailable cleanup, whole-recording error fallback and empty/no-speech results remain preview-only. Validation does not guarantee meaning or recognition accuracy. Manual recording/file replay never has an insertion target. Unapproved shortcut fields are inspected without opening the microphone when automatic typing is enabled.

## Limits to assess before daily use

Foreground HWND, PID and focused element identity are checked before Unicode injection and at each batch boundary. Astral characters such as emoji are fenced into separate batches to preserve order in Qt controls. Line breaks use Unicode text separators rather than Enter key presses, avoiding keyboard-based form/chat submission. Display of those separators depends on the target editor; single-line fields and some custom controls may not show multiline formatting. There is no automatic Return-key or clipboard fallback. Focus changes or held keys stop further batches and may leave partial text; there is no retry. App-side focus can still change between check and SendInput. The same control can move its caret, change its contents, navigate documents or repurpose itself while ASR runs. This MVP does not detect these changes. For sensitive documents use preview/manual copy and leave auto insertion off.

UIA password detection depends on what the target app reports. Provider calls run in a disposable helper process; a query taking more than 350 ms returns unknown and terminates that helper. Helper warm-up may also return unknown temporarily. Elevated targets are subject to Windows integrity restrictions; the app does not elevate to bypass them. SendInput may be blocked/partially accepted, and its success count does not prove the target displayed all characters. No automatic retry is performed to avoid duplicates. Existing selections in allowed fields may be replaced by typing, just as with normal input.

Capture is held in RAM, but CLI adapters create temporary WAV, JSON and cleanup prompt files in the OS temp directory. Normal success/error/cancel paths remove those files. Crashes, power loss, pagefiles, antivirus, filesystem recovery and process dumps can retain data. There is no secure-erasure or encrypted-memory guarantee. Keep the project/models/temp folders outside cloud-synced storage for stricter local handling and use OS disk encryption if desired. No blanket temp-directory deletion occurs.

Use trusted engine binaries/DLLs and verified model hashes. External executables run with the user's permissions; this app is not an executable sandbox. Offline operation can be independently checked with Windows Firewall and network monitoring after provisioning. No outbound requests are needed for dictation.

## Resident live mode

Live workers listen only on 127.0.0.1. A fresh random secret protects Whisper inference URLs and a Bearer token protects Qwen inference. The native benchmark verifies unauthenticated inference is rejected. No proxy, redirects or external provider fallback are used. Audio and prompt request bodies are held in memory and native logs are discarded. Workers may retain inference context in RAM while loaded. Free model memory, Clear, Cancel, Disarm, close-to-tray and Quit terminate both workers and discard that context. Clear does not securely erase memory or remove text already copied to the Windows clipboard.

Provisional live text is never inserted. Stable completed sentences extracted from agreeing Whisper previews may be sent locally to Qwen while recording; raw unstable/unfinished text is not cleaned until it stabilises or Stop. Stop rechecks the entire audio and invalidates stale cleanup when recognition changes. Stable complete sentences are cleaned in order; previews and unfinished text are held until sentence completion or Stop; after Stop the final result uses the same field restrictions and focus checks as conventional mode. Continuous forced-cut recordings are rechecked in full before final use. CPU fallback remains local and may use temporary files as described above. Local port protection is not a boundary against malicious software already running as the same Windows user.
