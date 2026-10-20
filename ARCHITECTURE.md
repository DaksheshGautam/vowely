# Architecture

## Components

| Module | Responsibility |
|---|---|
| app.py | Qt tray/window, explicit hotkey and microphone actions, model preparation, provisional preview and final-only insertion |
| overlay.py | Nonactivating, click-through volume circle and indeterminate processing ring; transient completion/refusal feedback |
| audio.py | Bounded PCM16/16 kHz mono capture; incremental locked reads plus complete recording for recheck/fallback |
| streaming.py | Energy-based phrase boundaries, 200 ms pre-roll/padding, no silence endpoint in live mode, coalesced 2.5 s previews, sentence buffering, ordered final queues and concurrent ASR/cleanup threads |
| resident.py | Loopback-only authenticated native worker lifecycle, in-memory WAV transport, bounded JSON, request cancellation and Windows Job ownership |
| engines.py | Existing CLI recognition/cleanup, conservative output validation and whole-recording CPU fallback |
| windows.py / probe.py / policy.py | Explicit shortcut reservation, bounded UIA inspection, deny/allow rules, target identity checks and Unicode insertion without automatic clipboard use |
| config.py | Validated settings and atomic local save |
| learning.py | Debounced word corrections, in-memory watch, bounded local dictionary and per-request vocabulary |

## Live data flow

Model preparation happens with the microphone closed. Whisper Small and Qwen Q4_K_M can remain resident on the GTX 1650 between recordings. CPU choices and startup GPU-to-CPU fallback remain available. Changing worker-affecting settings invalidates the resident profile and causes a reload before recording.

Capture feeds a phrase buffer while retaining the bounded complete recording. Preview requests are replaceable; committed phrases are never silently dropped. The ASR thread prioritises final phrases and the cleanup thread processes their recognised text in order. Qwen receives sentences whose terminal punctuation agrees across two consecutive cumulative Whisper previews. Unfinished/unstable previews never enter cleanup. There is no Qwen boundary classifier. SentenceBuffer accumulates incomplete text across ASR endpoints, protects common abbreviations/initials/decimal dots and uses recognised terminal punctuation as an approximate completion signal. Qwen may clean a completed sentence while Whisper recognises the next one. Stop flushes an unpunctuated tail exactly once. Neither thread inserts text. Numbered sessions and monotonically numbered preview updates reject stale or out-of-order UI events.

Live capture never commits an ASR segment because of silence. Complete growing-audio snapshots are coalesced at the preview cadence. Stable sentence boundaries in their text gate Qwen. Every Stop transcribes the complete audio, reconciles revised sentences, invalidates stale cleanup by revision and cleans the remaining final tail. The audio sentence buffer spans up to 120 seconds, bounded by the configured 60/120-second capture limit. An emergency forced cut retains 400 ms overlap and marks the recording for whole-audio re-recognition after Stop; those partial cuts are never sent to Qwen. The complete recheck replaces provisional overlap before final sentence cleanup. Quiet audio that never crossed the phrase threshold gets a whole-audio check when its RMS is usable. Digital silence skips inference. If live ASR fails, the complete recording is processed locally on CPU after Stop and requires review. Cleanup failures preserve original phrases. Queue pressure triggers a whole-audio fallback rather than losing committed audio.

After Stop, capture ends first; pending phrases and cleanup finish; only then can the existing field policy permit final insertion. Each final unit carries a validation outcome, retained only while that unit's recognized source is unchanged. All final units must be validated edits or exact locally marked source fallbacks. A rejected Qwen rewrite is never eligible; only its source wording with deterministic layout can pass fallback equality checks. Whole-recording CPU retries use the same outcome checks. Cleanup notices are stored by current unit and discarded with revised source. Accepted results can bypass review-only display when automatic typing is enabled and a shortcut target was captured. Manual/WAV tests have no target. The target is consumed after completion to avoid repeat insertion. Focus is never restored automatically. Same-control caret moves are not detected, and Windows provides no atomic focus-check-and-insert operation. Unknown, changed, sensitive or password fields refuse insertion.

## Process and privacy boundary

Native workers bind IPv4 loopback only. Whisper uses a random 192-bit URL prefix covering its routes; Qwen uses a random Bearer token, no web UI and offline mode. Unauthenticated inference is tested to fail. HTTPConnection uses fixed loopback destinations with no proxy or redirect support. Responses are capped at 2 MB; audio is capped by configured capture duration. Native stdout/stderr are drained without retaining transcripts or prompts. Whisper reads in-memory uploaded WAV bytes; FFmpeg conversion is disabled and public directories are empty private temp folders.

Workers belong to a Windows Job with KILL_ON_JOB_CLOSE. Unload, Clear, Cancel, Pause and Quit interrupt connections, kill workers and discard model context. The shortcut starts automatically. Closing settings preserves the shortcut and workers. The microphone's latest-block level is retained only as a scalar, expires when input stops and resets on Stop. Indicator windows neither activate nor receive mouse/keyboard input. A late process assignment after cancellation is rejected and killed. This is process lifecycle ownership, not an executable sandbox. Same-user malicious processes, OS pagefiles/dumps and physical memory recovery are outside the privacy guarantee.

Conventional mode retains the original CLI path: each utterance loads its models and uses temporary WAV/JSON/prompt files removed on normal success/error/cancel. A crash may leave such files. Models and binaries are explicitly provisioned with pinned hashes; application runtime makes no external requests.

## Correction learning

After final insertion, a 60-second watch verifies the exact inserted text and collapsed caret in the existing disposable UIA helper, then polls every 750 ms. It tracks only the insertion and up to 24 unchanged following anchor characters. Some providers retain numeric endpoints when a corrected word changes length; the right anchor reconstructs the boundary with at most 64 characters of growth per observation. End-of-document insertions require a bounded move to still reach that end. Outside selections, changed identity, denied fields and ambiguous ranges stop the watch. No whole-field read or caret movement occurs.

A two-second stable single-token replacement saves only the new spelling to dictionary.json. Token additions/deletions and multiword rewrites end the session; case/punctuation-only changes are ignored. Manual vocabulary plus recent learned spellings is copied into the next recording's configuration. Vocabulary is absent from the worker signature, so hints update without reloading Whisper/Qwen. In-flight requests retain their original settings. Clear/Cancel/Pause/new recording/expiry/focus change forget the baseline and helper range.

## Validation and limits

See PERFORMANCE.md for measured public-sample results and their limits. tests cover phrase ordering, overlapping work, forced-cut replacement, quiet/silent input, final tail delivery, failure fallback, cancellation, stale UI events, process ownership and the existing insertion policy. The native public-audio test verifies both CUDA workers, protected endpoints, reuse and shutdown. Broad microphone/accent/noise scoring, code signing and Android remain separate work.
