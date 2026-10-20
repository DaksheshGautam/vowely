import argparse
import copy
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import threading
import time
import hashlib
import wave
import os

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QRunnable, QThreadPool, QTimer, Signal, Qt
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QFont, QFontDatabase
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout, QLabel,
                              QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
                              QStyle, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget)
from PySide6.QtWidgets import QFileDialog, QScrollArea, QHBoxLayout
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .audio import Recorder
from .config import Config
from .engines import Cancelled, pipeline
from .policy import check_target
from .windows import Windows
from .devices import microphones, default_input_label
from .resident import ResidentModels
from .streaming import StreamingSession
from .version import APP_NAME, RELEASE_VERSION
from .overlay import DictationOverlay
from .branding import application_icon, identify_windows_app
from .learning import EditSession, LearnedDictionary, MAX_SPAN
from .learning_popup import LearningPopup


class Signals(QObject):
    done = Signal(int, object)
    error = Signal(int, str)
    update = Signal(int, object)
    prepared = Signal(int, object)


class PrepareJob(QRunnable):
    def __init__(self,generation,runtime,cancel):
        super().__init__()
        self.generation,self.runtime,self.cancel = generation,runtime,cancel
        self.signals = Signals()

    def run(self):
        try:
            self.runtime.start()
            if self.cancel.is_set(): self.runtime.close()
            else: self.signals.prepared.emit(self.generation,self.runtime)
        except Cancelled:
            pass
        except Exception:
            self.runtime.close()
            if not self.cancel.is_set():
                self.signals.error.emit(self.generation,'Could not load live models. Retry Load models, or turn off Live mode to use recording-after-stop.')


class StreamJob(QRunnable):
    def __init__(self,generation,session):
        super().__init__()
        self.generation,self.session = generation,session
        self.signals = Signals()
        session.on_update = lambda payload:self.signals.update.emit(generation,payload)

    def run(self):
        try:
            result = self.session.run()
            if not self.session.cancel.is_set(): self.signals.done.emit(self.generation,result)
        except Cancelled:
            pass
        except Exception:
            if not self.session.cancel.is_set():
                self.signals.error.emit(self.generation,'Live processing failed. Nothing inserted. Reload models and try again.')


class Job(QRunnable):
    def __init__(self, generation, pcm, config, root, cancel):
        super().__init__()
        self.generation, self.pcm, self.config = generation, pcm, config
        self.root, self.cancel = root, cancel
        self.signals = Signals()

    def run(self):
        try:
            result = pipeline(self.pcm, self.config, self.root, self.cancel)
            if not self.cancel.is_set():
                self.signals.done.emit(self.generation, result)
        except Cancelled:
            pass
        except Exception as exc:
            # Avoid dumping audio, transcript, prompt or third-party engine logs.
            from .engines import EngineError
            message = str(exc) if isinstance(exc, EngineError) else "Local engine failed. Check files, device and setup."
            self.signals.error.emit(self.generation, message)
        finally:
            self.pcm = b""


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312 and msg.wParam == Windows.HOTKEY_ID:
            self.callback()
            return True, 0
        return False, 0


class Window(QMainWindow):
    def __init__(self, root, config_path, auto_prepare=True):
        super().__init__()
        # The offscreen/restricted Windows platform may expose no system fonts.
        # Load installed OS fonts explicitly; never redistribute Windows fonts.
        if not QFontDatabase.families():
            font_dir = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'Fonts'
            for filename in ('segoeui.ttf', 'seguisym.ttf', 'seguiemj.ttf'):
                path = font_dir / filename
                if path.is_file():
                    QFontDatabase.addApplicationFont(str(path))
        QApplication.instance().setFont(QFont('Segoe UI', 10))
        self.root, self.config_path = root, config_path
        self.c = Config.load(config_path)
        self.win = Windows()
        self.dictionary = LearnedDictionary(root/'dictionary.json')
        self.edit_session = None
        self.edit_target = None
        self.edit_pending = None
        self.edit_next = 0.0
        self.state = "idle"
        self.target = None
        self.recorder = None
        self.button_recording = False
        self.stop_requested = False
        self.generation = 0
        self.cancel = threading.Event()
        self.runtime = None
        self.live_session = None
        self.live_offset = 0
        self.live_sequence = 0
        self.replay_pcm = b''
        self.overlay = DictationOverlay()
        self.learning_popup = LearningPopup()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.setWindowTitle(f"{APP_NAME} {RELEASE_VERSION} • Offline dictation")
        self.resize(650, 780)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addWidget(QLabel("Audio and text stay local. No history is saved.\nFocus a text box, hold your shortcut to speak, then release to type."))
        self.status = QLabel("Starting dictation • microphone off")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItems(["Natural", "Verbatim", "Developer"])
        self.mode.setCurrentText(self.c.mode)
        form.addRow("Mode", self.mode)
        self.model = QComboBox()
        self.model.addItems(["base", "small"])
        self.model.setCurrentText(self.c.asr_model)
        form.addRow("Whisper model", self.model)
        self.search_quality = QComboBox()
        self.search_quality.addItem('Faster decoding', 1)
        self.search_quality.addItem('More thorough decoding (slower)', 5)
        self.search_quality.setCurrentIndex(0 if self.c.beam_size == 1 else 1)
        form.addRow('Recognition quality', self.search_quality)
        self.vocabulary = QLineEdit(', '.join(self.c.personal_vocabulary))
        self.vocabulary.setPlaceholderText('Your full name, people, product names — separated by commas')
        self.vocabulary.setToolTip('Stored only on this PC. Spelling hints can help recognition but cannot guarantee correct words.')
        form.addRow('Names and vocabulary', self.vocabulary)
        self.learn = QCheckBox('Learn spelling corrections after dictation')
        self.learn.setChecked(self.c.learn_corrections)
        self.learn.setToolTip('Compares your edited draft when the box clears or you leave it. Learns multiple corrected words without a typing pause. Only the dictated portion of a small eligible text box is learned.')
        form.addRow(self.learn)
        self.dictionary_button = QPushButton(f'Learned words ({len(self.dictionary.words)})')
        self.dictionary_button.clicked.connect(self.manage_dictionary)
        form.addRow(self.dictionary_button)
        self.dictionary_status = QLabel('Corrected spellings stay on this PC.' if self.dictionary.available else 'Local dictionary could not be loaded; learning unavailable.')
        self.dictionary_status.setTextFormat(Qt.PlainText)
        self.dictionary_status.setWordWrap(True)
        form.addRow(self.dictionary_status)
        self.backend = QComboBox()
        self.backend.addItems(["CPU", "NVIDIA CUDA (tested on this PC)"])
        self.backend.setCurrentIndex(1 if self.c.gpu else 0)
        form.addRow("Recognition backend", self.backend)
        self.language = QLineEdit(self.c.language)
        self.language.setPlaceholderText("auto, en, hi, or another Whisper language code")
        form.addRow("Language", self.language)
        self.vad = QCheckBox("Ignore silent sections with local voice detection")
        self.vad.setChecked(bool(self.c.vad_model))
        form.addRow(self.vad)
        self.hotkey = QLineEdit(self.c.hotkey)
        form.addRow("Push-to-talk shortcut", self.hotkey)
        self.mic = QComboBox()
        self.all_inputs = QCheckBox('Show all audio inputs (advanced)')
        self.populate_microphones(self.c.microphone)
        self.all_inputs.toggled.connect(self.change_microphone_view)
        form.addRow("Microphone", self.mic)
        form.addRow(self.all_inputs)
        self.cleanup = QCheckBox("Use local Qwen cleanup")
        self.cleanup.setToolTip('Final results type into the focused text box. If a cleanup edit is rejected, its original recognized words are used instead.')
        self.cleanup.setChecked(self.c.cleanup_enabled)
        form.addRow(self.cleanup)
        self.cleanup_backend = QComboBox()
        self.cleanup_backend.addItems(['CPU','NVIDIA CUDA (live mode)'])
        self.cleanup_backend.setCurrentIndex(1 if self.c.cleanup_gpu else 0)
        form.addRow('Cleanup backend',self.cleanup_backend)
        self.live = QCheckBox('Live preview + Whisper decides sentence endings')
        self.live.setChecked(self.c.streaming_enabled)
        self.live.setToolTip('No fixed silence wait. Sentence-ending punctuation must agree across two Whisper previews before Qwen cleans the sentence. Qwen does not decide boundaries. Stop rechecks the complete recording and cleans any unfinished text. Detection is approximate; preview checks and model processing take time. Final insertion happens only after Stop.')
        form.addRow(self.live)
        self.insert = QCheckBox("Automatically type final results into the focused text box")
        self.insert.setToolTip('Waits for final Whisper recognition and Qwen cleanup. No field approval is needed. Password fields and changed focus remain blocked.')
        self.insert.setChecked(self.c.auto_insert)
        form.addRow(self.insert)
        layout.addLayout(form)
        self.models_status = QLabel('Models are not loaded • microphone off')
        self.models_status.setWordWrap(True)
        self.models_status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.models_status)
        model_actions = QHBoxLayout()
        self.prepare_button = QPushButton('Load / reload models')
        self.prepare_button.clicked.connect(self.prepare_live)
        self.unload_button = QPushButton('Free model memory')
        self.unload_button.clicked.connect(self.unload_models)
        model_actions.addWidget(self.prepare_button);model_actions.addWidget(self.unload_button)
        layout.addLayout(model_actions)
        self.pause = QPushButton("Resume dictation")
        self.pause.setToolTip('Dictation starts automatically. Pause only when you want to stop the shortcut or change settings.')
        self.pause.clicked.connect(self.toggle_dictation)
        layout.addWidget(self.pause)
        self.record_button = QPushButton("Record a test • preview only")
        self.record_button.clicked.connect(self.manual_record)
        layout.addWidget(self.record_button)
        self.file_button = QPushButton("Transcribe a local WAV file • preview only")
        self.file_button.clicked.connect(self.transcribe_file)
        layout.addWidget(self.file_button)
        cancel = QPushButton("Cancel recording / processing")
        cancel.clicked.connect(self.abort)
        layout.addWidget(cancel)
        layout.addWidget(QLabel("Result • edit or copy after review"))
        actions = QHBoxLayout()
        self.copy_button = QPushButton("Copy reviewed result")
        self.copy_button.clicked.connect(self.copy_result)
        actions.addWidget(self.copy_button)
        self.clear_button = QPushButton("Clear text from memory")
        self.clear_button.clicked.connect(self.forget_result)
        actions.addWidget(self.clear_button)
        layout.addLayout(actions)
        self.preview = QTextEdit()
        layout.addWidget(self.preview)
        self.original = QTextEdit()
        layout.addWidget(QLabel('Original speech recognition • compare this with the result above'))
        self.original.setReadOnly(True)
        self.original.setPlaceholderText("Original words from Whisper, before any cleanup.")
        self.original.setMaximumHeight(100)
        layout.addWidget(self.original)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        self.setCentralWidget(scroll)
        self.controls = [self.mode, self.model, self.hotkey, self.mic, self.cleanup, self.insert,
                         self.backend, self.language, self.vad, self.all_inputs, self.search_quality, self.vocabulary,
                         self.cleanup_backend,self.live,self.learn]
        self.native_filter = HotkeyFilter(self.pressed)
        QApplication.instance().installNativeEventFilter(self.native_filter)
        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        QTimer.singleShot(0, self.win.prepare_probe)
        icon = application_icon()
        QApplication.instance().setWindowIcon(icon)
        self.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu(self)
        show = menu.addAction("Show Vowely")
        show.triggered.connect(self.reveal)
        self.tray_pause = menu.addAction("Resume dictation")
        self.tray_pause.triggered.connect(self.toggle_dictation)
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.reveal() if reason in
                                    (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()
        self.quitting = False
        self.live.toggled.connect(self.live_changed)
        self.file_button.setText('Replay a WAV in live mode • preview only' if self.live.isChecked() else 'Transcribe a local WAV file • preview only')
        self.prepare_button.setEnabled(self.live.isChecked())
        self.unload_button.setEnabled(False)
        if auto_prepare:
            QTimer.singleShot(0,self.start_automatically)

    def start_automatically(self):
        if not self.win.registered: self.toggle_dictation()

    def reveal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def run_background(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.status.setText('No system tray is available. Minimise the window to use your shortcut.')

    def populate_microphones(self, selected):
        self.mic.clear()
        try:
            import sounddevice as sd
            self.mic.addItem(default_input_label(sd), None)
            for device in microphones(sd, advanced=self.all_inputs.isChecked(), selected=selected):
                self.mic.addItem(device.name, device.index)
            row = self.mic.findData(selected)
            if row < 0:
                self.mic.addItem('Saved input is not in the current list — select a microphone', -1)
                row = self.mic.count() - 1
            self.mic.setCurrentIndex(row)
        except Exception:
            if not self.mic.count():
                self.mic.addItem('Windows default microphone', None)
            self.status.setText('Could not list microphones. Check Windows microphone permissions.')

    def change_microphone_view(self):
        self.populate_microphones(self.mic.currentData())

    def settings(self):
        c = copy.deepcopy(self.c)
        c.mode, c.asr_model = self.mode.currentText(), self.model.currentText()
        c.beam_size = self.search_quality.currentData()
        c.personal_vocabulary = list(dict.fromkeys(x.strip() for x in self.vocabulary.text().split(',') if x.strip()))
        c.hotkey, c.microphone = self.hotkey.text().strip(), self.mic.currentData()
        c.cleanup_enabled, c.auto_insert = self.cleanup.isChecked(), self.insert.isChecked()
        c.learn_corrections = self.learn.isChecked()
        c.streaming_enabled = self.live.isChecked()
        c.cleanup_gpu = self.cleanup_backend.currentIndex() == 1
        gpu = self.backend.currentIndex() == 1
        if gpu != c.gpu:
            c.whisper_exe = 'vendor/whisper-cuda/Release/whisper-cli.exe' if gpu else 'vendor/whisper/Release/whisper-cli.exe'
        c.gpu = gpu
        if not c.cpu_whisper_exe:
            c.cpu_whisper_exe = 'vendor/whisper/Release/whisper-cli.exe'
        c.language = self.language.text().strip().lower()
        c.vad_model = (c.vad_model or 'models/ggml-silero-v6.2.0.bin') if self.vad.isChecked() else ''
        c.validate()
        return c

    def working(self, busy):
        for control in self.controls:
            control.setEnabled(not busy and not self.win.registered)
        self.preview.setReadOnly(busy)
        self.copy_button.setEnabled(not busy)
        self.dictionary_button.setEnabled(not busy)
        self.record_button.setEnabled(self.state in ('idle','recording'))
        self.file_button.setEnabled(not busy)
        self.pause.setEnabled(self.win.registered or not busy)
        self.prepare_button.setEnabled(not busy and not self.win.registered and self.live.isChecked())
        self.unload_button.setEnabled(not busy and not self.win.registered and self.runtime is not None)

    def unload_models(self):
        if self.runtime:
            self.runtime.close()
            self.runtime = None
        self.models_status.setText('Models unloaded • microphone off')
        self.unload_button.setEnabled(False)

    def live_changed(self, enabled):
        self.file_button.setText('Replay a WAV in live mode • preview only' if enabled else 'Transcribe a local WAV file • preview only')
        if enabled:
            self.prepare_live()
        else:
            self.unload_models()
            self.working(False)

    def prepare_live(self):
        if self.state != 'idle' or self.pool.activeThreadCount(): return
        try:
            self.c = self.settings()
            self.c.save(self.config_path)
            if not self.c.streaming_enabled: return
            self.unload_models()
            self.cancel = threading.Event()
            self.generation += 1
            self.runtime = ResidentModels(self.c,self.root)
            self.state = 'preparing'
            self.working(True)
            self.status.setText('Loading local models • microphone off')
            if self.win.registered:
                self.overlay.show_phase('processing','Loading models…')
            self.models_status.setText('Loading models into memory…')
            self.job = PrepareJob(self.generation,self.runtime,self.cancel)
            self.job.signals.prepared.connect(self.models_prepared)
            self.job.signals.error.connect(self.failed)
            self.pool.start(self.job)
        except Exception:
            self.failed(self.generation,'Could not prepare models. Check model files and settings, then retry.')

    def models_prepared(self, generation, runtime):
        if generation != self.generation or self.cancel.is_set():
            runtime.close()
            return
        self.state = 'idle'
        self.working(False)
        self.models_status.setText('Ready • '+runtime.description)
        self.status.setText(f'Ready • focus a text box and hold {self.c.hotkey} • microphone off')
        if self.overlay.phase=='processing':
            self.overlay.show_phase('done','Ready — hold shortcut',1800)

    def ensure_live_ready(self):
        if not self.c.streaming_enabled: return True
        if self.runtime and self.runtime.matches(self.c): return True
        self.prepare_live()
        return False

    def start_stream(self):
        self.cancel = threading.Event()
        self.generation += 1
        self.live_sequence = 0
        self.live_session = StreamingSession(self.runtime,self.inference_config(),self.root,self.cancel)
        self.job = StreamJob(self.generation,self.live_session)
        self.job.signals.update.connect(self.live_update)
        self.job.signals.done.connect(self.finished)
        self.job.signals.error.connect(self.failed)
        self.pool.start(self.job)

    def live_update(self, generation, payload):
        if generation != self.generation or self.cancel.is_set() or self.state not in ('recording','processing','replaying'): return
        sequence = payload.get('sequence',self.live_sequence+1)
        if sequence <= self.live_sequence: return
        self.live_sequence = sequence
        self.preview.setPlainText(payload['text'])
        self.original.setPlainText(payload['raw'])
        activity = 'Recognising + cleaning' if payload['asr_busy'] and payload['cleanup_busy'] else ('Recognising' if payload['asr_busy'] else ('Cleaning' if payload['cleanup_busy'] else 'Listening'))
        if payload.get('waiting_sentence') and not payload['asr_busy'] and not payload['cleanup_busy']:
            activity = 'Waiting for a stable Whisper sentence ending or Stop'
        self.models_status.setText(payload['warning'] or f"{activity} • {payload['cleaned_phrases']} sentences ready • {payload['pending_phrases']} queued • provisional until finished")
        if self.state=='processing' and self.overlay.phase=='processing':
            self.overlay.label = 'Cleaning…' if payload['cleanup_busy'] else 'Recognising…'

    def forget_result(self):
        if self.state != 'idle': self.abort()
        self.clear_text()
        self.unload_models()
        self.status.setText('Text cleared and model context discarded • microphone off')

    def start_live_replay(self, pcm):
        self.clear_text()
        self.target = None
        self.replay_pcm = pcm
        self.live_offset = 0
        self.record_started = time.monotonic()
        self.state = 'replaying'
        self.start_stream()
        self.working(True)
        self.status.setText('Replaying local WAV at speaking speed • microphone off • preview only')

    def toggle_dictation(self):
        if self.win.registered:
            self.disarm()
            return
        try:
            c = self.settings()
            self.win.arm(c.hotkey)
            try:
                c.save(self.config_path)
            except Exception:
                self.win.disarm()
                raise
            self.c = c
            self.pause.setText("Pause dictation")
            self.tray_pause.setText("Pause dictation")
            self.working(False)
            self.status.setText(f"Ready • hold {self.c.hotkey} to speak • microphone off")
            if c.streaming_enabled and (not self.runtime or not self.runtime.matches(c)):
                self.prepare_live()
        except Exception as exc:
            self.status.setText(str(exc))
            self.overlay.show_phase('notice','Shortcut unavailable',3000)

    def disarm(self):
        self.win.disarm()
        self.abort()
        self.pause.setText("Resume dictation")
        self.tray_pause.setText("Resume dictation")
        for control in self.controls:
            control.setEnabled(True)
        self.status.setText("Paused • microphone off")

    def pressed(self):
        if not self.win.registered or self.state != "idle" or self.pool.activeThreadCount():
            return
        self.stop_learning(finalize=True)
        self.target = self.win.snapshot()
        ok, why = check_target(self.target, self.c)
        if not ok and why in ("Password field blocked.", "Application is on the denylist.", "Sensitive field blocked."):
            self.status.setText(why + " Microphone remains off.")
            self.overlay.show_phase('notice','Field blocked',2200)
            return
        if not ok and self.c.auto_insert:
            self.status.setText(why+' Click inside an editable text box and try again.')
            self.overlay.show_phase('notice','Select a text box',2800)
            return
        self.button_recording = False
        if not self.ensure_live_ready(): return
        self.begin_recording()

    def begin_recording(self):
        try:
            self.stop_learning()
            self.clear_text()
            self.recorder = Recorder(self.c.microphone, self.c.max_seconds)
            self.recorder.start()
            self.state = "recording"
            self.record_started = time.monotonic()
            self.stop_requested = False
            self.live_offset = 0
            if self.c.streaming_enabled: self.start_stream()
            self.working(True)
            self.record_button.setText("Stop recording" if self.button_recording else "Recording with shortcut")
            self.status.setText("● Recording locally • release shortcut or press Stop")
            self.tray.setToolTip("Vowely • RECORDING")
            self.overlay.show_phase('listening')
        except Exception as exc:
            self.abort()
            self.status.setText(f"Could not open the selected microphone: {exc}. Choose another input; some device variants do not support 16 kHz mono.")
            self.overlay.show_phase('notice','Microphone unavailable',2500)

    def manual_record(self):
        if self.state == "recording":
            if time.monotonic() - self.record_started < 0.3:
                return  # Ignore an accidental double-click on the start button.
            self.stop_requested = True
            return
        if self.state != "idle" or self.pool.activeThreadCount():
            self.status.setText("Local processing is still running. Cancel it or wait for the result.")
            return
        try:
            self.c = self.settings()
            self.c.save(self.config_path)
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.target = None
        self.button_recording = True
        if not self.ensure_live_ready(): return
        self.begin_recording()

    def transcribe_file(self):
        if self.state != 'idle' or self.pool.activeThreadCount():
            self.status.setText('Finish or cancel the current recording/processing first.')
            return
        try:
            self.c = self.settings()
            if not self.ensure_live_ready(): return
        except Exception as exc:
            self.status.setText(str(exc))
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Choose a local 16 kHz mono PCM16 WAV',
                                             str(self.root / 'samples'), 'WAV audio (*.wav)')
        if not path:
            return
        try:
            self.c = self.settings()
            with wave.open(path, 'rb') as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype()) != (1, 2, 16000, 'NONE'):
                    raise ValueError('Choose an uncompressed 16 kHz, mono, PCM16 WAV.')
                if not 0 < audio.getnframes() <= 120 * 16000:
                    raise ValueError('Choose a WAV shorter than 120 seconds.')
                pcm = audio.readframes(audio.getnframes())
            self.clear_text()
            self.target = None
            if self.c.streaming_enabled: self.start_live_replay(pcm)
            else: self.start_job(pcm)
        except Exception as exc:
            self.status.setText(str(exc) if isinstance(exc, ValueError) else 'Could not read this local WAV file.')

    def start_job(self, pcm):
        self.state = 'processing'
        self.working(True)
        self.cancel = threading.Event()
        self.generation += 1
        self.job = Job(self.generation, pcm, self.inference_config(), self.root, self.cancel)
        self.job.signals.done.connect(self.finished)
        self.job.signals.error.connect(self.failed)
        self.pool.start(self.job)
        self.status.setText('Transcribing locally • microphone off')
        self.overlay.show_phase('processing')

    def tick(self):
        if self.state=='idle' and time.monotonic()>=self.edit_next:
            self.poll_learning()
        if self.state == 'replaying':
            end = min(len(self.replay_pcm),int((time.monotonic()-self.record_started)*16000)*2)
            if end > self.live_offset:
                self.live_session.feed(self.replay_pcm[self.live_offset:end])
                self.live_offset = end
            if end == len(self.replay_pcm):
                self.state = 'processing'
                self.live_session.finish_input(self.replay_pcm)
                self.replay_pcm = b''
                self.status.setText('Finishing the last sentence • microphone off')
            return
        if self.state == "recording":
            self.overlay.set_level(getattr(self.recorder,'input_level',0.0))
            elapsed = time.monotonic() - self.record_started
            captured = len(self.recorder.data) / 32000
            if elapsed >= 3 and captured == 0:
                self.abort()
                self.status.setText("No audio received from the selected microphone. Choose another input in Microphone. A disconnected Bluetooth headset can appear active without delivering audio.")
                return
            self.status.setText(f"● Recording locally • microphone audio: {captured:.1f}s • {elapsed:.1f} / {self.c.max_seconds} seconds elapsed • press Stop when finished")
            if self.live_session:
                delta,self.live_offset = self.recorder.read_since(self.live_offset)
                if delta: self.live_session.feed(delta)
        released = self.state == "recording" and not self.button_recording and not self.win.down(self.win.vk)
        if self.state == "recording" and (released or self.stop_requested or self.recorder.full.is_set()):
            try:
                pcm = self.recorder.stop()
                self.recorder = None
                self.record_button.setText("Record a test • preview only")
                self.tray.setToolTip("Vowely • microphone off")
                if len(pcm) < 3200:
                    self.abort()
                    if not pcm:
                        self.status.setText("No audio received from the selected microphone. Choose another input in Microphone, then record again. Check a Bluetooth headset is connected for microphone use.")
                    else:
                        self.status.setText(f"Only {len(pcm) / 32000:.2f}s of microphone audio was captured. Record for a few seconds, then press Stop.")
                    return
                if self.live_session:
                    if len(pcm)>self.live_offset: self.live_session.feed(pcm[self.live_offset:])
                    self.state = 'processing'
                    self.working(True)
                    self.live_session.finish_input(pcm)
                    self.status.setText('Finishing the last sentence • microphone off')
                    self.overlay.show_phase('processing')
                else: self.start_job(pcm)
            except Exception:
                self.abort()
                self.status.setText("Recording failed or overflowed; discarded. Try a different input device.")

    def finished(self, generation, result):
        if generation != self.generation or self.cancel.is_set():
            return
        self.state = "idle"
        self.live_session = None
        self.replay_pcm = b''
        self.working(False)
        self.preview.setPlainText(result["text"])
        self.original.setPlainText(result['raw'])
        attempted = self.target is not None and result.get('insertion_ready',not result['review'])
        inserted = False
        if attempted:
            inserted, message = self.win.insert(self.target, result["text"], self.c)
            if inserted and self.c.learn_corrections and self.dictionary.available and 0<len(result['text'])<=MAX_SPAN:
                self.edit_target = self.target
                self.edit_pending = result['text']
                self.edit_session = EditSession(result['text'],time.monotonic())
                self.edit_next = time.monotonic()+.1
            if inserted and result.get('cleanup_fallback'):
                message += ' Cleanup partly unavailable or rejected; original words used for those portions.'
        elif self.target is None:
            message = 'Test recording • preview only; no typing target was captured.'
        elif result["review"]:
            message = 'Final result was incomplete; nothing typed. '+result['warning']
        else:
            message = 'Preview ready • copy the result when ready.'
        label = 'Typed • original fallback' if inserted and result.get('cleanup_fallback') else 'Typed'
        if not inserted:
            if not result['text']: label = 'Nothing to type'
            elif self.target is None: label = 'Test recording — preview'
            elif not attempted: label = 'Final text incomplete'
            elif 'Focus changed' in message: label = 'Focus changed — not typed'
            elif 'keys' in message.lower(): label = 'Release shortcut keys'
            elif 'Automatic insertion is off' in message: label = 'Automatic typing is off'
            elif 'password' in message.lower(): label = 'Password field blocked'
            elif 'Sensitive field' in message: label = 'Sensitive field blocked'
            elif 'Application is on' in message: label = 'Application blocked'
            elif 'partial' in message.lower(): label = 'Typing blocked — check box'
            elif 'verified' in message or 'editable' in message: label = 'Text box unavailable'
            else: label = 'Typing failed — see status'
        self.target = None  # Each recording can insert at most once.
        self.overlay.show_phase('done' if inserted else 'notice',
                                label,
                                1100 if inserted else 2600)
        fallback = " GPU unavailable; CPU fallback used." if result["cpu_fallback"] else ""
        backend = ' NVIDIA CUDA active.' if result['gpu_used'] else ''
        timing = f"After Stop: {result['tail_ms']} ms." if result.get('streaming') else f"Local processing: {result['total_ms']} ms (includes model loading)."
        if result.get('streaming') and self.runtime:
            self.models_status.setText(('Ready • '+self.runtime.description) if self.runtime.ready else 'Models stopped • reload before next recording')
            backend = ' '+self.runtime.description+'.'
        self.status.setText(f"{message}{fallback}{backend} {timing}")
        # Do not activate or show the window here: original target focus is preserved.
        self.tray.setToolTip("Vowely • result ready")

    def failed(self, generation, message):
        if generation == self.generation:
            self.abort()
            self.status.setText(message)
            self.overlay.show_phase('notice','Could not finish',2500)

    def abort(self):
        self.stop_learning()
        self.learning_popup.clear()
        self.overlay.clear()
        self.cancel.set()
        self.generation += 1
        if self.live_session: self.live_session.abort()
        self.live_session = None
        self.replay_pcm = b''
        self.unload_models()
        if self.recorder:
            try:
                self.recorder.discard()
            except Exception:
                pass
        self.recorder = None
        self.record_button.setText("Record a test • preview only")
        self.target = None
        self.state = "idle"
        self.working(False)
        self.clear_text()
        self.tray.setToolTip("Vowely • microphone off")
        self.status.setText("Cancelled • microphone off")

    def inference_config(self):
        config = copy.deepcopy(self.c)
        config.personal_vocabulary = self.dictionary.vocabulary(config.personal_vocabulary)
        return config

    def stop_learning(self,finalize=False):
        if self.edit_session or self.edit_pending:
            words = self.win.clear_correction_watch(finalize)
            if finalize and words: self.save_learned(words)
        self.edit_session = self.edit_target = self.edit_pending = None
        self.edit_next = time.monotonic()+.15

    def poll_learning(self):
        self.edit_next = time.monotonic()+.15
        if not self.edit_session: return
        if not self.c.learn_corrections or time.monotonic()>=self.edit_session.deadline:
            self.stop_learning();return
        update = self.win.correction_update(self.edit_target,self.c,self.edit_pending)
        self.edit_pending = None
        if update is None:
            self.stop_learning();return
        if update.get('status')=='finished':
            words = update.get('words',[])
            self.stop_learning()
            self.save_learned(words)

    def save_learned(self,words):
        if words:
            try:
                learned = self.dictionary.add(words)
                if learned:
                    self.dictionary_status.setText('Learned locally: '+', '.join(learned))
                    self.dictionary_button.setText(f'Learned words ({len(self.dictionary.words)})')
                    self.learning_popup.show_words(learned)
            except OSError:
                self.dictionary_status.setText('Could not save learned words; dictation is still available.')
                self.stop_learning()

    def manage_dictionary(self):
        from PySide6.QtWidgets import QDialog, QListWidget, QAbstractItemView
        self.stop_learning()
        dialog = QDialog(self)
        dialog.setWindowTitle('Vowely • learned words')
        dialog.resize(400,360)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Stored locally. These spellings help future dictation.'))
        words = QListWidget()
        words.setSelectionMode(QAbstractItemView.ExtendedSelection)
        words.addItems(self.dictionary.words)
        layout.addWidget(words)
        remove = QPushButton('Remove selected words')
        def remove_words():
            try:
                self.dictionary.remove([item.text() for item in words.selectedItems()])
                words.clear();words.addItems(self.dictionary.words)
                self.dictionary_button.setText(f'Learned words ({len(self.dictionary.words)})')
                self.dictionary_status.setText('Corrected spellings stay on this PC.')
            except OSError:
                self.dictionary_status.setText('Could not update the local dictionary.')
        remove.clicked.connect(remove_words)
        layout.addWidget(remove)
        close = QPushButton('Close')
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def clear_text(self):
        self.stop_learning()
        self.preview.clear()
        self.original.clear()

    def copy_result(self):
        if self.preview.toPlainText():
            QApplication.clipboard().setText(self.preview.toPlainText())
            self.status.setText("Copied by request. Windows clipboard history/sync may retain it; clear it yourself after use.")

    def closeEvent(self, event: QCloseEvent):
        if self.quitting:
            event.accept()
        elif QSystemTrayIcon.isSystemTrayAvailable():
            self.run_background()
            event.ignore()
        else:
            self.quit()
            event.accept()

    def quit(self):
        self.quitting = True
        self.disarm()
        self.pool.waitForDone(3000)
        self.win.close()
        self.tray.hide()
        self.overlay.clear()
        self.overlay.close()
        self.learning_popup.clear()
        self.learning_popup.close()
        QApplication.instance().quit()


def main():
    parser = argparse.ArgumentParser(description="Vowely offline dictation")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Folder containing config.json, vendor and models")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("The desktop MVP requires Windows")
    identify_windows_app()
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    name = 'Local\\LocalFlow-' + hashlib.sha256(str(args.root.resolve()).lower().encode()).hexdigest()[:16]
    ctypes.set_last_error(0)
    mutex = kernel.CreateMutexW(None, False, name)
    if not mutex:
        QMessageBox.critical(None, 'Vowely', 'Could not acquire the local application lock.')
        return 1
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(mutex)
        socket = QLocalSocket()
        socket.connectToServer(name.replace('Local\\', '') + '-show')
        if socket.waitForConnected(1500):
            socket.write(b'SHOW')
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            return 0
        QMessageBox.information(None, 'Vowely', 'Vowely is already running. Open it from the system tray.')
        return 0
    try:
        window = Window(args.root.resolve(), args.root.resolve() / "config.json")
    except Exception as exc:
        QMessageBox.critical(None, "Vowely could not start", f"Check config.json and Windows dependencies.\n{type(exc).__name__}")
        kernel.CloseHandle(mutex)
        return 1
    server = QLocalServer(app)
    server.setSocketOptions(QLocalServer.UserAccessOption)
    server_name = name.replace('Local\\', '') + '-show'
    QLocalServer.removeServer(server_name)
    server.listen(server_name)
    def show_requested():
        while server.hasPendingConnections():
            client = server.nextPendingConnection()
            client.setParent(server)
            def received(client=client):
                # This pipe accepts one fixed command, never text, files or hotkeys.
                if client.bytesAvailable() >= 4:
                    if bytes(client.read(5)) == b'SHOW':
                        window.reveal()
                    client.disconnectFromServer()
            client.readyRead.connect(received)
            client.disconnected.connect(client.deleteLater)
            timeout = QTimer(client)
            timeout.setSingleShot(True)
            timeout.timeout.connect(client.abort)
            timeout.start(2000)
            received()
    server.newConnection.connect(show_requested)
    if not QSystemTrayIcon.isSystemTrayAvailable(): window.reveal()
    app.aboutToQuit.connect(window.win.close)
    try:
        return app.exec()
    finally:
        kernel.CloseHandle(mutex)


if __name__ == "__main__":
    raise SystemExit(main())
