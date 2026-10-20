# Components and provenance

Vowely uses the components below. The source repository and Windows portable ZIP do not include large model weights or inference engine redistributions. Explicit setup downloads pinned assets, verifies SHA-256 and keeps upstream archives/notices locally. Normal dictation never downloads anything or calls an external inference API.

| Component | Purpose | Upstream |
|---|---|---|
| Python | Application runtime | https://www.python.org/ |
| PySide6 / Qt / shiboken6 | Desktop window, tray and bindings | https://www.qt.io/qt-for-python |
| sounddevice / PortAudio | Microphone capture | https://python-sounddevice.readthedocs.io/ |
| comtypes | Windows UI Automation bindings | https://github.com/enthought/comtypes |
| psutil | Process identity and diagnostics | https://github.com/giampaolo/psutil |
| cffi / pycparser | Audio binding dependencies | https://cffi.readthedocs.io/ |
| whisper.cpp b5454 | CPU/CUDA local speech recognition | https://github.com/ggml-org/whisper.cpp/tree/d1be6fde11ac6e0407606b4e42fe72d34add8037 |
| Whisper Base / Small | Speech models | https://huggingface.co/ggerganov/whisper.cpp |
| llama.cpp b11734 | CPU/CUDA local text inference | https://github.com/ggml-org/llama.cpp/tree/f3fb2fcdbc93a8f677e893b8dbd36462b3190ffd |
| Qwen3-1.7B Q4_K_M | Text cleanup; quantization published by Unsloth | https://huggingface.co/unsloth/Qwen3-1.7B-GGUF |
| Silero VAD | Optional local voice detection | https://huggingface.co/ggml-org/whisper-vad |
| NVIDIA CUDA / cuBLAS | Optional GPU inference runtime | https://developer.nvidia.com/cuda-toolkit |

The exact artifact URLs, revisions, sizes and hashes are in assets-manifest.json. The public benchmark WAV is upstream samples/jfk.wav from the pinned whisper.cpp revision; it is not a user's recording.

The portable app includes available upstream license/notice files under THIRD_PARTY_LICENSES and dynamic Qt runtime libraries. Python/Qt/dependency licenses remain their publishers' licenses; inclusion does not change them. Downloaded engines/models retain their own licensing terms and notices. See the pinned [whisper.cpp license](https://github.com/ggml-org/whisper.cpp/blob/d1be6fde11ac6e0407606b4e42fe72d34add8037/LICENSE) and [llama.cpp license](https://github.com/ggml-org/llama.cpp/blob/f3fb2fcdbc93a8f677e893b8dbd36462b3190ffd/LICENSE). Windows fonts are read from the OS when needed and are not redistributed.

The alpha.12 Windows installer contains the dynamic application runtime and available dependency licenses, plus Inno Setup installer machinery. It does not redistribute model weights or inference engines inside the setup executable; the explicit setup screen obtains the same pinned upstream assets. Microsoft native runtime DLLs supplied with the Qt package are copied beside installed engines for app-local loading; no system runtime or driver installation is performed. Inno Setup is from https://jrsoftware.org/. The installer compiler version and checksum are pinned in scripts/install_build_tools.ps1.
