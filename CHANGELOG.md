# Changelog

Alpha.2–alpha.11 were published retrospectively as source snapshots from their original commits. They do not include Windows installers. Alpha.12 is the current installable prerelease.

## 0.1.0-alpha.12 — installer prerelease

- Per-user Windows setup executable, Start-menu entries, optional desktop shortcut, upgrade guard and uninstaller. No separate Python installation or manual setup script.
- Explicit asynchronous model/engine setup with SHA-256 verification, existing-folder reuse, cancellation/resume, retry and independent NVIDIA options. Whisper Base/Small, Qwen and Silero are included in setup; downloads never start during dictation.
- Separate local application-data directory; existing installed configuration is preserved, with optional import of a portable profile. Uninstall retains local data for reuse.

## 0.1.0-alpha.11 — historical source release

- Configurable hold-to-dictate and optional press-to-start / press-again-to-stop shortcuts, available together in Settings / Dictation, with a keyboard picker and dashboard instructions. Existing hold shortcuts are preserved; toggle starts disabled.
- Function keys, Space, and letters/digits with two modifiers; unsupported/reserved combinations and duplicate bindings are rejected. Windows reservation conflicts release any partially registered pair, with no alternate mapping.
- Hold ends on release of any required key. Toggle ends on its next press or the existing maximum duration. Both use the existing final recognition, cleanup and focus-checked typing. Fast completions wait briefly for stop keys without blocking the UI.

## 0.1.0-alpha.10 — historical source release

- Charcoal/lavender PySide6 desktop with Home, current-session Dictation, Vocabulary, Models, categorized Settings and Help pages; responsive sidebar, keyboard navigation, visible save actions and local error/loading states.
- Revisit-able first-run setup with explicit microphone test, installed-model checks, shortcut validation and real preview dictation. Existing settings and custom paths are retained.
- Model lifecycle operations and diagnostics run outside the Qt thread; shutdown remains cancellable during model preparation. Real processing timings are shown without latency guarantees.
- Expanded tray navigation; original global shortcut, auto-type safeguards, dictionary behavior, icon, floating orb and words-added popup retained. No saved transcript history, telemetry, cloud sync or automatic downloads.

## 0.1.0-alpha.9 — historical source release

- Compare edited drafts on completion, learn multiple corrected words without a typing pause, and show newly added spellings in a nonactivating popup.

## 0.1.0-alpha.8 — historical source release

- Local spelling dictionary and per-request vocabulary hints.

## 0.1.0-alpha.7 — historical source release

- User-supplied lavender V emblem for the window, tray, Windows executable and local shortcut icons.
- Bundled artwork in source installations and portable builds, with seven Windows icon sizes from 16 to 256 pixels and a stable taskbar identity.

## 0.1.0-alpha.6 — historical source release

- Fixed final typing being blocked when one Qwen edit was rejected and the original recognized wording was retained.
- Validated Qwen edits and exact local source fallbacks can be combined and typed once after complete final recognition. Rejected model rewrites never become insertion-ready; a fallback must exactly equal the original wording plus deterministic list layout.
- Retired cleanup warnings are discarded when recognition revises a sentence, so stale failures cannot govern final output.
- Replaced the generic Result in Vowely notice with the actual insertion reason; successful source fallback is reported explicitly.

## 0.1.0-alpha.5 — historical source release

- Starts the shortcut and loads configured live models automatically on launch, running in the tray. No arming, field approval or Run in background step.
- Removed the approval button, field-inspection workflow and persisted allowlist. Legacy configurations migrate without losing model/microphone preferences.
- Focused editable controls use their runtime identity even without an AutomationId. Password/sensitive/read-only/unknown controls and changed focus still refuse insertion.
- Optional Pause/Resume remains in settings and the tray; shortcut conflicts fail clearly without remapping another shortcut. Resume reloads models automatically.

## 0.1.0-alpha.4 — historical source release

- Final validated Qwen output can type once into an approved, still-focused field when automatic insertion is enabled. Drafts are never inserted or replaced; rejected/failed cleanup remains preview-only.
- Nonactivating, click-through circle grows with voice loudness, with quiet-input gating and a completely still silent state; indeterminate loading ring during final recognition/cleanup; brief completion/refusal messages.
- Multiline typing uses Unicode text separators, preserving bullet lines in the native editor check without sending Enter or using the clipboard. Rendering in other target controls varies.
- Run in background and close-to-tray retain the armed shortcut. Tray Disarm and cancel and Quit retain their stop behavior.
- Automatic-typing setup inspects unapproved shortcut fields without recording. Manual recording and WAV replay remain preview-only.
- Added final-result, focus, stale-result, meter, overlay and background lifecycle regressions. Published alpha.1 release assets remain unchanged.

## 0.1.0-alpha.3 — historical source release

- Four or more delimiter commas automatically create a bullet list in Natural/Developer cleanup, without spoken layout commands.
- Numeric separators, quoted text, parenthesised/code commas and written calendar dates do not count toward the threshold.
- Qwen receives preformatted items; a local layout fallback preserves source items if cleanup merges the list back into prose. The original transcript remains available.
- Live cleanup keeps comma-list context together and still waits for stable sentence endings. The published alpha.1 ZIP is unchanged.

## 0.1.0-alpha.2 — historical source release

- Spoken bullet-list, numbered-list, new-paragraph and new-line cues in Natural/Developer cleanup.
- Sequential list markers no longer fail numeric validation; amounts, signs, currencies, dates, times, phone digits and version literals remain protected.
- Formatting requests retain context across live sentence boundaries, and copied output preserves line breaks.
- Added synthetic local-Qwen checks and automated formatting/number-preservation regressions. Existing v0.1.0-alpha.1 release assets are unchanged.

## 0.1.0-alpha.1

First Windows prerelease of Vowely.

- Global explicitly armed push-to-talk and microphone selection.
- Local Whisper Base/Small with optional Silero and independent CPU/CUDA choices for Whisper and Qwen cleanup.
- Live previews with stable Whisper sentence endings, concurrent cleanup and complete-recording recognition after Stop.
- Natural, Developer and Verbatim modes; original transcript remains available for review.
- Protected loopback workers, owned process lifecycle, cancellation and local CPU fallback.
- Guarded final-only cursor insertion with explicit field approval, password/sensitive checks and focus preservation.
- Versioned portable Windows runtime, explicit verified model/engine setup, source setup, tests and packaging tools.

Alpha limitations: unsigned portable build; no bundled weights/engines; setup needs internet once; no general accuracy guarantee; cleanup requires review; broad target-app compatibility and Android remain unfinished.
