# Architecture

## Components

| Module | Responsibility |
|---|---|
| app.py | Qt tray/window, explicit hotkey and microphone actions, model preparation, provisional preview and final-only insertion |
| audio.py | Bounded PCM16/16 kHz mono capture; incremental locked reads plus complete recording for recheck/fallback |
| streaming.py | Energy-based phrase boundaries, 200 ms pre-roll/padding, no silence endpoint in live mode, coalesced 2.5 s previews, sentence buffering, ordered final queues and concurrent ASR/cleanup threads |
| resident.py | Loopback-only authenticated native worker lifecycle, in-memory WAV transport, bounded JSON, request cancellation and Windows Job ownership |
| engines.py | Existing CLI recognition/cleanup, conservative output validation and whole-recording CPU fallback |
| windows.py / probe.py / policy.py | Explicit shortcut reservation, bounded UIA inspection, deny/allow rules, target identity checks and Unicode insertion without automatic clipboard use |
| config.py | Validated settings and atomic local save |

## Live data flow

Model preparation happens with the microphone closed. Whisper Small and Qwen Q4_K_M can remain resident on the GTX 1650 between recordings. CPU choices and startup GPU-to-CPU fallback remain available. Changing worker-affecting settings invalidates the resident profile and causes a reload before recording.

Capture feeds a phrase buffer while retaining the bounded complete recording. Preview requests are replaceable; committed phrases are never silently dropped. The ASR thread prioritises final phrases and the cleanup thread processes their recognised text in order. Qwen receives sentences whose terminal punctuation agrees across two consecutive cumulative Whisper previews. Unfinished/unstable previews never enter cleanup. There is no Qwen boundary classifier. SentenceBuffer accumulates incomplete text across ASR endpoints, protects common abbreviations/initials/decimal dots and uses recognised terminal punctuation as an approximate completion signal. Qwen may clean a completed sentence while Whisper recognises the next one. Stop flushes an unpunctuated tail exactly once. Neither thread inserts text. Numbered sessions and monotonically numbered preview updates reject stale or out-of-order UI events.

Live capture never commits an ASR segment because of silence. Complete growing-audio snapshots are coalesced at the preview cadence. Stable sentence boundaries in their text gate Qwen. Every Stop transcribes the complete audio, reconciles revised sentences, invalidates stale cleanup by revision and cleans the remaining final tail. The audio sentence buffer spans up to 120 seconds, bounded by the configured 60/120-second capture limit. An emergency forced cut retains 400 ms overlap and marks the recording for whole-audio re-recognition after Stop; those partial cuts are never sent to Qwen. The complete recheck replaces provisional overlap before final sentence cleanup. Quiet audio that never crossed the phrase threshold gets a whole-audio check when its RMS is usable. Digital silence skips inference. If live ASR fails, the complete recording is processed locally on CPU after Stop and requires review. Cleanup failures preserve original phrases. Queue pressure triggers a whole-audio fallback rather than losing committed audio.

After Stop, capture ends first; pending phrases and cleanup finish; only then can the existing field policy permit final insertion. Cleanup always requires review. Focus is never restored automatically. Same-control caret moves are not detected, and Windows provides no atomic focus-check-and-insert operation. Unknown, changed, sensitive or password fields refuse insertion.

## Process and privacy boundary

Native workers bind IPv4 loopback only. Whisper uses a random 192-bit URL prefix covering its routes; Qwen uses a random Bearer token, no web UI and offline mode. Unauthenticated inference is tested to fail. HTTPConnection uses fixed loopback destinations with no proxy or redirect support. Responses are capped at 2 MB; audio is capped by configured capture duration. Native stdout/stderr are drained without retaining transcripts or prompts. Whisper reads in-memory uploaded WAV bytes; FFmpeg conversion is disabled and public directories are empty private temp folders.

Workers belong to a Windows Job with KILL_ON_JOB_CLOSE. Unload, Clear, Cancel, Disarm, close-to-tray and Quit interrupt connections, kill workers and discard model context. A late process assignment after cancellation is rejected and killed. This is process lifecycle ownership, not an executable sandbox. Same-user malicious processes, OS pagefiles/dumps and physical memory recovery are outside the privacy guarantee.

Conventional mode retains the original CLI path: each utterance loads its models and uses temporary WAV/JSON/prompt files removed on normal success/error/cancel. A crash may leave such files. Models and binaries are explicitly provisioned with pinned hashes; application runtime makes no external requests.

## Validation and limits

See PERFORMANCE.md for measured public-sample results and their limits. tests cover phrase ordering, overlapping work, forced-cut replacement, quiet/silent input, final tail delivery, failure fallback, cancellation, stale UI events, process ownership and the existing insertion policy. The native public-audio test verifies both CUDA workers, protected endpoints, reuse and shutdown. Broad microphone/accent/noise scoring, code signing and Android remain separate work.
