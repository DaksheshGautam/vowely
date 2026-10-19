"""Headless UI lifecycle checks; no real microphone, shortcut or insertion."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HAS_QT = importlib.util.find_spec("PySide6") is not None and sys.platform == "win32"
if HAS_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from localflow.app import Window


@unittest.skipUnless(HAS_QT, "Windows + PySide6 required for UI checks")
class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mic_patch = patch("sounddevice.query_devices", return_value=[])
        self.mic_patch.start()
        self.addCleanup(self.mic_patch.stop)
        root = Path(self.tmp.name)
        self.window = Window(root, root / "config.json")
        self.addCleanup(self.window.quit)

    def test_start_is_disarmed_and_cancel_clears_text(self):
        self.assertFalse(self.window.win.registered)
        self.assertIsNone(self.window.recorder)
        self.window.preview.setPlainText("private draft")
        self.window.abort()
        self.assertEqual(self.window.preview.toPlainText(), "")

    def test_failed_hotkey_does_not_save_or_arm(self):
        with patch.object(self.window.win, "arm", side_effect=RuntimeError("Shortcut in use")):
            self.window.toggle_arm()
        self.assertFalse(self.window.win.registered)
        self.assertFalse(self.window.config_path.exists())
        self.assertIn("in use", self.window.status.text())

    def test_stale_completion_ignored(self):
        self.window.preview.setPlainText("current")
        self.window.finished(self.window.generation - 1, {"text": "stale"})
        self.assertEqual(self.window.preview.toPlainText(), "current")

    def test_missing_microphone_frames_reports_device_instead_of_short_click(self):
        self.window.state = 'recording'
        self.window.button_recording = True
        self.window.record_started = time.monotonic() - 4
        recorder = SimpleNamespace(data=bytearray(), full=threading.Event(), discard=lambda: None)
        self.window.recorder = recorder
        self.window.tick()
        self.assertEqual(self.window.state, 'idle')
        self.assertIn('No audio received', self.window.status.text())
        self.assertNotIn('too short', self.window.status.text())

    def test_manual_recording_stays_active_until_stop_and_submits_audio(self):
        self.window.state = 'recording'
        self.window.button_recording = True
        self.window.record_started = time.monotonic() - 2
        pcm = b'\0\1' * 16000
        self.window.recorder = SimpleNamespace(data=bytearray(pcm), full=threading.Event(), stop=lambda: pcm)
        with patch.object(self.window, 'start_job') as job:
            self.window.tick()
            job.assert_not_called()
            self.assertEqual(self.window.state, 'recording')
            self.window.manual_record()
            self.window.tick()
            job.assert_called_once_with(pcm)

    def test_start_double_click_does_not_immediately_stop_capture(self):
        self.window.state = 'recording'
        self.window.record_started = time.monotonic()
        self.window.manual_record()
        self.assertFalse(self.window.stop_requested)

    def test_live_preview_is_provisional_and_never_inserts(self):
        self.window.state = 'recording'
        payload = dict(raw='raw phrase',text='Clean phrase.',asr_busy=True,cleanup_busy=True,
                       warning='',cleaned_phrases=1,pending_phrases=1)
        with patch.object(self.window.win,'insert') as insert:
            self.window.live_update(self.window.generation,payload)
            insert.assert_not_called()
        self.assertEqual(self.window.preview.toPlainText(),'Clean phrase.')
        self.assertIn('Recognising + cleaning',self.window.models_status.text())
        self.window.abort()
        self.window.live_update(self.window.generation-1,payload)
        self.assertEqual(self.window.preview.toPlainText(),'')

    def test_live_stop_delivers_last_audio_before_finish(self):
        from unittest.mock import Mock
        pcm = b'\0\1'*16000
        self.window.state = 'recording'
        self.window.button_recording = True
        self.window.record_started = time.monotonic()-2
        self.window.stop_requested = True
        self.window.recorder = SimpleNamespace(data=bytearray(pcm),full=threading.Event(),
            read_since=lambda offset:(pcm[offset:],len(pcm)),stop=lambda:pcm)
        session = self.window.live_session = Mock()
        self.window.tick()
        session.feed.assert_called_once_with(pcm)
        session.finish_input.assert_called_once_with(pcm)
        self.assertEqual(self.window.state,'processing')
        self.assertFalse(self.window.copy_button.isEnabled())

    def test_clear_discards_resident_context(self):
        from unittest.mock import Mock
        runtime = self.window.runtime = Mock()
        self.window.preview.setPlainText('draft')
        self.window.forget_result()
        runtime.close.assert_called_once()
        self.assertIsNone(self.window.runtime)
        self.assertEqual(self.window.preview.toPlainText(),'')


if __name__ == "__main__":
    unittest.main()
