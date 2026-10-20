from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from localflow import launcher
from localflow.version import RELEASE_VERSION


class ReleaseTests(unittest.TestCase):
    def test_explicit_setup_wizard_never_starts_dictation_or_downloads_by_itself(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(sys,'argv',['vowely','--setup-wizard','--root',str(root),'--manifest',str(root/'assets.json')]),patch('localflow.setup_ui.run',return_value=0) as wizard,patch('localflow.app.main') as app,patch('urllib.request.urlopen') as network:
                self.assertEqual(launcher.main(),0)
            wizard.assert_called_once_with(root.resolve(),root/'assets.json');app.assert_not_called();network.assert_not_called()

    def test_incomplete_installed_launch_opens_setup_without_downloading(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(sys,'argv',['vowely','--root',str(root)]),patch.object(sys,'frozen',True,create=True),patch('localflow.installation.installed',return_value=True),patch('localflow.setup_ui.run',return_value=0) as wizard,patch('urllib.request.urlopen') as network:
                self.assertEqual(launcher.main(),0)
            wizard.assert_called_once();network.assert_not_called()
    def test_version_flag_does_not_start_ui_or_provision(self):
        output = io.StringIO()
        with patch.object(sys,'argv',['vowely','--version']),redirect_stdout(output),patch('localflow.provision.main') as setup:
            self.assertEqual(launcher.main(),0)
        setup.assert_not_called()
        self.assertEqual(output.getvalue().strip(),RELEASE_VERSION)

    def test_ordinary_launch_cannot_download_assets(self):
        with patch.object(sys,'argv',['vowely']),patch('localflow.app.main',return_value=0) as app,patch('localflow.provision.main') as setup:
            self.assertEqual(launcher.main(),0)
        app.assert_called_once()
        setup.assert_not_called()

    def test_explicit_setup_logs_metadata_and_passes_only_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            log = root/'setup.log'
            with patch.object(sys,'argv',['vowely','--root',str(root),'--provision-assets','--setup-log',str(log)]),patch('localflow.provision.main') as setup:
                self.assertEqual(launcher.main(),0)
            setup.assert_called_once_with(['--root',str(root.resolve())])
            self.assertTrue(log.exists())

    def test_setup_failure_returns_failure_instead_of_opening_microphone(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            log = root/'setup.log'
            with patch.object(sys,'argv',['vowely','--root',str(root),'--provision-assets','--setup-log',str(log)]),patch('localflow.provision.main',side_effect=RuntimeError('Checksum mismatch')):
                self.assertEqual(launcher.main(),1)
            self.assertIn('Checksum mismatch',log.read_text())


if __name__=='__main__': unittest.main()
