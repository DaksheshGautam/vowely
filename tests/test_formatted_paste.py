"""No real clipboard or keys: verify lease/focus/cancellation transitions."""
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication
from localflow.config import Config
from localflow.formatted_paste import FormattedPaste
from localflow.policy import Target


class FormattedPasteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.target=Target(1,2,'editor.exe',(1,),'editor','Editor',False,True)
        self.probe=SimpleNamespace(prepare_paste=Mock(return_value=True),check_paste=Mock(return_value='waiting'),clear_paste=Mock())
        self.native=SimpleNamespace(snapshot=lambda:self.target,modifiers_down=lambda:False,trigger_down=lambda:False,
                                    prepare_probe=lambda:None,probe=self.probe,send_paste_keys=Mock(return_value=True))
        self.worker=SimpleNamespace(request=Mock(side_effect=self.respond),close=Mock())
        self.manager=FormattedPaste(self.native,self.worker);self.addCleanup(self.manager.close)
        self.done=Mock()

    def respond(self,command):
        return {'status':{'stage':'ready','restore':'restored','cancel':'recoverable','recover':'restored'}[command[0]]}

    def begin(self):
        self.manager.begin(self.target,'- One\n- Two\n\nClosing.',Config(),self.done);self.manager.timer.stop()
        if self.manager.phase=='settle':self.manager.deadline=0;self.manager.poll()

    def test_restores_only_after_exact_target_confirmation(self):
        self.begin();self.assertEqual(self.manager.phase,'verify')
        self.native.send_paste_keys.assert_called_once()
        self.manager.poll();self.assertEqual(self.manager.phase,'verify')
        self.assertEqual([call.args[0][0] for call in self.worker.request.call_args_list],['stage'])
        self.probe.check_paste.return_value='inserted';self.manager.poll();self.manager.poll()
        self.done.assert_called_once();self.assertTrue(self.done.call_args.args[0])
        self.assertEqual(self.worker.request.call_args.args[0],('restore',))

    def test_timeout_never_restores_private_previous_clipboard_to_queued_paste(self):
        self.begin();self.manager.deadline=time.monotonic()-1;self.manager.poll();self.manager.poll()
        self.assertEqual(self.worker.request.call_args.args[0],('cancel',))
        self.assertTrue(self.manager.recovery_available)
        self.assertFalse(self.done.call_args.args[0])

    def test_unknown_or_changed_focus_never_sends_paste(self):
        self.native.snapshot=lambda:None;self.begin()
        self.worker.request.assert_not_called();self.native.send_paste_keys.assert_not_called()

    def test_failed_preflight_does_not_touch_clipboard(self):
        self.probe.prepare_paste.return_value=False;self.begin()
        self.worker.request.assert_not_called();self.assertFalse(self.done.call_args.args[0])

    def test_focus_change_after_staging_rolls_back_without_paste(self):
        def respond(command):
            self.native.snapshot=lambda:None
            return {'status':'ready' if command[0]=='stage' else 'restored'}
        self.worker.request.side_effect=respond;self.begin();self.manager.poll()
        self.native.send_paste_keys.assert_not_called()
        self.assertEqual(self.worker.request.call_args.args[0],('restore',))

    def test_partial_paste_is_not_retried(self):
        self.native.send_paste_keys.return_value=False;self.begin();self.manager.poll()
        self.native.send_paste_keys.assert_called_once();self.assertFalse(self.done.call_args.args[0])

    def test_newer_clipboard_is_preserved_after_success(self):
        self.begin();self.probe.check_paste.return_value='inserted';self.manager.poll()
        self.worker.request.side_effect=lambda command:{'status':'changed'};self.manager.poll()
        self.assertTrue(self.done.call_args.args[0]);self.assertIn('newer clipboard',self.done.call_args.args[1])

    def test_config_keeps_keyboard_only_choice(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json';config=Config(preserve_line_breaks=False);config.save(path)
            self.assertFalse(Config.load(path).preserve_line_breaks)
        self.assertTrue(Config.load(Path('missing-profile/config.json')).preserve_line_breaks)

    def test_cancel_before_paste_restores_without_injecting_keys(self):
        self.manager.begin(self.target,'One\nTwo',Config(),self.done);self.manager.timer.stop()
        self.assertEqual(self.manager.phase,'settle')
        self.manager.cancel();self.manager.poll()
        self.native.send_paste_keys.assert_not_called()
        self.assertEqual(self.worker.request.call_args.args[0],('restore',))
        self.assertFalse(self.done.call_args.args[0])

    def test_sensitive_target_cannot_stage_clipboard(self):
        from dataclasses import replace
        for target in (replace(self.target,password=True),replace(self.target,process='bitwarden.exe'),replace(self.target,editable=False)):
            self.manager.begin(target,'One\nTwo',Config(),self.done)
        self.worker.request.assert_not_called();self.native.send_paste_keys.assert_not_called()
