# Measurements and limits

These are development measurements on Ryzen 5 3550H / 16 GB RAM / GTX 1650 4 GB, using pinned Whisper Small and Qwen3-1.7B Q4_K_M engines. They are not guarantees for other hardware, power/thermal conditions, workloads or personal speech.

## Current Whisper-controlled live mode

A 22.1-second public-audio test used the bundled upstream speech sample twice with only 0.1 seconds added between clips. Both CUDA workers were confirmed. Silence endpoints were disabled. Eight Whisper previews were processed; a stable sentence was sent for cleanup at 12.06 seconds, before Stop. Exactly one complete-audio recognition ran after Stop. Its raw 44-word transcript matched the reference. ASR and cleanup overlap was observed; no CPU fallback was used. Both workers stopped afterward.

In that run, models loaded in 6.31 seconds, the first preview appeared at 4.22 seconds, and final processing after Stop took 6.49 seconds including pending cleanup. Models can stay loaded between recordings. Preview cadence is about 2.5 seconds when processing keeps up. Whole-audio final recognition deliberately adds after-Stop work so revised live recognition can replace stale cleanup.

The automated suite covers boundary stability and lifecycle/policy logic. Public-clip recognition does not establish general accuracy. Broad accent/noise/microphone scoring, long recordings, daily-app compatibility and production security review remain unfinished. Qwen can change meaning; compare original and cleaned text.

Reproduce the current functional measurement with scripts/test_whisper_endpoints.py after explicit provisioning. It opens no microphone and leaves settings unchanged. Output JSON contains timing/count/hash metadata. Local reports are excluded from Git because other diagnostic reports may contain machine-specific paths or device details.
