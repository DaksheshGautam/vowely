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
    from PySide6.QtCore import Qt
    from localflow.policy import Target


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
        self.window = Window(root, root / "config.json",auto_prepare=False)
        self.addCleanup(self.window.quit)

    def test_start_is_disarmed_and_cancel_clears_text(self):
        self.assertFalse(self.window.win.registered)
        self.assertIsNone(self.window.recorder)
        self.window.preview.setPlainText("private draft")
        self.window.abort()
        self.assertEqual(self.window.preview.toPlainText(), "")

    def test_failed_hotkey_does_not_save_or_arm(self):
        with patch.object(self.window.win, "arm", side_effect=RuntimeError("Shortcut in use")):
            self.window.toggle_dictation()
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
        self.assertEqual(self.window.overlay.phase,'processing')

    def test_clear_discards_resident_context(self):
        from unittest.mock import Mock
        runtime = self.window.runtime = Mock()
        self.window.preview.setPlainText('draft')
        self.window.forget_result()
        runtime.close.assert_called_once()
        self.assertIsNone(self.window.runtime)
        self.assertEqual(self.window.preview.toPlainText(),'')

    def test_reviewed_result_and_explicit_copy_preserve_list_and_paragraph_breaks(self):
        from unittest.mock import Mock
        text = '1. Pay ₹500.\n2. Meet at 18:30.\n\nDone.'
        result = dict(text=text,raw='original',review=True,warning='Review',
                      cpu_fallback=False,gpu_used=False,total_ms=10)
        self.window.finished(self.window.generation,result)
        self.assertEqual(self.window.preview.toPlainText(),text)
        clipboard = Mock()
        with patch('localflow.app.QApplication.clipboard',return_value=clipboard):
            self.window.copy_result()
        clipboard.setText.assert_called_once_with(text)

    def final_result(self,**changes):
        result = dict(text='- Milk\n- Bread',raw='milk, bread',review=True,
                      insertion_ready=True,warning='Cleanup requires review.',
                      cpu_fallback=False,gpu_used=False,total_ms=10)
        result.update(changes)
        return result

    def test_only_final_validated_result_inserts_once_without_activating_window(self):
        target = self.window.target = Target(100,5,'editor.exe',(1,2),'Editor','Editor',False,True)
        result = self.final_result()
        with patch.object(self.window.win,'insert',return_value=(True,'Inserted into the original field.')) as insert, \
             patch.object(self.window,'reveal') as reveal,patch.object(self.window,'activateWindow') as activate:
            self.window.finished(self.window.generation,result)
            insert.assert_called_once_with(target,result['text'],self.window.c)
            self.assertEqual(self.window.overlay.phase,'done')
            self.assertEqual(self.window.overlay.label,'Typed')
            self.window.finished(self.window.generation,result)
            insert.assert_called_once()
            reveal.assert_not_called();activate.assert_not_called()

    def test_failed_cleanup_manual_recording_and_stale_results_never_insert(self):
        with patch.object(self.window.win,'insert') as insert:
            self.window.target = object()
            self.window.finished(self.window.generation,self.final_result(insertion_ready=False))
            self.window.target = None
            self.window.finished(self.window.generation,self.final_result())
            self.window.target = object()
            self.window.finished(self.window.generation-1,self.final_result())
            insert.assert_not_called()

    def test_focus_refusal_stays_in_preview_and_overlay_reports_it(self):
        self.window.target = object()
        with patch.object(self.window.win,'insert',return_value=(False,'Focus changed. Preview ready; no text inserted.')):
            self.window.finished(self.window.generation,self.final_result())
        self.assertIn('Focus changed',self.window.overlay.label)
        self.assertEqual(self.window.preview.toPlainText(),'- Milk\n- Bread')

    def test_source_fallback_inserts_and_reports_why_original_words_were_used(self):
        self.window.target = object()
        result = self.final_result(cleanup_fallback=True)
        with patch.object(self.window.win,'insert',return_value=(True,'Inserted into the original field.')) as insert:
            self.window.finished(self.window.generation,result)
        insert.assert_called_once()
        self.assertEqual(self.window.overlay.label,'Typed • original fallback')
        self.assertIn('original words',self.window.status.text())

    def test_insertion_refusal_overlay_displays_real_reason(self):
        for message,label in [('Shortcut keys are still held. Preview only.','Release shortcut keys'),
                              ('Automatic insertion is off. Preview ready.','Automatic typing is off'),
                              ('Focused field cannot be verified. Preview only.','Text box unavailable'),
                              ('Insertion blocked or partial.','Typing blocked — check box')]:
            with self.subTest(message=message):
                self.window.target = object()
                with patch.object(self.window.win,'insert',return_value=(False,message)):
                    self.window.finished(self.window.generation,self.final_result())
                self.assertEqual(self.window.overlay.label,label)

    def test_overlay_is_nonactivating_click_through_and_clears_on_cancel(self):
        overlay = self.window.overlay
        flags = overlay.windowFlags()
        self.assertTrue(flags & Qt.WindowDoesNotAcceptFocus)
        self.assertTrue(flags & Qt.WindowTransparentForInput)
        self.assertTrue(overlay.testAttribute(Qt.WA_ShowWithoutActivating))
        overlay.show_phase('listening')
        overlay.set_level(.9);overlay.animate()
        self.assertGreater(overlay.level,0)
        overlay.show_phase('processing')
        self.assertEqual(overlay.target_level,0)
        self.window.abort()
        self.assertEqual(overlay.phase,'hidden')
        self.assertFalse(overlay.timer.isActive())

    def test_background_and_close_keep_armed_shortcut(self):
        from PySide6.QtGui import QCloseEvent
        with patch('localflow.app.QSystemTrayIcon.isSystemTrayAvailable',return_value=True), \
             patch.object(self.window,'disarm') as disarm:
            self.window.run_background()
            event = QCloseEvent()
            self.window.closeEvent(event)
            disarm.assert_not_called()
            self.assertFalse(event.isAccepted())

    def test_silent_listening_settles_then_stays_completely_still(self):
        overlay = self.window.overlay
        overlay.show_phase('listening')
        overlay.set_level(1)
        for _ in range(10): overlay.animate()
        self.assertGreater(overlay.level,.9)
        overlay.set_level(0)
        for _ in range(35): overlay.animate()
        self.assertEqual(overlay.level,0)
        angle = overlay.angle
        for _ in range(10): overlay.animate()
        self.assertEqual((overlay.level,overlay.angle),(0,angle))
        overlay.show_phase('processing')
        overlay.animate()
        self.assertNotEqual(overlay.angle,angle)

    def test_shortcut_records_in_focused_box_without_approval(self):
        self.window.c.auto_insert = True
        self.window.win.registered = True
        target = Target(100,5,'editor.exe',(1,2),'','Editor',False,True)
        with patch.object(self.window.win,'snapshot',return_value=target),patch.object(self.window,'begin_recording') as record:
            self.window.pressed()
            record.assert_called_once()
        self.assertEqual(self.window.target,target)
        self.assertFalse(hasattr(self.window,'allow_button'))
        self.assertFalse(hasattr(self.window,'background'))
        self.assertFalse(hasattr(self.window,'arm'))
        self.window.win.registered = False

    def test_startup_registers_shortcut_without_user_setup(self):
        def reserve(key): self.window.win.registered = True
        with patch.object(self.window.win,'arm',side_effect=reserve) as reserve_key:
            self.window.start_automatically()
            reserve_key.assert_called_once_with(self.window.c.hotkey)
            self.window.start_automatically()
            reserve_key.assert_called_once()
        self.assertEqual(self.window.pause.text(),'Pause dictation')
        self.window.win.registered = False

    def test_resume_automatically_reloads_models_before_next_shortcut(self):
        with patch.object(self.window,'prepare_live'):
            self.window.live.setChecked(True)
        self.window.state = 'idle'
        def reserve(key): self.window.win.registered = True
        with patch.object(self.window.win,'arm',side_effect=reserve),patch.object(self.window,'prepare_live') as prepare:
            self.window.start_automatically()
            prepare.assert_called_once()
        self.window.win.registered = False

    def test_dictionary_updates_next_request_without_changing_manual_settings(self):
        self.window.c.personal_vocabulary = ['ManualName']
        self.window.dictionary.add(['Jane'])
        config = self.window.inference_config()
        self.assertEqual(config.personal_vocabulary,['ManualName','Jane'])
        self.assertEqual(self.window.c.personal_vocabulary,['ManualName'])

    def test_successful_insertion_starts_watch_and_clear_discards_it(self):
        from localflow.learning import EditSession
        target = Target(100,5,'editor.exe',(1,2),'','Editor',False,True)
        self.window.target = target
        with patch.object(self.window.win,'insert',return_value=(True,'Inserted')):
            self.window.finished(self.window.generation,self.final_result())
        self.assertIsInstance(self.window.edit_session,EditSession)
        self.assertEqual(self.window.edit_target,target)
        with patch.object(self.window.win,'clear_correction_watch') as forget:
            self.window.clear_text()
            forget.assert_called_once()
        self.assertIsNone(self.window.edit_session)

    def test_failed_insertion_and_disabled_learning_do_not_start_watch(self):
        for enabled,inserted in [(True,False),(False,True)]:
            self.window.c.learn_corrections = enabled
            self.window.target = object()
            with patch.object(self.window.win,'insert',return_value=(inserted,'Test')):
                self.window.finished(self.window.generation,self.final_result())
            self.assertIsNone(self.window.edit_session)

    def test_settled_word_is_saved_and_changed_focus_clears_watch(self):
        from localflow.learning import EditSession
        self.window.edit_session = EditSession('Meet Jan today.',0)
        self.window.edit_target = object()
        self.window.edit_pending = 'Meet Jan today.'
        with patch.object(self.window.win,'correction_span',return_value='Meet Jane today.'), \
             patch('localflow.app.time.monotonic',return_value=1) as now:
            self.window.poll_learning()
            now.return_value = 4
            self.window.poll_learning()
        self.assertEqual(self.window.dictionary.words,['Jane'])
        self.assertIn('Learned locally',self.window.dictionary_status.text())
        with patch.object(self.window.win,'correction_span',return_value=None), \
             patch('localflow.app.time.monotonic',return_value=5), \
             patch.object(self.window.win,'clear_correction_watch') as forget:
            self.window.poll_learning()
            forget.assert_called_once()
        self.assertIsNone(self.window.edit_session)


if __name__ == "__main__":
    unittest.main()
