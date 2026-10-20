"""Installer/setup checks use tiny synthetic files, no external downloads."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch,Mock
import zipfile

from localflow.asset_setup import AssetSetup,SetupCancelled,selected_assets
from localflow.config import Config
from localflow.installation import installed,default_root,needs_assets


def asset(data=b'model',name='model.bin',kind='model',destination='models/model.bin'):
    return dict(kind=kind,name=name,destination=destination,url='https://example.invalid/model',
                size=len(data),sha256=hashlib.sha256(data).hexdigest())


class Response(io.BytesIO):
    status=200
    headers={}
    def geturl(self):return 'https://example.invalid/model'


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'target';self.root.mkdir()
        self.reuse=Path(self.tmp.name)/'old';self.reuse.mkdir()
    def tearDown(self):self.tmp.cleanup()
    def setup(self,assets,**kw):return AssetSetup(self.root,{'assets':assets},**kw)

    def test_selection_always_includes_models_and_cpu_only_by_default(self):
        paths=['vendor/whisper','vendor/llama','vendor/whisper-cuda','vendor/cuda-runtime',
               'vendor/llama-cuda','vendor/llama-cuda-runtime','models/ggml-base.bin',
               'models/ggml-small.bin','models/Qwen3-1.7B-Q4_K_M.gguf','models/ggml-silero-v6.2.0.bin','samples/jfk.wav']
        manifest={'assets':[asset(destination=p) for p in paths]}
        basic=[a['destination'] for a in selected_assets(manifest)]
        self.assertEqual(len(basic),6);self.assertNotIn('vendor/whisper-cuda',basic)
        self.assertEqual(len(selected_assets(manifest,True,True)),10)

    def test_existing_verified_model_never_opens_network(self):
        a=asset();p=self.root/a['destination'];p.parent.mkdir();p.write_bytes(b'model')
        with patch('urllib.request.urlopen') as network:self.assertEqual(self.setup([a]).install_asset(a),'existing')
        network.assert_not_called()

    def test_reuse_copies_only_verified_file_and_preserves_source(self):
        a=asset();p=self.reuse/a['destination'];p.parent.mkdir();p.write_bytes(b'model')
        with patch('urllib.request.urlopen') as network:self.assertEqual(self.setup([a],reuse=self.reuse).install_asset(a),'reused')
        network.assert_not_called();self.assertEqual(p.read_bytes(),b'model');self.assertEqual((self.root/a['destination']).read_bytes(),b'model')

    def test_existing_different_model_is_never_overwritten(self):
        a=asset();p=self.root/a['destination'];p.parent.mkdir();p.write_bytes(b'private')
        with patch('urllib.request.urlopen') as network,self.assertRaisesRegex(RuntimeError,'preserved'):self.setup([a]).install_asset(a)
        network.assert_not_called();self.assertEqual(p.read_bytes(),b'private')

    def test_missing_model_downloads_and_verifies(self):
        a=asset()
        with patch('urllib.request.urlopen',return_value=Response(b'model')) as network:
            self.assertEqual(self.setup([a]).install_asset(a),'downloaded')
        network.assert_called_once();self.assertEqual((self.root/a['destination']).read_bytes(),b'model')

    def test_corrupt_download_is_not_installed_and_retry_starts_fresh(self):
        a=asset();target=self.root/a['destination']
        with patch('urllib.request.urlopen',return_value=Response(b'wrong')),self.assertRaisesRegex(RuntimeError,'checksum'):
            self.setup([a]).install_asset(a)
        self.assertFalse(target.exists())
        with patch('urllib.request.urlopen',return_value=Response(b'model')):self.setup([a]).install_asset(a)
        self.assertEqual(target.read_bytes(),b'model');self.assertTrue(list(target.parent.glob('*.bad-*')))

    def test_resume_validates_content_range_and_appends(self):
        a=asset();target=self.root/a['destination'];target.parent.mkdir();target.with_suffix('.bin.part').write_bytes(b'mo')
        response=Response(b'del');response.status=206;response.headers={'Content-Range':'bytes 2-4/5'}
        with patch('urllib.request.urlopen',return_value=response) as network:self.setup([a]).install_asset(a)
        self.assertEqual(network.call_args.args[0].headers['Range'],'bytes=2-');self.assertEqual(target.read_bytes(),b'model')

    def test_invalid_resume_range_does_not_append(self):
        a=asset();target=self.root/a['destination'];target.parent.mkdir();partial=target.with_suffix('.bin.part');partial.write_bytes(b'mo')
        response=Response(b'del');response.status=206;response.headers={'Content-Range':'bytes 0-4/5'}
        with patch('urllib.request.urlopen',return_value=response),self.assertRaisesRegex(RuntimeError,'resume range'):self.setup([a]).install_asset(a)
        self.assertEqual(partial.read_bytes(),b'mo')

    def test_pre_cancelled_setup_does_not_open_network(self):
        stop=threading.Event();stop.set()
        with patch('urllib.request.urlopen') as network,self.assertRaises(SetupCancelled):self.setup([asset()],cancel=stop).install_asset(asset())
        network.assert_not_called()

    def test_insecure_url_and_path_escape_are_rejected(self):
        a=asset(destination='../escape.bin')
        with self.assertRaises(ValueError):self.setup([a]).install_asset(a)
        a=asset();a['url']='http://example.invalid/file'
        with self.assertRaises(ValueError):self.setup([a]).install_asset(a)

    def test_archive_traversal_rejected_before_any_file_is_written(self):
        archive=self.root/'test.zip'
        with zipfile.ZipFile(archive,'w') as bundle:bundle.writestr('valid.dll',b'ok');bundle.writestr('../escape.dll',b'bad')
        a=asset(kind='archive',destination='vendor/engine')
        with self.assertRaises(ValueError):self.setup([a]).unpack(a,archive)
        self.assertFalse((self.root/'vendor').exists())

    def test_engine_index_skips_download_when_extracted_files_match(self):
        a=asset(kind='archive',name='cpu.zip',destination='vendor/engine')
        p=self.root/'vendor/engine/engine.exe';p.parent.mkdir(parents=True);p.write_bytes(b'engine')
        files={'cpu.zip':{'vendor/engine/engine.exe':hashlib.sha256(b'engine').hexdigest()}}
        with patch('urllib.request.urlopen') as network:self.assertEqual(self.setup([a],files=files).install_asset(a),'existing')
        network.assert_not_called()

    def test_layout_preserves_portable_root_and_separates_installed_data(self):
        exe=self.root/'app/Vowely/Vowely.exe';exe.parent.mkdir(parents=True);exe.touch()
        self.assertEqual(default_root(exe),self.root)
        (exe.parent/'installed-layout.json').write_text(json.dumps({'schema':1,'application':'Vowely'}))
        with patch.dict(os.environ,{'LOCALAPPDATA':str(self.reuse)}):
            self.assertTrue(installed(exe));self.assertEqual(default_root(exe),self.reuse/'Vowely')

    def test_app_local_native_runtime_is_verified_and_does_not_change_path(self):
        runtime=self.reuse/'runtime';runtime.mkdir();(runtime/'test.dll').write_bytes(b'runtime')
        files={'__runtime__':{'test.dll':hashlib.sha256(b'runtime').hexdigest()}}
        before=os.environ.get('PATH')
        self.setup([],files=files,runtime=runtime).run()
        self.assertEqual((self.root/'vendor/llama/test.dll').read_bytes(),b'runtime')
        self.assertEqual((self.root/'vendor/whisper/Release/test.dll').read_bytes(),b'runtime')
        self.assertEqual(os.environ.get('PATH'),before)

    def test_installer_staging_rejects_local_profiles_before_copying(self):
        import importlib.util
        script=Path(__file__).resolve().parents[1]/'scripts/build_installer.py'
        spec=importlib.util.spec_from_file_location('installer_builder',script);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        bundle=self.reuse/'bundle';bundle.mkdir();(bundle/'Vowely.exe').touch();(bundle/'dictionary.json').write_text('{}')
        stage=self.root/'stage'
        with self.assertRaisesRegex(RuntimeError,'personal/model'):module.stage(self.reuse,bundle,stage)
        self.assertFalse(stage.exists())

    def test_incomplete_setup_never_bypasses_explicit_setup_screen(self):
        self.assertTrue(needs_assets(self.root))
        (self.root/'setup-state.json').write_text(json.dumps({'complete':True}))
        self.assertTrue(needs_assets(self.root))
        for name in (Config().base_model,Config().whisper_exe):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
        self.assertFalse(needs_assets(self.root))


if os.name=='nt':
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from localflow.setup_ui import SetupWindow,finish_configuration


@unittest.skipUnless(os.name=='nt','Windows setup UI')
class SetupUiTests(unittest.TestCase):
    setUp=InstallerTests.setUp
    tearDown=InstallerTests.tearDown
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_new_config_has_no_personal_values_and_existing_config_is_preserved(self):
        finish_configuration(self.root,None,False,False,False)
        c=Config.load(self.root/'config.json');self.assertTrue(c.cleanup_enabled);self.assertTrue(c.streaming_enabled)
        self.assertEqual(c.personal_vocabulary,[]);self.assertIsNone(c.microphone)
        before=(self.root/'config.json').read_bytes();finish_configuration(self.root,None,False,True,True)
        self.assertEqual((self.root/'config.json').read_bytes(),before)

    def test_import_requires_explicit_choice_and_does_not_change_original(self):
        Config(threads=3,hotkey='Ctrl+Shift+F8').save(self.reuse/'config.json')
        from localflow.learning import LearnedDictionary
        LearnedDictionary(self.reuse/'dictionary.json').add(['SyntheticTerm'])
        finish_configuration(self.root,self.reuse,True,False,False)
        self.assertEqual(Config.load(self.root/'config.json').threads,3)
        self.assertEqual((self.reuse/'dictionary.json').read_bytes(),(self.root/'dictionary.json').read_bytes())

    def test_setup_is_idle_until_start_and_worker_runs_off_qt(self):
        p=self.root/'assets-manifest.json';p.write_text(json.dumps({'assets':[]}))
        w=SetupWindow(self.root,p,launch=False);self.addCleanup(w.close)
        with patch('localflow.setup_ui.AssetSetup.run',return_value={}) as install:
            self.assertFalse(w.busy);install.assert_not_called()
            w.start_setup();w.pool.waitForDone(2000);self.app.processEvents();install.assert_called_once()
        self.assertTrue(w.complete);self.assertTrue((self.root/'setup-state.json').exists())

    def test_cancel_error_can_be_retried_without_losing_controls(self):
        p=self.root/'assets-manifest.json';p.write_text(json.dumps({'assets':[]}))
        w=SetupWindow(self.root,p,launch=False);self.addCleanup(w.close)
        with patch('localflow.setup_ui.AssetSetup.run',side_effect=SetupCancelled('Cancelled')):
            w.start_setup();w.cancel_or_close();w.pool.waitForDone(2000);self.app.processEvents()
        self.assertTrue(w.start.isEnabled());self.assertTrue(w.stop.isEnabled());self.assertFalse(w.complete)
