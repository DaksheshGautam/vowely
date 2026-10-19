# Whisper decides when a sentence is ready

Live mode no longer uses a 1.2-second silence timer. Whisper recognises the growing recording at its normal preview cadence (about every 2.5 seconds when processing keeps up). Sentence-ending punctuation must agree in two consecutive Whisper snapshots before that sentence goes to Qwen for cleanup. Qwen does not classify sentence boundaries and receives no boundary-check prompts.

You can continue speaking without pausing for a fixed duration. Unfinished text stays visible and buffered. A completed sentence can be cleaned while Whisper recognises the next one. Stable punctuation is still an approximation of sentence completion: Whisper can punctuate incorrectly, and this cannot guarantee that the speaker has finished a thought. Waiting for two snapshots reduces transient preview mistakes but adds processing delay; this is not instantaneous endpoint detection.

Stop always triggers thorough recognition of the complete recording. The final result can replace provisional sentences and their cleanup. Changed sentences invalidate pending/in-flight cleanup results; unchanged cleaned sentences are reused. The unpunctuated final tail is cleaned after Stop. Cancellation discards pending text, stops model workers and prevents late results from appearing. Final-only insertion and the existing field restrictions remain unchanged.

## How to use

The installed option is **Live preview + Whisper decides sentence endings**. Open the desktop Vowely shortcut, wait for the models to be Ready, record and speak normally. There is no required 1.2-second pause. Press Stop to finalise the recording and review the result. Your selected mode, decoding quality, microphone and CPU/GPU choices are preserved.

## Validation

63 automated tests pass, covering two-snapshot agreement, no silence endpoint, incomplete text, duplicate suppression, changing recognition, stale in-flight cleanup, full-recording final recognition, concurrent processing, quiet/silent input, cancellation, fallback, process ownership and insertion protections.

The native GPU check is scripts/test_whisper_endpoints.py. It uses only the bundled public speech clip twice with 0.1 seconds added between clips; it opens no microphone and changes no application settings. It verifies that silence endpoints are disabled, live cleanup follows agreeing Whisper sentence endings, and Stop requests one complete-audio final recognition. Reports contain timestamps/counts/hashes, never transcript text. See PERFORMANCE.md for measured outcomes. Local diagnostic reports are intentionally excluded from the repository. These tests do not establish accuracy for personal speech or all accents/noise conditions.

Native GPU results: both CUDA workers confirmed; 22.1 seconds of public audio; eight preview requests; live cleanup first started at 12.06 seconds on a sentence whose punctuation agreed in the previous two Whisper snapshots. There was no silence endpoint. Stop performed exactly one complete-audio recognition, and its 44-word raw transcript matched the reference. Final processing took 6485 ms in this run, including final recognition and pending cleanup. ASR/cleanup overlap occurred, no CPU fallback was used, and workers stopped afterward. This is a functional public-clip test, not a promise of latency or personal-speech accuracy. The full final-audio check can increase the wait after Stop.
