# Changelog

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
