# Privacy and insertion contract

## Defaults

- No external APIs, telemetry, analytics, automatic downloads, transcript history or external runtime network requests. Live mode uses protected servers on this PC only; see below.
- App starts in the tray, registers its shortcut and loads configured models automatically. Closing settings preserves the shortcut and current operation. The nonactivating indicator shows recording/processing. Pause dictation stops both; Quit releases the shortcut and exits. The microphone opens only while holding the shortcut in an eligible field or after an explicit Record a test action. WAV replay never opens it. Duration is capped, and cancellation invalidates pending results.
- `auto_insert=true`; field approvals and the allowlist have been removed. The clean release configuration uses CPU Whisper Small and CPU Qwen, with selectable Silero and independent GPU choices. The microphone remains closed until a recording action. No microphone fallback to a different device if the configured capture fails.
- No automatic clipboard writes. Copy is a user action. Windows clipboard history and clipboard sync can retain or transmit copied text independently; the app does not toggle those OS settings.

## Automatic field selection

Focus an editable text box and hold the shortcut to dictate. Vowely captures that control's window, process and UIA runtime identity and checks them again before typing the final result. No field approval or AutomationId is required. Legacy allowlist settings are removed during migration. Disable automatic typing in settings if you want preview-only dictation.

Password, sensitive, denied, read-only and unknown controls remain blocked. Deny settings remain configurable:

```json
"deny_processes": ["keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe", "credentialuibroker.exe", "consent.exe", "windowsterminal.exe", "powershell.exe", "pwsh.exe", "cmd.exe"],
"deny_name_fragments": ["password", "passphrase", "secret", "token", "credit card", "cvv", "otp", "pin"]
```

Password fields are always blocked. Default terminals remain denied because dictated input can include newlines. There is no force-paste, automatic focus restoration, elevation request or automatic alternate hotkey. Name-fragment matching is intentionally conservative and can have false positives.

A field needs a known editable UIA control and nonempty runtime ID. Unknown accessibility state refuses insertion. With automatic typing enabled, successful validated final Qwen results may be inserted. Rejected, skipped or unavailable cleanup may use the exact original recognized wording with deterministic comma-list layout. That local fallback can be typed after final recognition completes; rejected Qwen output itself cannot. A successful complete-recording CPU retry follows the same rule. Incomplete and empty/no-speech results remain preview-only. Validation does not guarantee meaning or recognition accuracy. Manual recording/file replay never has an insertion target.

## Limits to assess before daily use

Foreground HWND, PID and focused element identity are checked before Unicode injection and at each batch boundary. Astral characters such as emoji are fenced into separate batches to preserve order in Qt controls. Line breaks use Unicode text separators rather than Enter key presses, avoiding keyboard-based form/chat submission. Display of those separators depends on the target editor; single-line fields and some custom controls may not show multiline formatting. There is no automatic Return-key or clipboard fallback. Focus changes or held keys stop further batches and may leave partial text; there is no retry. App-side focus can still change between check and SendInput. The same control can move its caret, change its contents, navigate documents or repurpose itself while ASR runs. This MVP does not detect these changes. For sensitive documents use preview/manual copy and leave auto insertion off.

UIA password detection depends on what the target app reports. Provider calls run in a disposable helper process; a query taking more than 350 ms returns unknown and terminates that helper. Helper warm-up may also return unknown temporarily. Elevated targets are subject to Windows integrity restrictions; the app does not elevate to bypass them. SendInput may be blocked/partially accepted, and its success count does not prove the target displayed all characters. No automatic retry is performed to avoid duplicates. Existing selections in editable fields may be replaced by typing, just as with normal input.

Capture is held in RAM, but CLI adapters create temporary WAV, JSON and cleanup prompt files in the OS temp directory. Normal success/error/cancel paths remove those files. Crashes, power loss, pagefiles, antivirus, filesystem recovery and process dumps can retain data. There is no secure-erasure or encrypted-memory guarantee. Keep the project/models/temp folders outside cloud-synced storage for stricter local handling and use OS disk encryption if desired. No blanket temp-directory deletion occurs.

Use trusted engine binaries/DLLs and verified model hashes. External executables run with the user's permissions; this app is not an executable sandbox. Offline operation can be independently checked with Windows Firewall and network monitoring after provisioning. No outbound requests are needed for dictation.

## Local correction learning

`learn_corrections=true` watches successful automatic insertions of at most 2,000 characters for 60 seconds. The same focused field identity and password/sensitive/deny/read-only policy are checked before and after every bounded read. The watcher first verifies the exact insertion at a collapsed caret. It uses UIA TextPattern ranges, never whole-field Value or DocumentRange. Up to 24 following characters form an unchanged boundary anchor; each observation allows at most 64 characters of local growth plus that anchor. Unsupported, changed or ambiguous ranges stop learning. Provider queries retain the 350 ms timeout. No general typing log, keyboard hook or clipboard inspection is used.

Insertion text, edits and boundary context stay in RAM during the watch and are discarded on expiry, leaving the field, moving outside the insertion, new recording, Clear, Cancel, Pause or Quit. A single-word replacement must settle for two seconds. Only its corrected spelling is atomically stored in plain local `dictionary.json` next to config.json, with a 128-word cap. No transcript, old spelling, field/application identity, timestamp or audio is stored in that file. A corrected word may still be private. Disabling learning stops new collection; remove existing words through **Learned words** to stop using their hints. Usual folder-sync, dumps and pagefile limitations apply.

Learned spellings are hints to later local Whisper/Qwen requests, not forced replacements or model training. Manual vocabulary takes priority within the 32-hint request limit. Dictionary files are ignored by Git and rejected by release packaging. A corrupt dictionary is preserved and learning disabled rather than silently overwritten.

## Resident live mode

Live workers listen only on 127.0.0.1. A fresh random secret protects Whisper inference URLs and a Bearer token protects Qwen inference. The native benchmark verifies unauthenticated inference is rejected. No proxy, redirects or external provider fallback are used. Audio and prompt request bodies are held in memory and native logs are discarded. Workers may retain inference context in RAM while loaded. Free model memory, Clear, Cancel, Pause and Quit terminate both workers and discard that context. Clear does not securely erase memory or remove text already copied to the Windows clipboard.

Provisional live text is never inserted. Stable completed sentences extracted from agreeing Whisper previews may be sent locally to Qwen while recording; raw unstable/unfinished text is not cleaned until it stabilises or Stop. Stop rechecks the entire audio and invalidates stale cleanup when recognition changes. Stable complete sentences are cleaned in order; previews and unfinished text are held until sentence completion or Stop; after Stop the final result uses the same field restrictions and focus checks as conventional mode. Continuous forced-cut recordings are rechecked in full before final use. CPU fallback remains local and may use temporary files as described above. Local port protection is not a boundary against malicious software already running as the same Windows user.
