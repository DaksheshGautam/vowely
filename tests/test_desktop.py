"""Presentation, migration and worker checks; no native input or microphone."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from dataclasses import asdict

HAS_QT = sys.platform=='win32' and importlib.util.find_spec('PySide6') is not None
if HAS_QT:
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtTest import QTest
    from localflow.app import Window
    from localflow.config import Config
    from localflow.windows import Windows
    from localflow.ui_jobs import AssetCheck


@unittest.skipUnless(HAS_QT,'Windows and Qt required')
class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.mics=patch('sounddevice.query_devices',return_value=[]);self.mics.start()
        self.probe=patch.object(Windows,'prepare_probe');self.probe.start()
        self.windows=[]

    def tearDown(self):
        for w in self.windows:
            w.quit()
            for pool in (w.pool,w.lifecycle_pool,w.utility_pool):pool.waitForDone(2000)
        for _ in range(4):self.app.processEvents()
        self.probe.stop();self.mics.stop();self.temp.cleanup()

    def window(self,config=None):
        if config is not None:config.save(self.root/'config.json')
        w=Window(self.root,self.root/'config.json',auto_prepare=False);self.windows.append(w)
        return w

    def test_existing_values_survive_apply_and_ui_migration(self):
        c=Config(beam_size=3,threads=7,max_seconds=97,inference_timeout=211,language='hi',mode='Developer',
                 base_model='custom/base.bin',small_model='custom/small.bin',cleanup_model='custom/qwen.gguf',
                 whisper_exe='custom/whisper.exe',llama_exe='custom/llama.exe',cpu_whisper_exe='',
                 personal_vocabulary=['Manual Name'],deny_processes=['custom.exe','another.exe'],deny_name_fragments=['private','credit card','passphrase'])
        w=self.window(c)
        self.assertFalse(w.needs_onboarding)
        self.assertTrue(w.apply_settings())
        self.assertEqual(asdict(Config.load(w.config_path)),asdict(c))

    def test_default_multiline_denylists_survive_save_exactly(self):
        c=Config();w=self.window(c)
        self.assertEqual(w.ui.deny_processes.toPlainText().splitlines(),c.deny_processes)
        self.assertEqual(w.ui.deny_names.toPlainText().splitlines(),c.deny_name_fragments)
        self.assertTrue(w.apply_settings())
        self.assertEqual(asdict(Config.load(w.config_path)),asdict(c))

    def test_new_setup_and_interrupted_setup_are_distinguished_from_legacy(self):
        w=self.window();self.assertTrue(w.needs_onboarding)
        w.ui.open_onboarding()
        self.assertFalse(json.loads((self.root/'ui-state.json').read_text())['onboarding_completed'])
        Config().save(self.root/'config.json')
        again=self.window();self.assertTrue(again.needs_onboarding)

    def test_setup_completion_records_only_ui_flag_and_delegates_to_startup(self):
        w=self.window();w.ui.open_onboarding()
        with patch.object(w,'start_automatically') as start:
            w.ui.finish_onboarding();start.assert_called_once()
        self.assertFalse(w.needs_onboarding)
        self.assertEqual(json.loads((self.root/'ui-state.json').read_text()),{'version':1,'onboarding_completed':True})
        self.assertEqual(w.ui.stack.currentIndex(),0)

    def test_invalid_shortcut_does_not_overwrite_existing_config(self):
        w=self.window(Config());before=w.config_path.read_bytes()
        w.hotkey.setText('Ctrl+A')
        self.assertFalse(w.apply_settings());self.assertEqual(w.config_path.read_bytes(),before)

    def test_navigation_keeps_engine_state_and_does_not_save_history(self):
        w=self.window(Config());w.preview.setPlainText('Current session only.')
        w.win.registered=True;w.working(False)
        with patch.object(w,'abort') as abort,patch.object(w,'toggle_dictation') as toggle:
            for i in range(6):w.ui.navigate(i)
            abort.assert_not_called();toggle.assert_not_called()
        self.assertTrue(w.win.registered)
        self.assertEqual(w.preview.toPlainText(),'Current session only.')
        self.assertNotIn('History',w.ui.NAMES)
        self.assertFalse((self.root/'history.json').exists())
        w.win.registered=False

    def test_dashboard_and_setup_share_only_the_current_result_document(self):
        w=self.window(Config());w.preview.setPlainText('One current result.')
        self.assertEqual(w.ui.home_preview.toPlainText(),'One current result.')
        self.assertEqual(w.ui.setup_result.toPlainText(),'One current result.')
        w.clear_text()
        self.assertEqual(w.ui.home_preview.toPlainText(),'')
        self.assertEqual(w.ui.setup_result.toPlainText(),'')

    def test_compact_navigation_and_pages_remain_scrollable(self):
        w=self.window(Config());w.resize(780,560);w.ui.adapt()
        self.assertEqual(w.ui.sidebar.width(),68)
        for i in range(6):
            w.ui.navigate(i)
            self.assertTrue(w.ui.stack.currentWidget().widgetResizable())
        w.resize(1100,740);w.ui.adapt();self.assertEqual(w.ui.sidebar.width(),196)

    def test_keyboard_shortcut_navigates_without_arming_dictation(self):
        w=self.window(Config());w.show();w.activateWindow();self.app.processEvents()
        QTest.keyClick(w,Qt.Key_3,Qt.AltModifier);self.app.processEvents()
        self.assertEqual(w.ui.stack.currentIndex(),2)
        self.assertFalse(w.win.registered)

    def test_update_notification_opens_details_and_sidebar_action_survives_compact_layout(self):
        from localflow.updates import select_update
        from test_updates import release
        w=self.window(Config());w.show();self.app.processEvents()
        w.updates.candidate=select_update([release('v9.0.0')],'1.0.0',False);w.updates.refresh()
        self.assertTrue(w.ui.update_notice.isVisible())
        w.resize(780,560);w.ui.adapt();self.app.processEvents()
        self.assertEqual(w.ui.update_notice.action.text(),'↓')
        self.assertLessEqual(w.ui.update_notice.width(),w.ui.sidebar.width())
        self.assertTrue(w.ui.update_notice.action.isVisible())
        with patch.object(w,'reveal') as reveal:
            w.tray.messageClicked.emit();reveal.assert_called_once()
        self.assertEqual(w.ui.settings_tabs.currentIndex(),4);self.assertEqual(w.ui.stack.currentIndex(),4)

    def test_vocabulary_search_and_removal_change_future_hints(self):
        w=self.window(Config());w.dictionary.add(['Acme','LocalTerm']);w.ui.navigate(2)
        w.ui.word_search.setText('acme')
        self.assertFalse(w.ui.word_list.item(0).isHidden());self.assertTrue(w.ui.word_list.item(1).isHidden())
        w.ui.word_list.setCurrentRow(0);w.ui.remove_selected_words()
        self.assertEqual(w.dictionary.words,['LocalTerm'])
        self.assertNotIn('Acme',w.inference_config().personal_vocabulary)

    def test_model_shutdown_does_not_block_qt_or_execute_on_its_thread(self):
        w=self.window(Config());entered=threading.Event();release=threading.Event();threads=[]
        def close():threads.append(threading.get_ident());entered.set();release.wait(1)
        w.runtime=Mock(stop=threading.Event(),close=close)
        before=time.monotonic();w.unload_models();elapsed=time.monotonic()-before
        try:
            self.assertLess(elapsed,.3);self.assertTrue(entered.wait(1))
            self.assertNotEqual(threads[0],threading.get_ident())
            callbacks=[];QTimer.singleShot(0,lambda:callbacks.append(True));self.app.processEvents()
            self.assertTrue(callbacks);self.assertIsNone(w.runtime)
        finally:release.set();w.lifecycle_pool.waitForDone(1000)

    def test_model_loading_is_async_and_cancellable_while_starting(self):
        from localflow.engines import Cancelled
        w=self.window(Config(streaming_enabled=True));entered=threading.Event();closed=threading.Event()
        class Runtime:
            def __init__(self,*args):self.stop=threading.Event()
            def start(self):
                entered.set();self.stop.wait(1)
                if self.stop.is_set():raise Cancelled('Cancelled')
            def close(self):closed.set()
        with patch('localflow.app.ResidentModels',Runtime):
            before=time.monotonic();w.prepare_live()
            self.assertLess(time.monotonic()-before,.3)
            self.assertTrue(entered.wait(1));self.assertEqual(w.state,'preparing')
            w.abort();w.lifecycle_pool.waitForDone(1500)
            self.assertTrue(closed.is_set());self.assertEqual(w.state,'idle')

    def test_asset_diagnostics_are_real_and_make_no_network_requests(self):
        job=AssetCheck(self.root,Config());rows=[];job.signals.done.connect(rows.extend)
        with patch('socket.create_connection',side_effect=AssertionError('Network forbidden')):job.run()
        self.assertIn(('Whisper Base',False,0),rows)
        self.assertIn(('PySide6',True,0),rows)

    def test_microphone_diagnostic_uses_worker_and_cancels_without_retaining_audio(self):
        w=self.window(Config());entered=threading.Event()
        class Recorder:
            input_level=.4
            def __init__(self,*args):self.full=threading.Event()
            def start(self):entered.set()
            def stop(self):return b'\0\1'*2000
            def discard(self):pass
        with patch('localflow.audio.Recorder',Recorder):
            w.test_microphone();self.assertTrue(entered.wait(1));self.assertEqual(w.state,'audio_testing')
            w.abort();self.assertEqual(w.state,'stopping_audio');w.utility_pool.waitForDone(1000);self.app.processEvents()
            self.assertEqual(w.state,'idle');self.assertIsNone(w.recorder)
            self.assertEqual(w.preview.toPlainText(),'')

    def test_setup_sample_is_real_preview_recording_without_insertion_target(self):
        w=self.window(Config());w.ui.open_onboarding();w.ui.setup_step(3)
        recorder=Mock(data=bytearray(),full=threading.Event())
        with patch('localflow.app.Recorder',return_value=recorder):w.ui.setup_sample.click()
        self.assertEqual(w.state,'recording');self.assertIsNone(w.target)
        recorder.start.assert_called_once();w.abort();recorder.discard.assert_called_once()

    def test_timing_summary_retains_no_transcript_and_clears_with_result(self):
        w=self.window(Config())
        result=dict(text='Sample.',raw='sample',review=True,cpu_fallback=False,gpu_used=False,total_ms=123)
        w.finished(w.generation,result);w.ui.refresh()
        self.assertEqual(w.last_metrics,{'total_ms':123,'gpu_used':False,'cpu_fallback':False})
        self.assertIn('123',w.ui.performance_summary.text())
        w.clear_text();self.assertEqual(w.last_metrics,{})


if __name__=='__main__':unittest.main()
