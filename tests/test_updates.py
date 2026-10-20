"""Update checks use synthetic metadata/installers; no live installation here."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from localflow.updates import GitHubUpdates,UpdateError,UpdateCancelled,select_update,version_key,REPOSITORY
from localflow.update_handoff import helper_command


def release(tag='v1.0.1',data=b'installer',prerelease=False,source_only=False):
    version=tag.removeprefix('v');name='Vowely-'+version+'-Setup-x64.exe'
    base='https://github.com/'+REPOSITORY+'/releases/download/'+tag+'/'
    assets=[] if source_only else [dict(name=name,state='uploaded',size=len(data),browser_download_url=base+name,digest='sha256:'+hashlib.sha256(data).hexdigest()),
        dict(name='SHA256SUMS.txt',state='uploaded',size=100,browser_download_url=base+'SHA256SUMS.txt')]
    return dict(tag_name=tag,body='Synthetic release notes.',draft=False,prerelease=prerelease,assets=assets)


class Response(io.BytesIO):
    status=200
    headers={}
    def __init__(self,data,url='https://github.com/DaksheshGautam/vowely/releases/download/v1.0.1/file'):
        super().__init__(data);self.url=url
    def geturl(self):return self.url


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()

    def update(self):return select_update([release()],'1.0.0',False)
    def checksum(self,u):return (hashlib.sha256(b'installer').hexdigest()+'  '+u.name+'\n').encode()

    def test_semantic_order_ignores_github_order_and_retroactive_publication(self):
        rows=[release('v0.1.0-alpha.9',prerelease=True),release('v0.1.0-alpha.12',prerelease=True),release('v0.1.0-alpha.11',prerelease=True),release('v1.0.0-beta.1',prerelease=True)]
        self.assertEqual(select_update(rows,'0.1.0-alpha.8',True).version,'1.0.0-beta.1')
        self.assertIsNone(select_update(rows,'1.0.0-beta.1',True))
        self.assertLess(version_key('1.0.0-beta.9'),version_key('1.0.0-beta.10'))
        self.assertLess(version_key('1.0.0-rc.1'),version_key('v1'))

    def test_prereleases_are_opt_in_and_downgrades_are_never_selected(self):
        rows=[release('v2.0.0-beta.1',prerelease=True),release('v1.0.1')]
        self.assertEqual(select_update(rows,'1.0.0',False).version,'1.0.1')
        self.assertEqual(select_update(rows,'1.0.0',True).version,'2.0.0-beta.1')
        self.assertIsNone(select_update(rows,'3.0.0',True))

    def test_drafts_historical_source_only_and_mislabeled_versions_are_ignored(self):
        draft=release('v2.0.0');draft['draft']=True
        self.assertIsNone(select_update([draft,release('v3.0.0',source_only=True),release('v4.0.0-beta.1')],'1.0.0',True))

    def test_asset_url_origin_size_and_name_must_match_release(self):
        for change in ('url','size','name','duplicate','digest'):
            row=release()
            if change=='url':row['assets'][0]['browser_download_url']='https://example.invalid/evil.exe'
            if change=='size':row['assets'][0]['size']=10**10
            if change=='name':row['assets'][0]['name']='Vowely-9.0.0-Setup-x64.exe'
            if change=='duplicate':row['assets'].append(row['assets'][0].copy())
            if change=='digest':row['assets'][0]['digest']='sha256:invalid'
            self.assertIsNone(select_update([row],'1.0.0',True),change)

    def test_metadata_pagination_searches_beyond_first_page(self):
        first=[release('v0.1.0',source_only=True)]*100;engine=GitHubUpdates()
        with patch.object(engine,'read',side_effect=[json.dumps(first).encode(),json.dumps([release()]).encode()]) as read:
            self.assertEqual(engine.check('1.0.0',False).version,'1.0.1')
        self.assertEqual(read.call_count,2)

    def test_metadata_is_bounded_and_never_uses_credentials(self):
        engine=GitHubUpdates()
        with patch('urllib.request.urlopen',return_value=Response(b'x'*20)) as network,self.assertRaises(UpdateError):engine.read('https://api.github.com/test',10)
        self.assertNotIn('Authorization',network.call_args.args[0].headers)

    def test_offsite_requests_and_redirects_are_blocked(self):
        with patch('urllib.request.urlopen') as network,self.assertRaises(UpdateError):GitHubUpdates().read('https://example.invalid/evil',20)
        network.assert_not_called()
        with patch('urllib.request.urlopen',return_value=Response(b'ok','http://github.com/file')),self.assertRaises(UpdateError):GitHubUpdates().read('https://github.com/file',20)

    def test_download_is_checked_against_checksum_and_github_digest(self):
        u=self.update();engine=GitHubUpdates()
        with patch('urllib.request.urlopen',side_effect=[Response(self.checksum(u)),Response(b'installer')]):
            path,sha=engine.download(u,self.root)
        self.assertEqual(path.read_bytes(),b'installer');self.assertEqual(sha,hashlib.sha256(b'installer').hexdigest())

    def test_cached_verified_installer_is_reused(self):
        u=self.update();(self.root/u.name).write_bytes(b'installer');engine=GitHubUpdates()
        with patch('urllib.request.urlopen',return_value=Response(self.checksum(u))) as network:engine.download(u,self.root)
        self.assertEqual(network.call_count,1)

    def test_checksum_disagreement_and_corrupt_download_never_install(self):
        u=self.update();engine=GitHubUpdates()
        with patch('urllib.request.urlopen',return_value=Response(('0'*64+'  '+u.name).encode())),self.assertRaises(UpdateError):engine.download(u,self.root)
        self.assertFalse((self.root/u.name).exists())
        with patch('urllib.request.urlopen',side_effect=[Response(self.checksum(u)),Response(b'bad-bytes')]),self.assertRaises(UpdateError):engine.download(u,self.root)
        self.assertFalse((self.root/u.name).exists())

    def test_resume_checks_exact_range_and_rechecks_complete_hash(self):
        u=self.update();(self.root/(u.name+'.part')).write_bytes(b'ins')
        response=Response(b'taller');response.status=206;response.headers={'Content-Range':'bytes 3-8/9'}
        with patch('urllib.request.urlopen',side_effect=[Response(self.checksum(u)),response]) as network:
            path,_=GitHubUpdates().download(u,self.root)
        self.assertEqual(path.read_bytes(),b'installer');self.assertEqual(network.call_args.args[0].headers['Range'],'bytes=3-')

    def test_cancel_never_downloads_or_runs_an_installer(self):
        stop=threading.Event();stop.set()
        with patch('urllib.request.urlopen') as network,self.assertRaises(UpdateCancelled):GitHubUpdates(stop).download(self.update(),self.root)
        network.assert_not_called()

    def test_duplicate_checksum_lines_are_rejected(self):
        u=self.update()
        with patch('urllib.request.urlopen',return_value=Response(self.checksum(u)*2)),self.assertRaises(UpdateError):GitHubUpdates().download(u,self.root)

    def test_helper_uses_original_directory_and_quotes_paths_without_policy_bypass(self):
        app=self.root/'App with spaces'/"Vowely.exe";app.parent.mkdir();app.touch()
        (app.parent/'installed-layout.json').write_text(json.dumps({'schema':1,'application':'Vowely'}))
        cache=self.root/'updates';cache.mkdir();installer=cache/"Vowely-o'neil.exe";installer.touch()
        command=helper_command(123,installer,'a'*64,app,self.root,'1.0.1')
        text=base64.b64decode(command[-1]).decode('utf-16-le')
        self.assertIn("o''neil.exe",text);self.assertIn('WaitForExit(90000)',text);self.assertIn('SHA256]::Create()',text)
        self.assertIn('/DIR=',text);self.assertIn('3010',text);self.assertNotIn('ExecutionPolicy',text)
        with self.assertRaises(ValueError):helper_command(123,self.root/'outside.exe','a'*64,app,self.root,'1.0.1')

    def test_portable_copy_cannot_silently_change_installation_target(self):
        with self.assertRaises(ValueError):helper_command(123,self.root/'updates/setup.exe','a'*64,self.root/'Vowely.exe',self.root,'1.0.1')


if os.name=='nt':
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication,QTextEdit,QMessageBox
    from PySide6.QtCore import QCoreApplication,QEvent
    from localflow.update_ui import UpdatePanel,UpdateNotice


@unittest.skipUnless(os.name=='nt','Windows Qt checks')
class UpdateUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.preview=QTextEdit();self.window=SimpleNamespace(root=self.root,state='idle',quitting=False,preview=self.preview,quit=Mock())
        self.notice=UpdateNotice(self.window);self.panel=UpdatePanel(self.window,self.notice)
        self.window.updates=self.panel
        self.panel.candidate=select_update([release('v9.0.0')],'1.0.0',False)
    def tearDown(self):
        self.panel.shutdown();self.panel.pool.waitForDone(3000);self.app.processEvents()
        self.panel.close();self.preview.close();self.notice.close();self.panel.deleteLater();self.preview.deleteLater();self.notice.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);self.app.processEvents();self.tmp.cleanup()

    def test_constructing_panel_never_contacts_network(self):
        self.assertFalse(self.panel.busy);self.assertEqual(self.panel.preferences['last_attempt'],0)
        self.assertFalse(self.panel.auto_timer.isActive())

    def test_check_runs_outside_gui_thread_and_does_not_touch_dictation(self):
        threads=[];main=threading.get_ident();candidate=select_update([release('v9.0.0')],'1.0.0',False)
        def check(*args):threads.append(threading.get_ident());return candidate
        with patch('localflow.update_ui.GitHubUpdates.check',side_effect=check):
            self.panel.check();self.panel.pool.waitForDone(3000);self.app.processEvents()
        self.assertNotEqual(threads,[main]);self.assertEqual(self.panel.candidate,candidate);self.window.quit.assert_not_called();self.assertEqual(self.window.state,'idle')

    def test_auto_checks_wait_for_idle_and_obey_daily_interval(self):
        self.window.state='recording'
        with patch.object(self.panel,'check') as check:
            self.panel.automatic_check();check.assert_not_called()
            self.window.state='idle';self.panel.preferences['last_attempt']=time.time();self.panel.automatic_check();check.assert_not_called()
            self.panel.preferences['last_attempt']=0;self.panel.automatic_check();check.assert_called_once_with(False)

    def test_automatic_checks_can_be_disabled_and_preferences_contain_no_text(self):
        self.preview.setPlainText('Private current result')
        self.panel.automatic.setChecked(False)
        with patch.object(self.panel,'check') as check:self.panel.automatic_check();check.assert_not_called()
        data=(self.root/'update-settings.json').read_text();self.assertNotIn('Private',data);self.assertNotIn('microphone',data)

    def test_current_result_restart_requires_confirmation(self):
        self.panel.installable=True;self.panel.cached=(self.root/'setup.exe','a'*64);self.preview.setPlainText('Unsaved result')
        with patch('localflow.update_ui.QMessageBox.question',return_value=QMessageBox.Cancel),patch.object(self.panel,'launch_job') as job:
            self.panel.install();job.assert_not_called()
        self.window.quit.assert_not_called()

    def test_empty_result_also_requires_confirmation_and_cancel_prevents_install(self):
        self.panel.installable=True;self.panel.cached=(self.root/'setup.exe','a'*64)
        with patch('localflow.update_ui.QMessageBox.question',return_value=QMessageBox.Cancel) as confirm,patch.object(self.panel,'launch_job') as job:
            self.panel.install();confirm.assert_called_once();job.assert_not_called()
        self.window.quit.assert_not_called()

    def test_confirmed_install_verifies_then_rechecks_idle_after_dialog(self):
        self.panel.installable=True;self.panel.cached=(self.root/'setup.exe','a'*64)
        with patch('localflow.update_ui.QMessageBox.question',return_value=QMessageBox.Yes),patch.object(self.panel,'launch_job') as job:
            self.panel.install();self.assertEqual(job.call_args.args[0],'verify')
        def start_recording(*args):self.window.state='recording';return QMessageBox.Yes
        with patch('localflow.update_ui.QMessageBox.question',side_effect=start_recording),patch.object(self.panel,'launch_job') as job:
            self.panel.install();job.assert_not_called()

    def test_available_update_notifies_once_without_downloading_or_raising_window(self):
        self.window.tray=Mock();self.window.reveal=Mock();self.panel.kind='check';candidate=self.panel.candidate
        with patch('localflow.update_ui.QSystemTrayIcon.supportsMessages',return_value=True),patch.object(self.panel,'download') as download:
            self.panel.completed(candidate);self.panel.completed(candidate)
        self.window.tray.showMessage.assert_called_once();download.assert_not_called();self.window.reveal.assert_not_called()
        self.assertFalse(self.notice.isHidden());self.assertIn('Download',self.notice.action.text())
        self.assertEqual(json.loads((self.root/'update-settings.json').read_text())['notified_version'],candidate.version)

    def test_notification_unavailable_keeps_bottom_left_action_and_does_not_mark_notified(self):
        self.window.tray=Mock();self.panel.kind='check'
        with patch('localflow.update_ui.QSystemTrayIcon.supportsMessages',return_value=False):self.panel.completed(self.panel.candidate)
        self.window.tray.showMessage.assert_not_called();self.assertFalse(self.notice.isHidden())
        self.assertEqual(self.panel.preferences['notified_version'],'')

    def test_bottom_left_action_downloads_then_offers_confirmed_idle_install(self):
        self.panel.refresh()
        with patch.object(self.panel,'download') as download:self.notice.action.click();download.assert_called_once()
        self.panel.installable=True;self.panel.cached=(self.root/'setup.exe','a'*64);self.panel.refresh()
        self.assertEqual(self.notice.action.text(),'Install and restart')
        with patch.object(self.panel,'show_details') as details,patch.object(self.panel,'install') as install:
            self.notice.action.click();details.assert_called_once();install.assert_called_once()
        self.window.state='recording';self.panel.refresh();self.assertFalse(self.notice.action.isEnabled())
        self.window.state='idle';self.panel.refresh();self.assertTrue(self.notice.action.isEnabled())

    def test_compact_action_keeps_accessible_download_and_channel_changes_clear_notice(self):
        self.notice.set_compact(True);self.panel.refresh()
        self.assertEqual(self.notice.action.text(),'↓');self.assertIn('Download update',self.notice.action.accessibleName())
        self.assertTrue(self.notice.title.isHidden());self.panel.channel_changed();self.assertTrue(self.notice.isHidden())

    def test_download_errors_keep_retry_action_and_never_start_install(self):
        self.panel.kind='download';self.panel.failed('Connection interrupted')
        self.assertFalse(self.notice.isHidden());self.assertIn('paused',self.notice.status.text())
        self.assertTrue(self.notice.action.isEnabled());self.window.quit.assert_not_called()

    def test_held_recording_prevents_install_even_if_downloaded(self):
        self.panel.installable=True;self.panel.cached=(self.root/'setup.exe','a'*64);self.window.state='recording'
        with patch.object(self.panel,'launch_job') as job:self.panel.install();job.assert_not_called()

    def test_handoff_failure_keeps_app_open(self):
        self.panel.kind='verify';self.panel.candidate=select_update([release('v9.0.0')],'1.0.0',False)
        with patch('localflow.update_ui.start_handoff',side_effect=OSError('Unavailable')):
            self.panel.completed((self.root/'setup.exe','a'*64))
        self.window.quit.assert_not_called();self.assertIn('Unavailable',self.panel.status.text())

    def test_successful_handoff_quits_only_after_helper_starts(self):
        self.panel.kind='verify';self.panel.candidate=select_update([release('v9.0.0')],'1.0.0',False)
        with patch('localflow.update_ui.start_handoff') as handoff:
            self.panel.completed((self.root/'setup.exe','a'*64));handoff.assert_called_once()
        self.window.quit.assert_called_once();self.assertEqual(self.window.state,'updating')
