from dataclasses import asdict, dataclass, field
from pathlib import Path
import json


@dataclass
class Config:
    whisper_exe: str = "vendor/whisper/Release/whisper-cli.exe"
    base_model: str = "models/ggml-base.bin"
    small_model: str = "models/ggml-small.bin"
    asr_model: str = "base"
    gpu: bool = False
    cpu_whisper_exe: str = ""  # Separate CPU build if the CUDA build cannot initialize.
    llama_exe: str = "vendor/llama/llama-completion.exe"
    cleanup_model: str = "models/Qwen3-1.7B-Q4_K_M.gguf"
    cleanup_enabled: bool = False
    mode: str = "Natural"
    threads: int = 4
    language: str = "auto"
    microphone: int | None = None
    max_seconds: int = 60
    inference_timeout: int = 180
    hotkey: str = "Ctrl+Alt+F9"
    auto_insert: bool = False
    allow_fields: list[str] = field(default_factory=list)
    deny_processes: list[str] = field(default_factory=lambda: [
        "keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe",
        "credentialuibroker.exe", "consent.exe", "windowsterminal.exe",
        "powershell.exe", "pwsh.exe", "cmd.exe"])
    deny_name_fragments: list[str] = field(default_factory=lambda: [
        "password", "passphrase", "secret", "token", "credit card", "cvv", "otp", "pin"])
    vad_model: str = ""  # Optional whisper.cpp-compatible Silero ggml model.
    beam_size: int = 1
    personal_vocabulary: list[str] = field(default_factory=list)
    streaming_enabled: bool = False
    cleanup_gpu: bool = False

    def validate(self):
        for value in (self.gpu, self.cleanup_enabled, self.auto_insert,self.streaming_enabled,self.cleanup_gpu):
            if type(value) is not bool:
                raise ValueError("gpu, cleanup_enabled and auto_insert must be JSON booleans")
        if self.asr_model not in ("base", "small"):
            raise ValueError("asr_model must be base or small")
        if self.mode not in ("Natural", "Verbatim", "Developer"):
            raise ValueError("Unknown dictation mode")
        if not 1 <= self.threads <= 8 or not 1 <= self.max_seconds <= 120:
            raise ValueError("threads must be 1–8; max_seconds must be 1–120")
        if not 1 <= self.inference_timeout <= 600:
            raise ValueError("inference_timeout must be 1–600 seconds")
        if type(self.beam_size) is not int or not 1 <= self.beam_size <= 5:
            raise ValueError("beam_size must be 1–5")
        if (not isinstance(self.personal_vocabulary, list) or len(self.personal_vocabulary) > 32
                or any(not isinstance(x, str) or not x.strip() or len(x) > 80
                       or any(ord(ch) < 32 for ch in x) for x in self.personal_vocabulary)
                or len(', '.join(self.personal_vocabulary).encode('utf-8')) > 2000):
            raise ValueError('Personal vocabulary must contain at most 32 short names/phrases, without control characters')
        if self.language != "auto" and not (self.language.isalpha() and len(self.language) <= 3):
            raise ValueError("language must be auto or a Whisper language code")
        if self.microphone is not None and (type(self.microphone) is not int or self.microphone < 0):
            raise ValueError("microphone must be null or a nonnegative device index")
        for names in (self.allow_fields, self.deny_processes, self.deny_name_fragments):
            if not isinstance(names, list) or not all(isinstance(x, str) and x for x in names):
                raise ValueError("Allow/deny entries must be nonempty strings")

    @classmethod
    def load(cls, path: Path):
        if not path.exists():
            return cls()
        c = cls(**json.loads(path.read_text(encoding="utf-8")))
        c.validate()
        return c

    def save(self, path: Path):
        self.validate()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(path)

    def resolve(self, root: Path, value: str) -> Path:
        p = Path(value)
        return (root / p).resolve() if not p.is_absolute() else p.resolve()
