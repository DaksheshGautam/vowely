"""Shortcut registration and recording transitions, without mic or key injection."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from localflow.config import Config
from localflow.windows import Windows, parse_hotkey


class ShortcutTests(unittest.TestCase):
    def test_supported_keys_and_reserved_combinations(self):
        for text, expected in [(' Ctrl + Alt + d ',(3,68)),('Shift+Ctrl+7',(6,55)),
                               ('Ctrl+Space',(2,32)),('Alt+Shift+F24',(5,135))]:
            self.assertEqual(parse_hotkey(text),expected)
        for text in ['Ctrl+A','Shift+Space','Win+D','Ctrl+F12','Ctrl+F012','Alt+F4','Alt+F04','Ctrl+','Ctrl+Ctrl+D','AltGr+D',None]:
            with self.subTest(text=text),self.assertRaises(ValueError):parse_hotkey(text)

    def test_config_migrates_existing_hold_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json';path.write_text(json.dumps({'hotkey':'Ctrl+Shift+F8','threads':3}))
            c=Config.load(path);self.assertEqual(c.hotkey,'Ctrl+Shift+F8');self.assertEqual(c.toggle_hotkey,'')
            c.toggle_hotkey='Ctrl+Alt+D';c.save(path);self.assertEqual(Config.load(path),c)
            c.toggle_hotkey='Shift+Ctrl+F8'
            with self.assertRaises(ValueError):c.save(path)
            self.assertEqual(Config.load(path).toggle_hotkey,'Ctrl+Alt+D')

    def native(self):
        w=object.__new__(Windows);w.user=Mock();w.registered=False;w.vk=None;w.bindings={}
        return w

    def test_atomic_reservation_rollback_and_release(self):
        w=self.native();w.user.RegisterHotKey.side_effect=[1,0]
        with self.assertRaisesRegex(RuntimeError,'Toggle shortcut'):w.arm('Ctrl+Alt+F9','Ctrl+Alt+D')
        w.user.UnregisterHotKey.assert_called_once_with(None,w.HOTKEY_ID)
        self.assertFalse(w.registered);self.assertEqual(w.bindings,{})
        w.user.RegisterHotKey.side_effect=None;w.user.RegisterHotKey.return_value=1
        w.arm('Ctrl+Alt+F9','Ctrl+Alt+D');self.assertTrue(w.registered)
        for call in w.user.RegisterHotKey.call_args_list:self.assertTrue(call.args[2] & 0x4000)
        w.user.UnregisterHotKey.reset_mock();w.disarm()
        self.assertEqual(w.user.UnregisterHotKey.call_count,2);self.assertEqual(w.bindings,{})

    def test_duplicate_binding_never_reserves_anything(self):
        w=self.native()
        with self.assertRaises(ValueError):w.arm('Ctrl+Alt+F9','Alt+Ctrl+F9')
        w.user.RegisterHotKey.assert_not_called()

    def test_hold_requires_all_keys_and_toggle_trigger_blocks_insertion(self):
        w=self.native();w.arm('Ctrl+Alt+F9','Ctrl+Alt+D')
        keys={0x11,0x12,0x78};w.down=lambda vk:vk in keys
        self.assertTrue(w.shortcut_down());keys.remove(0x11);self.assertFalse(w.shortcut_down())
        keys.clear();keys.add(68);self.assertTrue(w.trigger_down())
        ok,why=w.insert(None,'text',Config());self.assertFalse(ok);self.assertIn('still held',why)


if os.name=='nt':
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from localflow.app import Window, HotkeyFilter
    from localflow.policy import Target


@unittest.skipUnless(os.name=='nt','Windows desktop tests')
class ShortcutUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        with patch('sounddevice.query_devices',return_value=[]):self.w=Window(root,root/'config.json',auto_prepare=False)
        self.w.c.toggle_hotkey='Ctrl+Alt+D';self.w.toggle_hotkey.setText(self.w.c.toggle_hotkey)
        self.target=Target(100,5,'editor.exe',(1,2),'Editor','Editor',False,True)

    def tearDown(self):
        self.w.win.registered=False;self.w.quit()
        self.w.pool.waitForDone(2000);self.w.lifecycle_pool.waitForDone(2000);self.w.utility_pool.waitForDone(2000)
        self.app.processEvents();self.tmp.cleanup()

    def recording(self,kind='toggle',manual=False):
        pcm=b'\0\1'*16000
        self.w.state='recording';self.w.button_recording=manual;self.w.recording_shortcut=kind
        self.w.record_started=time.monotonic()-2;self.w.win.registered=True
        self.w.recorder=SimpleNamespace(data=bytearray(pcm),full=threading.Event(),stop=Mock(return_value=pcm),discard=Mock())
        return pcm

    def test_native_dispatch_distinguishes_hold_toggle_and_other_messages(self):
        callback=Mock();f=HotkeyFilter(callback);msg=wintypes.MSG();msg.message=0x0312
        for identity,kind in [(Windows.HOTKEY_ID,'hold'),(Windows.TOGGLE_HOTKEY_ID,'toggle')]:
            msg.wParam=identity;self.assertTrue(f.nativeEventFilter(None,ctypes.addressof(msg))[0]);callback.assert_called_with(kind)
        msg.wParam=1;self.assertFalse(f.nativeEventFilter(None,ctypes.addressof(msg))[0]);self.assertEqual(callback.call_count,2)

    def test_toggle_start_captures_original_target_and_ignores_press_during_processing(self):
        self.w.win.registered=True
        with patch.object(self.w.win,'snapshot',return_value=self.target),patch.object(self.w,'begin_recording') as begin:
            self.w.pressed('toggle');begin.assert_called_once();self.assertEqual(self.w.target,self.target)
            self.assertEqual(self.w.recording_shortcut,'toggle');self.assertFalse(self.w.button_recording)
            self.w.state='processing';self.w.pressed('toggle');begin.assert_called_once()

    def test_toggle_release_keeps_recording_second_press_finishes_same_pipeline(self):
        pcm=self.recording()
        with patch.object(self.w.win,'shortcut_down',return_value=False),patch.object(self.w,'start_job') as job,patch.object(self.w.win,'snapshot') as snapshot:
            self.w.tick();job.assert_not_called();self.assertEqual(self.w.state,'recording')
            self.w.pressed('toggle');self.w.tick();job.assert_called_once_with(pcm);snapshot.assert_not_called()

    def test_toggle_stop_feeds_final_audio_into_existing_live_session(self):
        pcm=self.recording();self.w.live_session=session=Mock();self.w.recorder.read_since=lambda offset:(pcm[offset:],len(pcm))
        self.w.pressed('toggle');self.w.tick();session.feed.assert_called_once_with(pcm);session.finish_input.assert_called_once_with(pcm)
        self.assertEqual(self.w.state,'processing');self.assertIsNone(self.w.recorder)

    def test_hold_stops_on_any_required_key_release_and_other_shortcut_is_ignored(self):
        pcm=self.recording('hold')
        with patch.object(self.w,'start_job') as job,patch.object(self.w.win,'shortcut_down',return_value=False):
            self.w.pressed('toggle');self.assertFalse(self.w.stop_requested)
            self.w.tick();job.assert_called_once_with(pcm)

    def test_manual_capture_does_not_become_toggle_and_toggle_obeys_duration_limit(self):
        pcm=self.recording(manual=True)
        with patch.object(self.w,'start_job') as job:
            self.w.pressed('toggle');self.w.tick();job.assert_not_called()
            self.w.button_recording=False;self.w.recorder.full.set();self.w.tick();job.assert_called_once_with(pcm)

    def test_disabled_toggle_and_blocked_fields_do_not_open_microphone(self):
        self.w.win.registered=True
        with patch.object(self.w,'begin_recording') as begin,patch.object(self.w.win,'snapshot',return_value=None):
            self.w.pressed('toggle');begin.assert_not_called()
            self.w.c.toggle_hotkey='';self.w.pressed('toggle');begin.assert_not_called()

    def test_picker_captures_keys_and_escape_preserves_value(self):
        edit=self.w.toggle_hotkey;edit.show();edit.start_capture()
        QTest.keyClick(edit.field,Qt.Key_D,Qt.ControlModifier|Qt.AltModifier)
        self.assertEqual(parse_hotkey(edit.text()),(3,68));self.assertFalse(edit.capturing)
        edit.start_capture();QTest.keyClick(edit.field,Qt.Key_F12,Qt.ControlModifier)
        self.assertTrue(edit.capturing);self.assertIn('reserved',edit.notice.text())
        QTest.keyClick(edit.field,Qt.Key_Escape);self.assertEqual(edit.text(),'Ctrl+Alt+D');self.assertFalse(edit.capturing)

    def test_shortcuts_save_preserve_values_and_are_shown_on_dashboard(self):
        self.w.hotkey.setText('Ctrl+Shift+F8');self.assertTrue(self.w.apply_settings())
        c=Config.load(self.w.config_path);self.assertEqual(c.toggle_hotkey,'Ctrl+Alt+D');self.assertEqual(c.hotkey,'Ctrl+Shift+F8')
        self.w.ui.refresh();self.assertIn(c.toggle_hotkey,self.w.ui.shortcut_label.text())
        self.w.toggle_hotkey.setText('Shift+Ctrl+F8');self.assertFalse(self.w.apply_settings())
        self.assertEqual(Config.load(self.w.config_path),c)

    def test_final_output_waits_for_stop_keys_without_unloading_models(self):
        self.w.target=self.target
        result=dict(text='Test.',raw='test',review=False,insertion_ready=True,cpu_fallback=False,gpu_used=False,total_ms=1)
        callbacks=[]
        with patch.object(self.w.win,'modifiers_down',return_value=True),patch.object(self.w.win,'insert') as insert,patch('localflow.app.QTimer.singleShot',side_effect=lambda ms,fn:callbacks.append(fn)):
            self.w.finished(self.w.generation,result);insert.assert_not_called();self.assertEqual(self.w.state,'processing')
        with patch.object(self.w.win,'modifiers_down',return_value=False),patch.object(self.w.win,'trigger_down',return_value=False),patch.object(self.w.win,'insert',return_value=(True,'Inserted')) as insert:
            callbacks.pop()();insert.assert_called_once_with(self.target,'Test.',self.w.c)
        self.assertEqual(self.w.state,'idle')

    def test_cancel_invalidates_completion_waiting_for_keys(self):
        self.w.target=self.target
        result=dict(text='Test.',raw='test',review=False,insertion_ready=True,cpu_fallback=False,gpu_used=False,total_ms=1)
        callbacks=[]
        with patch.object(self.w.win,'modifiers_down',return_value=True),patch('localflow.app.QTimer.singleShot',side_effect=lambda ms,fn:callbacks.append(fn)):
            self.w.finished(self.w.generation,result)
        self.w.abort()
        with patch.object(self.w.win,'insert') as insert:
            callbacks.pop()();insert.assert_not_called()
        self.assertEqual(self.w.preview.toPlainText(),'')

    def test_key_wait_expires_without_retrying_held_key_insertion(self):
        self.w.target=self.target
        result=dict(text='Test.',raw='test',review=False,insertion_ready=True,cpu_fallback=False,gpu_used=False,total_ms=1)
        with patch.object(self.w.win,'modifiers_down',return_value=True),patch('localflow.app.QTimer.singleShot') as timer:
            self.w.finished(self.w.generation,result,key_deadline=time.monotonic()-1)
            timer.assert_not_called()
        self.assertIn('still held',self.w.status.text());self.assertIsNone(self.w.target)
