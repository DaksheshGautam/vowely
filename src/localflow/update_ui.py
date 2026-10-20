"""Nonblocking update controls, independent of capture and inference workers."""
import json
import os
from pathlib import Path
import sys
import threading
import time

from PySide6.QtCore import QObject,QRunnable,QThreadPool,QTimer,Signal,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QCheckBox,QPushButton,QTextEdit,QProgressBar,QMessageBox

from .installation import installed
from .updates import GitHubUpdates,UpdateCancelled,RELEASES,release_url
from .update_handoff import start_handoff
from .version import RELEASE_VERSION


def load_preferences(path):
    result={'automatic':True,'prereleases':'-' in RELEASE_VERSION,'last_attempt':0,'last_checked':0}
    try:
        if path.stat().st_size>8192:return result
        values=json.loads(path.read_text(encoding='utf-8'))
        for key in ('automatic','prereleases'):
            if type(values.get(key)) is bool:result[key]=values[key]
        for key in ('last_attempt','last_checked'):
            if type(values.get(key)) in (int,float) and 0<=values[key]<=time.time()+300:result[key]=values[key]
    except (OSError,ValueError,TypeError,AttributeError):pass
    return result


class Signals(QObject):
    done=Signal(object)
    error=Signal(str)
    progress=Signal(int,int)


class UpdateJob(QRunnable):
    def __init__(self,function):super().__init__();self.function=function;self.signals=Signals()
    def run(self):
        try:self.signals.done.emit(self.function(self.signals))
        except Exception as error:self.signals.error.emit(str(error) or type(error).__name__)


class UpdatePanel(QWidget):
    def __init__(self,window):
        super().__init__();self.w=window;self.preferences_path=window.root/'update-settings.json'
        self.preferences=load_preferences(self.preferences_path)
        self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1)
        self.cancel=threading.Event();self.busy=False;self.candidate=None;self.cached=None;self.stopping=False
        body=QVBoxLayout(self);body.setContentsMargins(0,4,0,4);body.setSpacing(14)
        def label(text):
            item=QLabel(text);item.setWordWrap(True);body.addWidget(item);return item
        heading=label('Updates');heading.setProperty('role','heading')
        label('Installed version · '+RELEASE_VERSION)
        self.automatic=QCheckBox('Check GitHub automatically once a day when Vowely is idle');self.automatic.setChecked(self.preferences['automatic']);body.addWidget(self.automatic)
        self.prereleases=QCheckBox('Include beta, RC and alpha prereleases');self.prereleases.setChecked(self.preferences['prereleases']);body.addWidget(self.prereleases)
        self.automatic.toggled.connect(self.save_preferences);self.prereleases.toggled.connect(self.channel_changed)
        label('Checks contact the public Vowely GitHub repository. No audio, transcripts, dictionary, settings or device details are uploaded. Downloads and installation always require your action. Dictation and models remain local.')
        self.status=label('Check for updates when you’re ready.');self.status.setAccessibleName('Update status')
        self.available=label('');self.notes=QTextEdit();self.notes.setReadOnly(True);self.notes.setAcceptRichText(False);self.notes.setMinimumHeight(160);self.notes.setAccessibleName('Release notes')
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0)
        row=QHBoxLayout();self.check_button=QPushButton('Check for updates');self.check_button.clicked.connect(lambda:self.check(True));row.addWidget(self.check_button)
        self.download_button=QPushButton('Download update');self.download_button.clicked.connect(self.download);row.addWidget(self.download_button)
        self.cancel_button=QPushButton('Cancel download/check');self.cancel_button.clicked.connect(self.cancel_operation);row.addWidget(self.cancel_button);body.addLayout(row)
        self.install_button=QPushButton('Install update and restart');self.install_button.setProperty('primary',True);self.install_button.clicked.connect(self.install);body.addWidget(self.install_button)
        body.addWidget(self.progress);body.addWidget(self.notes)
        row=QHBoxLayout();self.release_button=QPushButton('View release on GitHub');self.release_button.clicked.connect(self.open_release);row.addWidget(self.release_button)
        self.folder_button=QPushButton('Open download folder');self.folder_button.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.w.root/'updates'))));row.addWidget(self.folder_button);body.addLayout(row)
        self.installable=bool(getattr(sys,'frozen',False) and installed(sys.executable))
        label('Install and restart is available in the installed Windows app. Portable/source copies can download the installer and open the download folder to migrate. Updates preserve the separate models, settings and vocabulary folder. The app and installer are currently unsigned.')
        self.last_check=label('');body.addStretch()
        self.auto_timer=QTimer(self);self.auto_timer.setInterval(30000);self.auto_timer.timeout.connect(self.automatic_check)
        try:
            result=json.loads((self.w.root/'updates/update-status.json').read_text(encoding='utf-8'))
            if result.get('stage') in ('failed','complete','reboot_required'):self.status.setText(str(result.get('message',''))[:1000])
        except (OSError,ValueError,AttributeError):pass
        self.refresh()

    def save_preferences(self):
        self.preferences.update(automatic=self.automatic.isChecked(),prereleases=self.prereleases.isChecked())
        try:
            self.preferences_path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.preferences_path.with_suffix('.tmp');temp.write_text(json.dumps(self.preferences,indent=2),encoding='utf-8');temp.replace(self.preferences_path)
        except OSError:self.status.setText('Could not save update preferences. You can still check manually.')

    def channel_changed(self):
        self.candidate=None;self.cached=None;self.available.clear();self.notes.clear();self.save_preferences();self.refresh()
        if hasattr(self.w,'tray_updates'):self.w.tray_updates.setText('Check for updates')

    def automatic_check(self):
        if self.stopping or not self.automatic.isChecked() or self.busy:return
        if self.w.state!='idle' or self.w.quitting:return
        if time.time()-self.preferences['last_attempt']<86400:return
        self.check(False)

    def start(self):
        self.auto_timer.start()
        QTimer.singleShot(15000,self.automatic_check)

    def launch_job(self,kind,function):
        self.busy=True;self.cancel=threading.Event();self.kind=kind
        self.job=UpdateJob(function);self.job.signals.done.connect(self.completed);self.job.signals.error.connect(self.failed);self.job.signals.progress.connect(self.download_progress)
        self.pool.start(self.job);self.refresh()

    def check(self,manual=True):
        if self.busy or self.stopping:return
        self.candidate=None;self.cached=None;self.available.clear();self.notes.clear();self.preferences['last_attempt']=time.time();self.save_preferences()
        self.status.setText('Checking public GitHub releases…');self.progress.setRange(0,0)
        include=self.prereleases.isChecked()
        self.launch_job('check',lambda signals:GitHubUpdates(self.cancel).check(RELEASE_VERSION,include))

    def download(self):
        if self.busy or not self.candidate or self.stopping:return
        candidate=self.candidate;self.status.setText('Downloading and verifying the update…');self.progress.setRange(0,100);self.progress.setValue(0)
        self.launch_job('download',lambda signals:GitHubUpdates(self.cancel,signals.progress.emit).download(candidate,self.w.root/'updates'))

    def download_progress(self,current,total):
        if self.stopping:return
        self.progress.setRange(0,100);self.progress.setValue(round(current/total*100))
        self.status.setText(f'Downloading update · {current/1_000_000:.1f} / {total/1_000_000:.1f} MB')

    def completed(self,result):
        self.busy=False
        if self.stopping:return
        self.progress.setRange(0,100)
        if self.kind=='check':
            self.preferences['last_checked']=time.time();self.save_preferences();self.candidate=result
            if result:
                self.status.setText('Update available. Review the notes, then download when ready.')
                self.available.setText(result.version+f' · Windows x64 · {result.size/1_000_000:.1f} MB');self.notes.setPlainText(result.notes)
                if hasattr(self.w,'tray_updates'):self.w.tray_updates.setText('Update available · '+result.version)
            else:self.status.setText('You’re up to date. No newer installable release was found in the selected channel.')
            if not result and hasattr(self.w,'tray_updates'):self.w.tray_updates.setText('Check for updates')
            self.progress.setValue(0)
        elif self.kind=='download':
            self.cached=result;self.progress.setValue(100);self.status.setText('Installer verified. Install when dictation is idle; Vowely will close and reopen.')
        elif self.kind=='verify':
            if self.w.state!='idle':self.status.setText('Finish the current dictation or model operation, then choose Install again.');self.refresh();return
            try:
                path,sha=result
                start_handoff(os.getpid(),path,sha,sys.executable,self.w.root,self.candidate.version)
            except Exception as error:self.status.setText('Could not start the installer: '+str(error));self.refresh();return
            self.w.state='updating';self.status.setText('Restarting to install the update…');self.w.quit()
        self.refresh()

    def failed(self,message):
        self.busy=False
        if not self.stopping:self.progress.setRange(0,100);self.status.setText(message+' You can retry.');self.refresh()

    def install(self):
        if self.busy or not self.cached or not self.installable or self.w.state!='idle' or self.stopping:return
        if self.w.preview.toPlainText().strip():
            answer=QMessageBox.question(self.w,'Install update','Vowely must restart. The current dictation result will be cleared. Copy it first if needed. Install now?',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)
            if answer!=QMessageBox.Yes:return
        path,sha=self.cached
        def verify(signals):
            engine=GitHubUpdates(self.cancel)
            if not Path(path).is_file() or engine.digest(Path(path))!=sha:raise ValueError('The cached installer changed. Download it again before installing.')
            return path,sha
        self.status.setText('Rechecking the installer before restart…');self.launch_job('verify',verify)

    def cancel_operation(self):
        if self.busy:self.cancel.set();self.status.setText('Cancelling update operation…')

    def open_release(self):QDesktopServices.openUrl(QUrl(release_url(self.candidate.tag) if self.candidate else RELEASES))

    def refresh(self):
        if self.stopping:return
        self.check_button.setEnabled(not self.busy);self.prereleases.setEnabled(not self.busy)
        self.notes.setVisible(self.candidate is not None)
        self.progress.setVisible(self.busy or self.cached is not None)
        self.download_button.setVisible(self.candidate is not None)
        self.cancel_button.setVisible(self.busy)
        self.install_button.setVisible(self.cached is not None)
        self.download_button.setEnabled(not self.busy and self.candidate is not None and self.cached is None)
        self.cancel_button.setEnabled(self.busy)
        self.install_button.setEnabled(not self.busy and self.cached is not None and self.installable and self.w.state=='idle')
        self.folder_button.setEnabled(self.cached is not None or (self.w.root/'updates').is_dir())
        stamp=self.preferences['last_checked']
        self.last_check.setText('Last successful check · '+time.strftime('%d %b %Y, %H:%M',time.localtime(stamp)) if stamp else 'No successful update check yet.')

    def shutdown(self):self.stopping=True;self.cancel.set();self.auto_timer.stop()
