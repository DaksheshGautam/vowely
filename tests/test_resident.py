from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from localflow.config import Config
from localflow.engines import EngineError
from localflow.resident import ProcessOwner, ResidentModels


class ResidentTests(unittest.TestCase):
    def test_five_minute_recording_reaches_local_whisper_without_old_two_minute_rejection(self):
        c=Config();models=ResidentModels(c,Path('.'));self.addCleanup(models.close)
        request=Mock(return_value={'text':'Synthetic long recording.'})
        models.asr=SimpleNamespace(request=request,close=lambda:None)
        self.assertEqual(models.transcribe(bytes(300*32000),c,threading.Event()),'Synthetic long recording.')
        self.assertGreater(len(request.call_args.args[2]),300*32000)
        with self.assertRaises(EngineError):models.transcribe(bytes(301*32000),c,threading.Event())

    @unittest.skipUnless(sys.platform=='win32','Windows Job ownership')
    def test_owner_close_kills_child_and_rejects_late_assignment(self):
        owner = ProcessOwner()
        self.addCleanup(owner.close)
        def child():
            p = subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.addCleanup(lambda:p.kill() if p.poll() is None else None)
            return p
        proc = child()
        owner.assign(proc)
        owner.close()
        proc.wait(timeout=3)
        late = child()
        with self.assertRaises(EngineError): owner.assign(late)
        self.assertIsNotNone(late.poll())

    def test_gpu_start_failure_uses_cpu_and_is_reported(self):
        models = ResidentModels(Config(gpu=True),Path('.'))
        self.addCleanup(models.close)
        def worker(gpu):
            def start():
                if gpu: raise EngineError('GPU unavailable')
            return SimpleNamespace(start=start,close=lambda:None,requested_gpu=gpu)
        with patch.object(models,'_make',side_effect=lambda kind,gpu:worker(gpu)):
            result = models._start_one('whisper',True)
        self.assertFalse(result.requested_gpu)
        self.assertTrue(models.asr_cpu_fallback)

    def test_dead_worker_needs_reload(self):
        models = ResidentModels(Config(),Path('.'))
        models.ready = True
        models.asr = SimpleNamespace(proc=SimpleNamespace(poll=lambda:1),close=lambda:None)
        self.addCleanup(models.close)
        self.assertFalse(models.matches(Config()))
