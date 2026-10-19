import sys
import types
import unittest
from unittest.mock import patch

from localflow.audio import Recorder


class CallbackStop(Exception):
    pass


class Stream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self.stopped = False

    def start(self):
        pass

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.sd = types.SimpleNamespace(RawInputStream=Stream, CallbackStop=CallbackStop)
        self.patch = patch.dict(sys.modules, {"sounddevice": self.sd})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_capture_format_and_limit(self):
        r = Recorder(device=2, max_seconds=1)
        r.start()
        stream = r.stream
        self.assertEqual(stream.kwargs["device"], 2)
        self.assertEqual(stream.kwargs["samplerate"], 16000)
        with self.assertRaises(CallbackStop):
            stream.kwargs["callback"](b"\0\0" * 20000, 20000, None, False)
        self.assertTrue(r.full.is_set())
        self.assertEqual(len(r.stop()), 32000)
        self.assertTrue(stream.closed)
        self.assertFalse(r.data)

    def test_overflow_is_discarded(self):
        r = Recorder()
        r.start()
        with self.assertRaises(CallbackStop):
            r.stream.kwargs["callback"](b"audio", 10, None, True)
        with self.assertRaises(RuntimeError):
            r.stop()
        self.assertFalse(r.data)
        self.assertIsNone(r.stream)

    def test_incremental_reads_preserve_complete_stop_audio(self):
        r = Recorder()
        r.start()
        callback = r.stream.kwargs['callback']
        callback(b'\0\1'*100,100,None,False)
        first,offset = r.read_since(0)
        callback(b'\0\2'*200,200,None,False)
        second,offset = r.read_since(offset)
        self.assertEqual(r.read_since(offset),(b'',offset))
        self.assertEqual(r.stop(),first+second)

    def test_start_failure_closes_stream(self):
        class Broken(Stream):
            def start(self):
                raise RuntimeError("missing mic")
        self.sd.RawInputStream = Broken
        r = Recorder()
        with self.assertRaises(RuntimeError):
            r.start()
        self.assertIsNone(r.stream)


if __name__ == "__main__":
    unittest.main()
