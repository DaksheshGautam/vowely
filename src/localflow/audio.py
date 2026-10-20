import threading
import array
import math
import time


class Recorder:
    RATE = 16000
    METER_NOISE_FLOOR = 120 / 32768  # Visual gate only; never discards audio.

    def __init__(self, device=None, max_seconds=60):
        self.device = device
        self.limit = max_seconds * self.RATE * 2
        self.data = bytearray()
        self.error = None
        self.full = threading.Event()
        self.stream = None
        self._lock = threading.Lock()
        self._level = 0.0
        self._level_at = 0.0

    @property
    def input_level(self):
        with self._lock:
            return self._level if time.monotonic()-self._level_at<.25 else 0.0

    def read_since(self,offset):
        with self._lock:
            size = len(self.data)
            return bytes(self.data[offset:size]),size

    def start(self):
        import sounddevice as sd
        self.data.clear()
        self.full.clear()
        self.error = None
        self._level = 0.0

        def callback(indata, frames, timing, status):
            if status:
                self.error = "Audio capture overflow or device error; recording discarded."
                self.full.set()
                raise sd.CallbackStop
            block = bytes(indata)
            samples = array.array('h',block[:len(block)//2*2])
            rms = math.sqrt(sum(x*x for x in samples)/max(1,len(samples)))/32768
            with self._lock:
                remaining = self.limit - len(self.data)
                self.data.extend(block[:remaining])
                self._level = min(1.0,math.sqrt((rms-self.METER_NOISE_FLOOR)*12)) if rms>self.METER_NOISE_FLOOR else 0.0
                self._level_at = time.monotonic()
                full = len(self.data) >= self.limit
            if full:
                self.full.set()
                raise sd.CallbackStop

        self.stream = sd.RawInputStream(samplerate=self.RATE, channels=1, dtype="int16",
                                       device=self.device, callback=callback, blocksize=1024)
        try:
            self.stream.start()
        except Exception:
            self.stream.close()
            self.stream = None
            raise

    def stop(self):
        if self.stream:
            try:
                self.stream.stop()
            finally:
                self.stream.close()
                self.stream = None
        with self._lock:
            data = bytes(self.data)
            self.data.clear()
            self._level = 0.0
        if self.error:
            raise RuntimeError(self.error)
        return data

    def discard(self):
        try:
            self.stop()
        finally:
            self.data.clear()
