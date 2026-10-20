"""Explicit, local desktop checks. No downloads or retained microphone audio."""
from pathlib import Path
import threading
import time

from PySide6.QtCore import QObject, QRunnable, Signal


class CheckSignals(QObject):
    done = Signal(object)
    level = Signal(float)


class AssetCheck(QRunnable):
    def __init__(self,root,config):
        super().__init__()
        self.root,self.config = Path(root),config
        self.signals = CheckSignals()

    def run(self):
        import importlib.util
        c = self.config
        assets = [('Whisper Base',c.base_model),('Whisper Small',c.small_model),
                  ('Qwen cleanup',c.cleanup_model),('Whisper engine',c.whisper_exe),
                  ('Qwen engine',c.llama_exe)]
        if c.vad_model: assets.append(('Silero voice detection',c.vad_model))
        if c.streaming_enabled:
            assets.append(('Whisper live engine','vendor/whisper-cuda/Release/whisper-server.exe' if c.gpu else 'vendor/whisper/Release/whisper-server.exe'))
            if c.cleanup_enabled and c.mode!='Verbatim':
                assets.append(('Qwen live engine','vendor/llama-cuda/llama-server.exe' if c.cleanup_gpu else 'vendor/llama/llama-server.exe'))
        rows = [(name,importlib.util.find_spec(name) is not None,0) for name in ('PySide6','sounddevice','comtypes','psutil')]
        for name,value in assets:
            try:
                path = c.resolve(self.root,value)
                size = path.stat().st_size if path.is_file() else 0
                rows.append((name,size>0,size))
            except OSError: rows.append((name,False,0))
        self.signals.done.emit(rows)


class MicrophoneCheck(QRunnable):
    def __init__(self,device,cancel):
        super().__init__()
        self.device,self.cancel = device,cancel
        self.signals = CheckSignals()

    def run(self):
        from .audio import Recorder
        recorder = Recorder(self.device,4)
        result = {'ok':False,'message':'Microphone check cancelled.'}
        try:
            recorder.start()
            until = time.monotonic()+3
            peak = 0.0
            while time.monotonic()<until and not self.cancel.wait(.06):
                peak = max(peak,recorder.input_level)
                self.signals.level.emit(recorder.input_level)
                if recorder.full.is_set(): break
            pcm = recorder.stop()
            if not self.cancel.is_set():
                received = len(pcm)>=3200
                result = {'ok':received,'message':('Input received. '+('Voice level detected.' if peak>0 else 'Input is very quiet; check distance and input volume.'))
                          if received else 'No usable input received. Choose another microphone and retry.'}
            pcm = b''
        except Exception:
            result = {'ok':False,'message':'Could not capture this microphone. Check its connection and Windows input permissions.'}
        finally:
            try: recorder.discard()
            except Exception: pass
            self.signals.level.emit(0)
            self.signals.done.emit(result)


class CloseModels(QRunnable):
    def __init__(self,runtime,done):
        super().__init__()
        self.runtime,self.done = runtime,done

    def run(self):
        try: self.runtime.close()
        finally: self.done.set()
