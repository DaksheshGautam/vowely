"""Explicit first-run downloads. No microphone, hotkeys or inference here."""
import json
from pathlib import Path
import subprocess
import sys
import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Qt
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QLabel,QPushButton,QCheckBox,QLineEdit,QFileDialog,QProgressBar,QListWidget,QScrollArea)

from .asset_setup import AssetSetup, SetupCancelled, selected_assets
from .branding import application_icon, identify_windows_app
from .config import Config
from .desktop import STYLE, brand_mark
from .version import RELEASE_VERSION


def finish_configuration(root,reuse,import_profile,asr_gpu,llm_gpu):
    """Never overwrite an existing profile; importing is an explicit choice."""
    if not (root/'config.json').exists():
        source=reuse/'config.json' if reuse and import_profile else None
        if source and source.is_file():c=Config.load(source)
        else:
            c=Config(asr_model='small',cleanup_enabled=True,streaming_enabled=True,language='auto',
                cpu_whisper_exe='vendor/whisper/Release/whisper-cli.exe',
                vad_model='models/ggml-silero-v6.2.0.bin',gpu=asr_gpu,cleanup_gpu=llm_gpu)
            if asr_gpu:c.whisper_exe='vendor/whisper-cuda/Release/whisper-cli.exe'
        c.save(root/'config.json')
    if reuse and import_profile and not (root/'dictionary.json').exists() and (reuse/'dictionary.json').is_file():
        from .learning import LearnedDictionary
        original=LearnedDictionary(reuse/'dictionary.json')
        if not original.available:raise ValueError('The existing dictionary could not be read; it was not imported.')
        # The dictionary reader validates its format; copy only this explicit file.
        LearnedDictionary(root/'dictionary.json').save_words(original.words)
    state=root/'setup-state.tmp'
    state.write_text(json.dumps({'schema':1,'version':RELEASE_VERSION,'complete':True}),encoding='utf-8')
    state.replace(root/'setup-state.json')


class Signals(QObject):
    progress=Signal(str,str,int,int)
    done=Signal(dict)
    error=Signal(str)


class SetupJob(QRunnable):
    def __init__(self,root,manifest,files,reuse,import_profile,asr_gpu,llm_gpu,cancel,runtime=None):
        super().__init__();self.signals=Signals()
        self.runtime=runtime
        self.args=(root,manifest,files,reuse,import_profile,asr_gpu,llm_gpu,cancel)

    def run(self):
        root,manifest,files,reuse,import_profile,asr_gpu,llm_gpu,cancel=self.args
        try:
            engine=AssetSetup(root,manifest,files,reuse,cancel,self.signals.progress.emit,runtime=self.runtime)
            result=engine.run(asr_gpu,llm_gpu)
            engine.check();finish_configuration(root,reuse,import_profile,asr_gpu,llm_gpu)
            self.signals.done.emit(result)
        except SetupCancelled as error:self.signals.error.emit(str(error))
        except Exception as error:self.signals.error.emit(f'{type(error).__name__}: {error}')


class SetupWindow(QMainWindow):
    def __init__(self,root,manifest_path,launch=True):
        super().__init__();self.root=Path(root).resolve();self.launch=launch
        self.manifest=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
        index=Path(manifest_path).with_name('engine-files.json')
        self.files=json.loads(index.read_text(encoding='utf-8')) if index.exists() else {}
        self.native_runtime=index.parent/'native-runtime' if '__runtime__' in self.files else None
        self.busy=False;self.closing=False;self.complete=False;self.cancel=threading.Event()
        self.pool=QThreadPool(self);self.pool.setMaxThreadCount(1)
        self.setWindowTitle('Set up Vowely');self.setWindowIcon(application_icon());self.resize(820,790)
        self.setMinimumSize(620,480)
        assets=Path(__file__).parent/'assets'
        self.setStyleSheet(STYLE.replace('CHECK_MARK',(assets/'check.svg').as_posix()).replace('CHEVRON',(assets/'chevron.svg').as_posix()))
        self.shell=QWidget();self.shell.setObjectName('shell');body=QVBoxLayout(self.shell);body.setContentsMargins(30,24,30,24);body.setSpacing(12)
        self.setCentralWidget(self.shell)
        scroll=QScrollArea();scroll.setWidgetResizable(True);content=QWidget();layout=QVBoxLayout(content);layout.setSpacing(14);scroll.setWidget(content);body.addWidget(scroll)
        header=QHBoxLayout();header.addWidget(brand_mark(70));title=QLabel('Welcome to Vowely\nYour voice. Stored on your PC.');title.setProperty('role','heading');header.addWidget(title,1);layout.addLayout(header)
        def text(value):
            label=QLabel(value);label.setTextFormat(Qt.PlainText);label.setWordWrap(True);layout.addWidget(label);return label
        text('Install local speech recognition and text cleanup. Downloads begin only when you choose Start setup. No microphone, recordings or personal text are accessed during setup.')
        text('Included: Whisper Base + Small, Qwen3-1.7B, Silero voice detection, and CPU engines. Internet is needed for missing files during setup; dictation works offline afterwards.')
        self.asr_gpu=QCheckBox('Add NVIDIA support for Whisper')
        self.llm_gpu=QCheckBox('Add NVIDIA support for Qwen')
        layout.addWidget(self.asr_gpu);layout.addWidget(self.llm_gpu)
        try:
            c=Config.load(self.root/'config.json');self.asr_gpu.setChecked(c.gpu);self.llm_gpu.setChecked(c.cleanup_gpu)
        except (OSError,ValueError,TypeError):pass
        self.size_label=text('');self.asr_gpu.toggled.connect(self.update_size);self.llm_gpu.toggled.connect(self.update_size);self.update_size()
        text('Already have Vowely files? Choose the old folder containing models and vendor. Only files matching published checksums will be reused. Nothing in that folder will be changed.')
        row=QHBoxLayout();self.reuse=QLineEdit();self.reuse.setPlaceholderText('Optional existing Vowely folder');self.reuse.setAccessibleName('Existing Vowely folder');row.addWidget(self.reuse,1)
        self.browse=QPushButton('Browse…');self.browse.clicked.connect(self.choose_folder);row.addWidget(self.browse);layout.addLayout(row)
        self.import_profile=QCheckBox('Also import settings and learned words if this is a new installation');layout.addWidget(self.import_profile)
        text('Your current installed settings and dictionary are always preserved. Models and settings are stored in Windows local application data, separately from the program. Uninstall removes the program and keeps these files for reuse.')
        self.status=text('Ready to check your files. Allow up to 10 GB free space for downloads, models and optional GPU runtimes.')
        self.progress=QProgressBar();self.progress.setRange(0,100);layout.addWidget(self.progress)
        self.log=QListWidget();self.log.setAccessibleName('Setup progress');self.log.setMinimumHeight(120);layout.addWidget(self.log)
        text('Only pinned upstream model and engine assets are downloaded from GitHub, Hugging Face and NVIDIA. Their license terms and provenance are available in THIRD_PARTY.md in the installation folder.')
        footer=QHBoxLayout();self.stop=QPushButton('Close');self.stop.clicked.connect(self.cancel_or_close);footer.addWidget(self.stop);footer.addStretch()
        self.start=QPushButton('Start setup');self.start.setProperty('primary',True);self.start.clicked.connect(self.start_setup);footer.addWidget(self.start);body.addLayout(footer)

    def update_size(self):
        total=sum(a['size'] for a in selected_assets(self.manifest,self.asr_gpu.isChecked(),self.llm_gpu.isChecked()))
        self.size_label.setText(f'Up to {total/1_000_000_000:.2f} GB download. Verified existing files are skipped. CPU is the default; NVIDIA acceleration requires a compatible GPU and driver.')

    def choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Choose existing Vowely folder')
        if folder:self.reuse.setText(folder)

    def start_setup(self):
        if self.complete:
            if self.launch:
                command=[sys.executable] if getattr(sys,'frozen',False) else [sys.executable,'-m','localflow.launcher']
                subprocess.Popen(command+['--root',str(self.root)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.close();return
        if self.busy:return
        reuse=Path(self.reuse.text().strip()).resolve() if self.reuse.text().strip() else None
        if reuse and not reuse.is_dir():self.status.setText('Choose an existing folder, or clear the optional folder field.');return
        if reuse and self.import_profile.isChecked() and not (self.root/'config.json').exists() and (reuse/'config.json').is_file():
            try:
                previous=Config.load(reuse/'config.json')
                if (previous.gpu and not self.asr_gpu.isChecked()) or (previous.cleanup_gpu and not self.llm_gpu.isChecked()):
                    self.status.setText('The settings you are importing use NVIDIA. Select the matching NVIDIA options above, or uncheck import to use new CPU settings.');return
            except (OSError,ValueError,TypeError):self.status.setText('Existing settings cannot be read. Uncheck import to use new settings; the old files will be preserved.');return
        self.cancel=threading.Event();self.busy=True;self.start.setEnabled(False);self.stop.setText('Cancel setup');self.status.setText('Checking local files…')
        for control in (self.reuse,self.browse,self.import_profile,self.asr_gpu,self.llm_gpu):control.setEnabled(False)
        self.job=SetupJob(self.root,self.manifest,self.files,reuse,self.import_profile.isChecked(),self.asr_gpu.isChecked(),self.llm_gpu.isChecked(),self.cancel,self.native_runtime)
        self.job.signals.progress.connect(self.updated);self.job.signals.done.connect(self.finished);self.job.signals.error.connect(self.failed);self.pool.start(self.job)

    def updated(self,name,phase,current,total):
        message=phase+' · '+name;self.status.setText(message)
        if total:self.progress.setRange(0,100);self.progress.setValue(round(current/total*100))
        else:self.progress.setRange(0,0)
        if not self.log.count() or self.log.item(self.log.count()-1).text()!=message:
            self.log.addItem(message);self.log.scrollToBottom()

    def finished(self,result):
        self.busy=False;self.complete=True;self.stop.setEnabled(True);self.progress.setRange(0,100);self.progress.setValue(100)
        self.status.setText('Setup complete. Models and engines verified. Vowely is ready for offline dictation.');self.start.setEnabled(True);self.start.setText('Open Vowely' if self.launch else 'Done');self.stop.setText('Close')
        self.log.addItem(f"{sum(v=='downloaded' for v in result.values())} downloaded · {sum(v=='reused' for v in result.values())} reused · {sum(v=='existing' for v in result.values())} already installed")
        if self.closing:self.wait_and_close()

    def failed(self,message):
        self.busy=False;self.stop.setEnabled(True);self.progress.setRange(0,100);self.progress.setValue(0);self.status.setText(message+' Verified files are kept. Check the connection or file indicated, then Retry.')
        self.start.setEnabled(True);self.start.setText('Retry setup');self.stop.setText('Close')
        for control in (self.reuse,self.browse,self.import_profile,self.asr_gpu,self.llm_gpu):control.setEnabled(True)
        if self.closing:self.wait_and_close()

    def cancel_or_close(self):
        if self.busy:
            self.cancel.set();self.status.setText('Cancelling… waiting for the current file operation to stop.');self.stop.setEnabled(False)
        else:self.close()

    def wait_and_close(self):
        if self.pool.activeThreadCount():QTimer.singleShot(40,self.wait_and_close)
        else:self.close()

    def closeEvent(self,event):
        if self.busy or self.pool.activeThreadCount():
            self.closing=True;self.cancel.set();self.status.setText('Finishing cancellation…');event.ignore();self.wait_and_close()
        else:event.accept()


def run(root,manifest):
    import ctypes
    from ctypes import wintypes
    import hashlib
    identify_windows_app();app=QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR];kernel.CreateMutexW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    name='Local\\LocalFlow-'+hashlib.sha256(str(root.resolve()).lower().encode()).hexdigest()[:16]
    ctypes.set_last_error(0);mutex=kernel.CreateMutexW(None,False,name)
    if not mutex or ctypes.get_last_error()==183:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(None,'Vowely setup','Vowely or another setup is running. Quit it from the system tray, then open Finish Vowely setup again.')
        if mutex:kernel.CloseHandle(mutex)
        return 1
    try:
        from .installation import installed
        guard=kernel.CreateMutexW(None,False,'Local\\Vowely-Installed') if installed(sys.executable) else None
        try:
            window=SetupWindow(root,manifest);window.show();return app.exec()
        finally:
            if guard:kernel.CloseHandle(guard)
    finally:kernel.CloseHandle(mutex)
