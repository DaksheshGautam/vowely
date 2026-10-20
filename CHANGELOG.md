# Changelog

## 0.1.0-alpha.5 — unreleased

- Starts the shortcut and loads configured live models automatically on launch, running in the tray. No arming, field approval or Run in background step.
- Removed the approval button, field-inspection workflow and persisted allowlist. Legacy configurations migrate without losing model/microphone preferences.
- Focused editable controls use their runtime identity even without an AutomationId. Password/sensitive/read-only/unknown controls and changed focus still refuse insertion.
- Optional Pause/Resume remains in settings and the tray; shortcut conflicts fail clearly without remapping another shortcut. Resume reloads models automatically.

## 0.1.0-alpha.4 — unreleased

- Final validated Qwen output can type once into an approved, still-focused field when automatic insertion is enabled. Drafts are never inserted or replaced; rejected/failed cleanup remains preview-only.
- Nonactivating, click-through circle grows with voice loudness, with quiet-input gating and a completely still silent state; indeterminate loading ring during final recognition/cleanup; brief completion/refusal messages.
- Multiline typing uses Unicode text separators, preserving bullet lines in the native editor check without sending Enter or using the clipboard. Rendering in other target controls varies.
- Run in background and close-to-tray retain the armed shortcut. Tray Disarm and cancel and Quit retain their stop behavior.
- Automatic-typing setup inspects unapproved shortcut fields without recording. Manual recording and WAV replay remain preview-only.
- Added final-result, focus, stale-result, meter, overlay and background lifecycle regressions. Published alpha.1 release assets remain unchanged.

## 0.1.0-alpha.3 — unreleased

- Four or more delimiter commas automatically create a bullet list in Natural/Developer cleanup, without spoken layout commands.
- Numeric separators, quoted text, parenthesised/code commas and written calendar dates do not count toward the threshold.
- Qwen receives preformatted items; a local layout fallback preserves source items if cleanup merges the list back into prose. The original transcript remains available.
- Live cleanup keeps comma-list context together and still waits for stable sentence endings. The published alpha.1 ZIP is unchanged.

## 0.1.0-alpha.2 — unreleased

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
