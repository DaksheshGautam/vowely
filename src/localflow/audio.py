import threading


class Recorder:
    RATE = 16000

    def __init__(self, device=None, max_seconds=60):
        self.device = device
        self.limit = max_seconds * self.RATE * 2
        self.data = bytearray()
        self.error = None
        self.full = threading.Event()
        self.stream = None
        self._lock = threading.Lock()

    def read_since(self,offset):
        with self._lock:
            size = len(self.data)
            return bytes(self.data[offset:size]),size

    def start(self):
        import sounddevice as sd
        self.data.clear()
        self.full.clear()
        self.error = None

        def callback(indata, frames, timing, status):
            if status:
                self.error = "Audio capture overflow or device error; recording discarded."
                self.full.set()
                raise sd.CallbackStop
            with self._lock:
                remaining = self.limit - len(self.data)
                self.data.extend(bytes(indata)[:remaining])
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
        if self.error:
            raise RuntimeError(self.error)
        return data

    def discard(self):
        try:
            self.stop()
        finally:
            self.data.clear()
