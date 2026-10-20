"""Presentation layer. Every action delegates to the existing dictation controller."""
import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize, QPoint, QRectF, QUrl
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut, QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox,
    QApplication, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QProgressBar, QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QGraphicsDropShadowEffect,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from .branding import application_icon
from .version import RELEASE_VERSION
from .shortcuts import ShortcutEdit


STYLE = '''
QMainWindow, QWidget#shell {background:#15151d; color:#eeedf6;}
QWidget {font-family:'Segoe UI'; font-size:10pt; color:#eeedf6;}
QFrame#sidebar {background:#1a1923; border-right:1px solid #2c2a38;}
QFrame#card {background:#201f2b; border:1px solid #343140; border-radius:16px;}
QFrame#hero {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #2c273e,stop:1 #201f2b);border:1px solid #4b4264;border-radius:20px;}
QFrame#updateNotice {background:#2b253b;border:1px solid #675184;border-radius:12px;}
QFrame#updateNotice QPushButton {padding:6px 3px;font-size:9pt;}
QFrame#updateNotice QLabel {font-size:9pt;}
QLabel {background:transparent;}
QLabel[role='muted'] {color:#aaa6bc;}
QLabel[role='eyebrow'] {color:#bdb1df; font-size:9pt; font-weight:600;}
QLabel[role='title'] {font-size:24pt; font-weight:600;}
QLabel[role='heading'] {font-size:13pt; font-weight:600;}
QLabel[role='state'] {font-size:28pt; font-weight:600;}
QLabel#offline {color:#9adeba; background:#25382e; border-radius:13px; padding:6px 12px;font-size:9pt;}
QPushButton {background:#302d40; border:1px solid #454055; border-radius:9px; padding:9px 14px; min-height:18px;}
QPushButton:hover {background:#3c364e; border-color:#7a6a9d;}
QPushButton:pressed {background:#4b405f;}
QPushButton:disabled {color:#777282; background:#252330; border-color:#302d3b;}
QPushButton[primary='true'] {background:#bba1ff; color:#21172f; border-color:#cbb5ff; font-weight:600;}
QPushButton[primary='true']:hover {background:#cfbaff;}
QPushButton[primary='true']:disabled {background:#494057;color:#8c819e;border-color:#494057;}
QPushButton[nav='true'] {text-align:left; background:transparent; border:1px solid transparent; padding:12px;}
QPushButton[nav='true']:checked {background:#39314f; border-color:#4b3d68;color:#f1eaff;}
QPushButton[nav='true']:hover {background:#2e293e;}
QPushButton:focus, QComboBox:focus, QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QListWidget:focus {border:2px solid #c1a7ff;}
QLineEdit,QComboBox,QSpinBox,QTextEdit,QListWidget {background:#191923;border:1px solid #454052;border-radius:9px;padding:8px;selection-background-color:#665382;selection-color:#fff;}
QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled {color:#888194;background:#24212d;}
QComboBox {min-height:22px;padding-right:22px;}
QComboBox::drop-down {border:0;width:22px;}
QComboBox::down-arrow {image:url("CHEVRON");width:14px;height:14px;}
QComboBox QAbstractItemView {background:#292534;color:#efebfa;selection-background-color:#55436f;}
QCheckBox {spacing:10px;padding:6px 0;}
QCheckBox::indicator {width:18px;height:18px;border-radius:5px;border:1px solid #635a73;background:#1a1822;}
QCheckBox::indicator:checked {background:#bba1ff;border-color:#d3bfff;image:url("CHECK_MARK");}
QCheckBox:disabled {color:#898191;}
QCheckBox::indicator:disabled {border-color:#4c4359;background:#3f344e;}
QCheckBox:focus {outline:1px solid #bba1ff;}
QScrollArea {background:transparent;border:0;}
QScrollArea > QWidget > QWidget {background:transparent;}
QScrollBar:vertical {background:#191821;width:10px;margin:2px;}
QScrollBar::handle:vertical {background:#51475f;border-radius:4px;min-height:30px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QTabWidget::pane {border:0;}
QTabBar::tab {background:#24212f;color:#aaa4ba;padding:10px 15px;border-radius:7px;margin:0 5px 10px 0;}
QTabBar::tab:selected {background:#443655;color:#f3eaff;}
QTabBar::tab:focus {border:1px solid #bba1ff;}
QProgressBar {background:#171620;border:0;border-radius:4px;height:7px;text-align:center;}
QProgressBar::chunk {background:#bba1ff;border-radius:4px;}
QMenu {background:#24212e;border:1px solid #494055;padding:6px;}
QMenu::item {padding:9px 24px;border-radius:5px;}
QMenu::item:selected {background:#493957;}
QToolTip {background:#302839;color:#f4eaff;border:1px solid #796589;padding:6px;}
'''


def label(text='',role=None):
    item = QLabel(text)
    item.setTextFormat(Qt.PlainText)
    item.setWordWrap(True)
    if role: item.setProperty('role',role)
    return item


def button(text,callback,primary=False):
    item = QPushButton(text)
    item.setCursor(Qt.PointingHandCursor)
    item.setProperty('primary',primary)
    item.clicked.connect(callback)
    return item


def card(title='',description='',hero=False):
    box = QFrame()
    box.setObjectName('hero' if hero else 'card')
    layout = QVBoxLayout(box)
    layout.setContentsMargins(22,20,22,20)
    layout.setSpacing(12)
    if title: layout.addWidget(label(title,'heading'))
    if description: layout.addWidget(label(description,'muted'))
    return box,layout


def form():
    layout = QFormLayout()
    layout.setSpacing(14)
    layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    layout.setRowWrapPolicy(QFormLayout.WrapLongRows)
    layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    return layout


def brand_mark(size):
    # Render the original artwork in a round viewport; asset files stay intact.
    source = QPixmap(str(Path(__file__).resolve().parent/'assets/vowely.png'))
    canvas = QPixmap(size,size);canvas.fill(Qt.transparent)
    painter = QPainter(canvas);painter.setRenderHint(QPainter.Antialiasing);painter.setRenderHint(QPainter.SmoothPixmapTransform)
    clip = QPainterPath();clip.addEllipse(QRectF(1,1,size-2,size-2));painter.setClipPath(clip)
    painter.drawPixmap(QRectF(0,0,size,size),source,QRectF(source.width()*.12,source.height()*.105,source.width()*.76,source.height()*.76));painter.end()
    item = QLabel();item.setPixmap(canvas);item.setAlignment(Qt.AlignCenter)
    glow = QGraphicsDropShadowEffect(item);glow.setBlurRadius(30);glow.setOffset(0,0);glow.setColor(QColor(151,117,239,65));item.setGraphicsEffect(glow)
    return item


def nav_icon(index):
    pixmap = QPixmap(24,24);pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap);painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor('#c8bcdf'),1.7,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
    if index==0:
        painter.drawPolyline([QPoint(*p) for p in [(3,11),(12,3),(21,11)]])
        painter.drawRoundedRect(6,10,12,11,2,2);painter.drawLine(11,21,11,15)
    elif index==1:
        painter.drawRoundedRect(9,3,6,12,3,3);painter.drawArc(6,7,12,12,180*16,180*16);painter.drawLine(12,19,12,22)
    elif index==2:
        painter.drawRoundedRect(4,4,16,17,2,2);painter.drawLine(8,4,8,21);painter.drawLine(11,10,17,10);painter.drawLine(11,14,16,14)
    elif index==3:
        painter.drawRoundedRect(5,5,14,14,3,3)
        for n in (8,12,16):
            painter.drawLine(n,2,n,5);painter.drawLine(n,19,n,22);painter.drawLine(2,n,5,n);painter.drawLine(19,n,22,n)
    elif index==4:
        for n,y in enumerate((6,12,18)):
            painter.drawLine(3,y,21,y);painter.setBrush(QColor('#1a1923'));painter.drawEllipse(7+(n%2)*7,y-3,6,6)
    else:
        painter.drawEllipse(3,3,18,18);painter.drawLine(12,11,12,17);painter.drawPoint(12,7)
    painter.end()
    return QIcon(pixmap)


class DesktopUI:
    NAMES = ('Home','Dictation','Vocabulary','Models','Settings','Help')

    def __init__(self,w):
        self.w = w
        self.assets = []
        self.onboarding_step = 0
        self._asset_signature = None
        w.setWindowTitle(f'Vowely {RELEASE_VERSION} • Offline dictation')
        screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        w.resize(min(1120,area.width()-50) if area else 1120,min(780,area.height()-60) if area else 780)
        w.setMinimumSize(760,540)
        assets = Path(__file__).resolve().parent/'assets'
        w.setStyleSheet(STYLE.replace('CHECK_MARK',(assets/'check.svg').as_posix()).replace('CHEVRON',(assets/'chevron.svg').as_posix()))
        shell = QWidget();shell.setObjectName('shell')
        outer = QHBoxLayout(shell);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        self.sidebar = QFrame();self.sidebar.setObjectName('sidebar');self.sidebar.setFixedWidth(196)
        side = QVBoxLayout(self.sidebar);side.setContentsMargins(14,22,14,18);side.setSpacing(6)
        brand = QHBoxLayout();logo = QLabel();logo.setPixmap(application_icon().pixmap(34,34));brand.addWidget(logo)
        self.brand_name = label('Vowely','heading');brand.addWidget(self.brand_name);brand.addStretch();side.addLayout(brand);side.addSpacing(30)
        self.nav = []
        navigation=QWidget()
        nav_layout=QVBoxLayout(navigation);nav_layout.setContentsMargins(0,0,0,0);nav_layout.setSpacing(6)
        nav_scroll=QScrollArea();nav_scroll.setWidgetResizable(True);nav_scroll.setWidget(navigation)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);side.addWidget(nav_scroll,1)
        group = QButtonGroup(w);group.setExclusive(True)
        for index,name in enumerate(self.NAMES):
            item = button('  '+name,lambda checked=False,i=index:self.navigate(i))
            item.setIcon(nav_icon(index));item.setIconSize(QSize(22,22));item.setCheckable(True);item.setProperty('nav',True)
            item.setToolTip(f'{name} · Alt+{index+1}');item.setAccessibleName(name)
            group.addButton(item);self.nav.append(item);nav_layout.addWidget(item)
            shortcut = QShortcut(QKeySequence(f'Alt+{index+1}'),w)
            shortcut.activated.connect(lambda i=index:self.navigate(i))
        nav_layout.addStretch()
        from .update_ui import UpdateNotice
        self.update_notice=UpdateNotice(w);side.addWidget(self.update_notice)
        self.side_privacy = label('ON THIS PC\nNo transcript history','muted');side.addWidget(self.side_privacy)
        self.version = label(RELEASE_VERSION,'muted');side.addWidget(self.version)
        outer.addWidget(self.sidebar)
        main = QVBoxLayout();main.setContentsMargins(0,0,0,0);main.setSpacing(0)
        header = QHBoxLayout();header.setContentsMargins(30,18,30,10)
        self.breadcrumb = label('WORKSPACE / HOME','eyebrow');self.breadcrumb.setWordWrap(False);header.addWidget(self.breadcrumb,1)
        badge = label('●  Offline');badge.setObjectName('offline');header.addWidget(badge);main.addLayout(header)
        self.stack = QStackedWidget();main.addWidget(self.stack,1)
        self.footer = QFrame();footer_layout=QHBoxLayout(self.footer);footer_layout.setContentsMargins(30,12,30,16)
        self.footer_status=label('Settings stay on this PC.','muted');footer_layout.addWidget(self.footer_status,1)
        self.footer_save=button('Save changes',w.apply_settings,True);footer_layout.addWidget(self.footer_save)
        self.footer.setVisible(False);main.addWidget(self.footer)
        outer.addLayout(main,1);w.setCentralWidget(shell)
        self.pages,self.page_layouts = [],[]
        for title,subtitle in [('Home','A little less typing. A little more flow.'),
                ('Current dictation','Review the current session. Nothing here is saved as history.'),
                ('Vocabulary','Names and words that sound like you.'),('Models & performance','Local recognition and cleanup, tuned to your PC.'),
                ('Settings','Make dictation feel at home.'),('Help & diagnostics','Check your setup without sending anything off this PC.')]:
            page = QWidget();layout = QVBoxLayout(page);layout.setContentsMargins(30,18,30,30);layout.setSpacing(18)
            layout.addWidget(label(title,'title'));layout.addWidget(label(subtitle,'muted'))
            scroll = QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page)
            self.stack.addWidget(scroll);self.pages.append(page);self.page_layouts.append(layout)
        self.build_controls()
        self.build_home();self.build_editor();self.build_vocabulary();self.build_models();self.build_settings();self.build_help();self.build_onboarding()
        self.nav[0].setChecked(True)
        w.preview.textChanged.connect(self.result_changed)
        self.timer = QTimer(w);self.timer.setInterval(120);self.timer.timeout.connect(self.refresh);self.timer.start()

    def build_controls(self):
        w,c = self.w,self.w.c
        w.status = label('Starting dictation • microphone off','muted')
        w.mode = QComboBox();w.mode.addItems(['Natural','Verbatim','Developer']);w.mode.setCurrentText(c.mode)
        w.model = QComboBox();w.model.addItems(['base','small']);w.model.setCurrentText(c.asr_model)
        w.search_quality = QComboBox();w.search_quality.addItem('Faster decoding',1);w.search_quality.addItem('More thorough decoding',5)
        # Keep intermediate existing beam sizes instead of silently mapping to 5.
        if c.beam_size not in (1,5): w.search_quality.addItem(f'Existing search width ({c.beam_size})',c.beam_size)
        w.search_quality.setCurrentIndex(w.search_quality.findData(c.beam_size))
        w.vocabulary = QLineEdit(', '.join(c.personal_vocabulary));w.vocabulary.setPlaceholderText('Names or phrases, separated by commas')
        w.learn = QCheckBox('Learn spelling corrections after dictation');w.learn.setChecked(c.learn_corrections)
        w.learn.setToolTip('Compares edited drafts when you leave the box or it clears. No typing pause is needed.')
        w.dictionary_status = label('Corrected spellings stay on this PC.' if w.dictionary.available else 'Local dictionary could not be loaded; learning is unavailable.','muted')
        w.dictionary_button = button(f'Learned words ({len(w.dictionary.words)})',lambda:self.navigate(2))
        w.backend = QComboBox();w.backend.addItems(['CPU','NVIDIA CUDA']);w.backend.setCurrentIndex(int(c.gpu))
        w.cleanup_backend = QComboBox();w.cleanup_backend.addItems(['CPU','NVIDIA CUDA (live mode)']);w.cleanup_backend.setCurrentIndex(int(c.cleanup_gpu))
        w.language = QLineEdit(c.language);w.language.setPlaceholderText('auto, en, hi…')
        w.vad = QCheckBox('Use local Silero voice detection');w.vad.setChecked(bool(c.vad_model))
        w.hotkey = ShortcutEdit(c.hotkey,name='Hold to dictate shortcut')
        w.toggle_hotkey = ShortcutEdit(c.toggle_hotkey,optional=True,name='Press to start or stop shortcut')
        w.mic = QComboBox();w.mic.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);w.mic.setMinimumContentsLength(18)
        w.all_inputs = QCheckBox('Show all audio inputs (advanced)');w.populate_microphones(c.microphone);w.all_inputs.toggled.connect(w.change_microphone_view)
        w.cleanup = QCheckBox('Use Qwen for local text cleanup');w.cleanup.setChecked(c.cleanup_enabled)
        w.live = QCheckBox('Live preview and sentence-based cleanup');w.live.setChecked(c.streaming_enabled)
        w.insert = QCheckBox('Automatically type the final result into the focused box');w.insert.setChecked(c.auto_insert)
        w.preserve_lines=QCheckBox('Preserve paragraph and list line breaks');w.preserve_lines.setChecked(c.preserve_line_breaks)
        w.preserve_lines.setToolTip('Multiline results use a temporary clipboard paste, excluded from Windows history and sync. The previous clipboard is restored after insertion is verified. Disable for keyboard-only soft breaks.')
        w.models_status = label('Models are not loaded • microphone off','muted')
        w.prepare_button = button('Load / reload models',w.prepare_live,True)
        w.unload_button = button('Free model memory',w.unload_models)
        w.pause = button('Resume dictation',w.toggle_dictation)
        w.record_button = button('Record a test • preview only',w.manual_record,True)
        w.file_button = button('Transcribe a local WAV file • preview only',w.transcribe_file)
        w.copy_button = button('Copy reviewed result',w.copy_result,True)
        w.clear_button = button('Clear text from memory',w.forget_result)
        w.preview = QTextEdit();w.preview.setAcceptRichText(False);w.preview.setMinimumHeight(230)
        w.preview.setAccessibleName('Current dictation result');w.preview.setPlaceholderText('Your words will appear here. Edit the final result before copying it.')
        w.original = QTextEdit();w.original.setReadOnly(True);w.original.setMinimumHeight(140);w.original.setMaximumHeight(240)
        w.original.setAccessibleName('Original Whisper recognition');w.original.setPlaceholderText('Original words before cleanup appear here.')
        self.threads = QSpinBox();self.threads.setRange(1,8);self.threads.setValue(c.threads)
        self.duration = QSpinBox();self.duration.setRange(1,300);self.duration.setSuffix(' seconds');self.duration.setValue(c.max_seconds)
        self.timeout = QSpinBox();self.timeout.setRange(1,600);self.timeout.setSuffix(' seconds');self.timeout.setValue(c.inference_timeout)
        self.deny_processes = QTextEdit();self.deny_processes.setAcceptRichText(False);self.deny_processes.setPlainText('\n'.join(c.deny_processes));self.deny_processes.setMaximumHeight(140)
        self.deny_names = QTextEdit();self.deny_names.setAcceptRichText(False);self.deny_names.setPlainText('\n'.join(c.deny_name_fragments));self.deny_names.setMaximumHeight(140)
        w.controls = [w.mode,w.model,w.hotkey,w.toggle_hotkey,w.mic,w.cleanup,w.insert,w.preserve_lines,w.backend,w.language,w.vad,w.all_inputs,
                      w.search_quality,w.vocabulary,w.cleanup_backend,w.live,w.learn,self.threads,self.duration,self.timeout,self.deny_processes,self.deny_names]

    def build_home(self):
        w = self.w;layout = self.page_layouts[0]
        layout.itemAt(0).widget().hide();layout.itemAt(1).widget().hide()
        hero,body = card(hero=True)
        row = QHBoxLayout();left = QVBoxLayout();left.setSpacing(8)
        left.addWidget(label('YOUR VOICE, IN YOUR FLOW','eyebrow'))
        self.home_state = label('Ready','state');left.addWidget(self.home_state)
        left.addWidget(w.status)
        self.shortcut_label = label(w.c.hotkey,'heading');left.addWidget(self.shortcut_label)
        left.addWidget(w.pause,0,Qt.AlignLeft);row.addLayout(left,1)
        self.hero_logo = brand_mark(132)
        row.addWidget(self.hero_logo);body.addLayout(row)
        self.home_busy=QProgressBar();self.home_busy.setRange(0,0);self.home_busy.setTextVisible(False);self.home_busy.setAccessibleName('Local operation in progress');self.home_busy.hide();body.addWidget(self.home_busy)
        layout.addWidget(hero)
        self.summary_grid = QGridLayout();self.summary_grid.setSpacing(12);self.summary_cards=[];self.summary_values=[]
        for title in ('MODE','RECOGNITION','LANGUAGE'):
            box,inner = card();inner.addWidget(label(title,'eyebrow'));value=label('','heading');inner.addWidget(value)
            self.summary_cards.append(box);self.summary_values.append(value)
        layout.addLayout(self.summary_grid);self.adapt()
        latest,inner = card('Latest transcription','Current session only. Clear it any time.')
        self.home_preview = QTextEdit();self.home_preview.setReadOnly(True);self.home_preview.setDocument(w.preview.document())
        self.home_preview.setFixedHeight(124);self.home_preview.setPlaceholderText('Your next dictation will appear here.')
        self.home_preview.setAccessibleName('Latest transcription preview');inner.addWidget(self.home_preview)
        actions=QHBoxLayout();actions.addWidget(button('Open editor',lambda:self.navigate(1),True));actions.addWidget(w.dictionary_button);actions.addStretch();inner.addLayout(actions)
        layout.addWidget(latest)
        status,inner = card('Audio input');self.home_microphone=label('','muted');inner.addWidget(self.home_microphone)
        layout.addWidget(status);layout.addStretch()

    def build_editor(self):
        w=self.w;layout=self.page_layouts[1]
        self.editor_state=label('Microphone off','eyebrow');layout.addWidget(self.editor_state)
        self.editor_meter=QProgressBar();self.editor_meter.setRange(0,100);self.editor_meter.setTextVisible(False);self.editor_meter.setAccessibleName('Microphone level');layout.addWidget(self.editor_meter)
        box,inner=card('Result','Provisional words can change. Only the final result is typed into another app.')
        inner.addWidget(w.preview)
        actions=QHBoxLayout();actions.addWidget(w.copy_button);actions.addWidget(w.clear_button);actions.addStretch();inner.addLayout(actions)
        self.character_count=label('0 characters','muted');inner.addWidget(self.character_count);layout.addWidget(box)
        original,inner=card('Original recognition','Compare Whisper’s original words with the cleaned result.');inner.addWidget(w.original);layout.addWidget(original)
        layout.addWidget(button('Cancel current recording / processing',w.abort),0,Qt.AlignLeft)
        layout.addStretch()

    def edit_notice(self,layout):
        box,inner=card()
        row=QHBoxLayout();message=label('Pause dictation to edit settings. Pausing clears the current result and model context.','muted');row.addWidget(message,1)
        item=button('Pause to edit',self.w.toggle_dictation);row.addWidget(item);inner.addLayout(row);layout.addWidget(box)
        if not hasattr(self,'edit_buttons'):self.edit_buttons=[]
        self.edit_buttons.append(item)
        return box

    def build_vocabulary(self):
        w=self.w;layout=self.page_layouts[2];self.edit_notice(layout)
        box,inner=card('Personal spelling hints','Names and phrases are supplied to Whisper and Qwen. They help spelling; they do not retrain either model.')
        inner.addWidget(w.vocabulary);inner.addWidget(w.learn)
        inner.addWidget(button('Save vocabulary',w.apply_settings,True),0,Qt.AlignLeft);self.vocab_save=inner.itemAt(inner.count()-1).widget()
        layout.addWidget(box)
        box,inner=card('Learned words','Vowely compares corrected drafts when the box clears or you leave it. No typing pause is required.')
        self.word_search=QLineEdit();self.word_search.setPlaceholderText('Search learned words');self.word_search.setAccessibleName('Search learned words');self.word_search.textChanged.connect(self.filter_words);inner.addWidget(self.word_search)
        self.word_list=QListWidget();self.word_list.setSelectionMode(QAbstractItemView.ExtendedSelection);self.word_list.setMinimumHeight(190);self.word_list.setAccessibleName('Learned vocabulary');inner.addWidget(self.word_list)
        self.word_empty=label('No learned words yet. Correct a dictation in the same text box, then send or leave the field.','muted');inner.addWidget(self.word_empty)
        self.remove_words=button('Remove selected words',self.remove_selected_words);inner.addWidget(self.remove_words,0,Qt.AlignLeft)
        inner.addWidget(w.dictionary_status);layout.addWidget(box);layout.addStretch();self.word_list.itemSelectionChanged.connect(self.refresh_word_actions)
        self.sync_words()

    def build_models(self):
        w=self.w;layout=self.page_layouts[3];self.edit_notice(layout)
        box,inner=card('Recognition · Whisper','Base is lighter. Small can improve recognition at a higher processing cost. Measure on your hardware.')
        fields=form();fields.addRow('Model',w.model);fields.addRow('Run recognition on',w.backend);fields.addRow('Decoding quality',w.search_quality);inner.addLayout(fields);layout.addWidget(box)
        box,inner=card('Cleanup · Qwen','The local language model cleans text after recognition. Verbatim bypasses cleanup.')
        inner.addWidget(w.cleanup);fields=form();fields.addRow('Run cleanup on',w.cleanup_backend);inner.addLayout(fields);inner.addWidget(w.live)
        inner.addWidget(label('Live mode uses agreeing sentence punctuation from Whisper. Stop rechecks the complete recording; final typing happens once.','muted'));layout.addWidget(box)
        box,inner=card('Model memory');inner.addWidget(w.models_status)
        row=QHBoxLayout();row.addWidget(w.prepare_button);row.addWidget(w.unload_button);row.addStretch();inner.addLayout(row)
        self.model_save=button('Apply model settings',w.apply_settings,True);inner.addWidget(self.model_save,0,Qt.AlignLeft);layout.addWidget(box)
        box,inner=card('Last dictation timing','Measured by the existing engine on this PC. Timing varies with each recording and includes the processing described below.')
        self.performance_summary=label('Complete a dictation to see its processing time and actual backend outcome.','muted');inner.addWidget(self.performance_summary);layout.addWidget(box)
        box,inner=card('Installed local assets','Presence checks run in the background. They do not download files or verify model accuracy.')
        self.asset_status=label('Run a check to inspect the configured engines and models.','muted');inner.addWidget(self.asset_status)
        self.asset_list=QListWidget();self.asset_list.setMinimumHeight(200);self.asset_list.setAccessibleName('Local model and engine checks');inner.addWidget(self.asset_list)
        self.asset_check=button('Check local files',w.check_assets);inner.addWidget(self.asset_check,0,Qt.AlignLeft);layout.addWidget(box)
        layout.addWidget(label('No latency promise: microphone, accent, decoding quality, CPU load, GPU memory and driver/build all affect results. Your active backend is reported above.','muted'));layout.addStretch()

    def build_settings(self):
        w=self.w;layout=self.page_layouts[4];self.settings_edit_notice=self.edit_notice(layout)
        self.settings_tabs=QTabWidget();self.settings_tabs.setAccessibleName('Settings categories')
        categories=[]
        for name in ('Audio','Dictation','Performance','Privacy'):
            page=QWidget();body=QVBoxLayout(page);body.setContentsMargins(0,4,0,4);body.setSpacing(16);categories.append(body);self.settings_tabs.addTab(page,name)
        box,inner=card('Microphone','Choose the physical input you want. Advanced inputs reveal additional Windows audio interfaces.')
        fields=form();fields.addRow('Input device',w.mic);inner.addLayout(fields);inner.addWidget(w.all_inputs);inner.addWidget(w.vad)
        row=QHBoxLayout();self.refresh_mics=button('Refresh inputs',lambda:w.populate_microphones(w.mic.currentData()));row.addWidget(self.refresh_mics)
        self.audio_test=button('Test microphone · 3 seconds',w.test_microphone);row.addWidget(self.audio_test);row.addStretch();inner.addLayout(row)
        self.audio_level=QProgressBar();self.audio_level.setTextVisible(False);self.audio_level.setRange(0,100);self.audio_level.setAccessibleName('Microphone diagnostic level');inner.addWidget(self.audio_level)
        self.audio_status=label('The microphone opens only when you explicitly test or dictate. Test audio is discarded.','muted');inner.addWidget(self.audio_status);categories[0].addWidget(box)
        box,inner=card('Dictation shortcuts','Pause dictation from Home to change keys. Select Set keys and press a combination, or type it in the field. Save, then Resume from Home.')
        fields=form();fields.addRow('Hold to dictate',w.hotkey);fields.addRow('Press to start / stop',w.toggle_hotkey);inner.addLayout(fields)
        inner.addWidget(label('Hold: release any key to finish. Toggle: press once to listen, release, then press the same combination again to finish. Both shortcuts can be available together. Leaving the toggle field empty disables it.','muted'))
        inner.addWidget(label('Use Ctrl / Alt / Shift with a function key (except F12) or Space. Letters and digits need two modifiers, e.g. Ctrl+Alt+D. Windows-key and modifier-only combinations are unavailable. Chosen shortcuts are reserved globally while dictation is active; app-specific shortcuts cannot always be detected.','muted'));categories[1].addWidget(box)
        box,inner=card('How your words are handled');fields=form();fields.addRow('Mode',w.mode);fields.addRow('Language',w.language);inner.addLayout(fields);inner.addWidget(w.insert)
        inner.addWidget(label('Natural removes fillers and fixes punctuation. Developer preserves technical terms. Verbatim keeps recognition without Qwen. Shortcut conflicts are reported; no silent remapping.','muted'))
        inner.addWidget(button('Recognition & cleanup settings',lambda:self.navigate(3)),0,Qt.AlignLeft);categories[1].addWidget(box)
        box,inner=card('Processing limits','Changes affect future recordings. Existing model paths and custom configuration values are preserved.')
        fields=form();fields.addRow('CPU threads',self.threads);fields.addRow('Maximum recording',self.duration);fields.addRow('Inference timeout',self.timeout);inner.addLayout(fields);categories[2].addWidget(box)
        box,inner=card('Typing safeguards','Password, sensitive, denied and unknown controls are blocked. No Enter-key submission. Formatted multiline typing temporarily uses the clipboard, excluded from Windows history and sync, then verifies the target before restoration.')
        inner.addWidget(w.preserve_lines)
        inner.addWidget(label('Disable paragraph preservation for keyboard-only typing with soft line separators. If a paste is interrupted, check the typing box before retrying. A previous clipboard can be recovered here only while no newer copy has replaced it.','muted'))
        self.restore_clipboard=button('Recover previous clipboard',lambda:w.recover_clipboard())
        inner.addWidget(self.restore_clipboard)
        inner.addWidget(label('Blocked processes · one executable name per line','muted'));inner.addWidget(self.deny_processes)
        inner.addWidget(label('Sensitive field names · one fragment per line','muted'));inner.addWidget(self.deny_names)
        inner.addWidget(label('Audio and current text are held locally. No transcript history, external inference, telemetry or cloud sync. Model downloads and update installation require explicit action. Learned spellings are retained locally until removed.','muted'));categories[3].addWidget(box)
        for body in categories:body.addStretch()
        from .update_ui import UpdatePanel
        w.updates=UpdatePanel(w,self.update_notice);self.settings_tabs.addTab(w.updates,'Updates')
        layout.addWidget(self.settings_tabs)
        self.settings_save=button('Save settings',w.apply_settings,True);layout.addWidget(self.settings_save,0,Qt.AlignLeft)
        self.save_status=label('','muted');layout.addWidget(self.save_status);layout.addStretch()
        self.settings_tabs.currentChanged.connect(self.settings_category_changed)

    def settings_category_changed(self,index):
        updates=index==4
        self.settings_edit_notice.setVisible(not updates);self.settings_save.setVisible(not updates);self.save_status.setVisible(not updates)
        self.footer.setVisible(self.stack.currentIndex() in (2,3) or (self.stack.currentIndex()==4 and not updates))

    def build_help(self):
        w=self.w;layout=self.page_layouts[5]
        box,inner=card('A quick way to get started','Focus an editable text box. Hold your hold shortcut to speak and release to finish, or use the optional toggle shortcut: press once to start, again to stop. Stay in the box while the ring finishes. Vowely types the final result once. Configure both in Settings → Dictation.')
        inner.addWidget(button('Revisit setup',self.open_onboarding,True),0,Qt.AlignLeft);layout.addWidget(box)
        box,inner=card('Lists and paragraph breaks','With Qwen cleanup enabled, ordinary tools, names and groceries stay in sentences. Distinct tasks or requests can become bullets; “the first one is … the second one is …” can become numbered items. Commas alone do not request a list. Say “new paragraph” or “paragraph break” for a blank line; “new line” for one break. Natural mode removes fillers and repetitions. Review unclear words and corrections. Verbatim keeps recognized words.')
        inner.addWidget(label('Stable sentences still go to Qwen while you speak. After Stop, a final formatting check connects the passage; longer recordings use bounded context blocks. This can add processing time. Automatic topic breaks and unclear item boundaries need review.','muted'));layout.addWidget(box)
        box,inner=card('Preview-only tests','These actions never type into another app. WAV input must be uncompressed 16 kHz, mono, PCM16 and under 120 seconds.')
        inner.addWidget(w.record_button);inner.addWidget(w.file_button);inner.addWidget(button('Open current result',lambda:self.navigate(1)))
        self.help_sample_status=label('Results stay in the current-session editor.','muted');inner.addWidget(self.help_sample_status);layout.addWidget(box)
        box,inner=card('Diagnostics','Local checks show missing files without collecting transcripts or making network requests.')
        inner.addWidget(button('Run local checks',w.check_assets),0,Qt.AlignLeft)
        self.help_checks=label('No checks run yet.','muted');inner.addWidget(self.help_checks)
        inner.addWidget(button('Audio input & microphone test',lambda:self.show_settings(0)),0,Qt.AlignLeft);layout.addWidget(box)
        box,inner=card('Install or repair models','For the installed app: Quit Vowely from the tray, then open “Finish Vowely setup” from Start. That screen checks existing files and asks before downloading missing models or optional NVIDIA support. Portable/source users can use the explicit setup script. Downloads never start while dictating.')
        layout.addWidget(box)
        box,inner=card('When something needs attention')
        for text in ['No input: choose a connected microphone, check its level, then run the three-second test.',
                     'Nothing typed: keep focus in the same editable box and release all shortcut keys. Manual tests are preview-only.',
                     'Models missing: use the explicit setup script described in SETUP.md. Vowely does not download models from this window.',
                     'Wrong words: try Small, select the language, add spelling hints, and compare the original recognition with cleanup.',
                     'Correction learning: supports eligible small text boxes with Windows accessibility. Custom fields may not expose every edit.',
                     'Close keeps Vowely in the tray. Use Pause to release the shortcut, or Quit to close models and exit.']:
            inner.addWidget(label(text,'muted'))
        layout.addWidget(box)
        box,inner=card('Local setup & benchmark guides','SETUP.md covers explicit downloads and offline transfer. PERFORMANCE.md explains measured timings. Advanced engine paths remain in config.json.')
        inner.addWidget(button('Open application folder',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(w.root)))),0,Qt.AlignLeft);layout.addWidget(box)
        layout.addWidget(label(f'Vowely {RELEASE_VERSION} · Python / PySide6 · whisper.cpp / llama.cpp\nFully local after explicit model and engine provisioning.','muted'));layout.addStretch()

    def build_onboarding(self):
        page=QWidget();body=QVBoxLayout(page);body.setContentsMargins(36,20,36,30);body.setSpacing(18)
        self.setup_title=label('Welcome to Vowely','title');body.addWidget(self.setup_title)
        self.setup_progress=label('SETUP / 1 OF 4','eyebrow');body.addWidget(self.setup_progress)
        self.setup_stack=QStackedWidget();body.addWidget(self.setup_stack)
        # Every step uses the same working controller; no simulated success.
        for _ in range(4):
            step=QWidget();layout=QVBoxLayout(step);layout.setContentsMargins(0,0,0,0);layout.setSpacing(18);self.setup_stack.addWidget(step)
        layout=self.setup_stack.widget(0).layout();logo=brand_mark(140);layout.addWidget(logo,0,Qt.AlignLeft)
        layout.addWidget(label('Local speech to text, built around your flow.','heading'))
        layout.addWidget(label('Your voice stays on this PC. Whisper recognizes speech; Qwen can clean the words. No account, transcript history or cloud speech processing.','muted'))
        layout.addWidget(label('We’ll check your microphone and model files, then try a short dictation. Downloads are always a separate, explicit setup step.','muted'));layout.addStretch()
        layout=self.setup_stack.widget(1).layout();box,inner=card('Choose your microphone','Speak at a normal volume during the three-second test. No test recording is saved.')
        self.setup_mic=QComboBox();self.setup_mic.setAccessibleName('Setup microphone');inner.addWidget(self.setup_mic)
        self.setup_use_mic=button('Use this microphone',self.use_setup_microphone);inner.addWidget(self.setup_use_mic,0,Qt.AlignLeft)
        self.setup_mic_test=button('Test microphone · 3 seconds',self.w.test_microphone,True);inner.addWidget(self.setup_mic_test,0,Qt.AlignLeft)
        self.setup_level=QProgressBar();self.setup_level.setRange(0,100);self.setup_level.setTextVisible(False);inner.addWidget(self.setup_level)
        self.setup_audio_status=label('Choose an input, apply it, then run the test.','muted');inner.addWidget(self.setup_audio_status);layout.addWidget(box);layout.addStretch()
        layout=self.setup_stack.widget(2).layout();box,inner=card('Check your local models','Whisper Base / Small and optional Qwen are the supported models. Existing choices are kept.')
        self.setup_models_status=label('Run the check to see which files are available.','muted');inner.addWidget(self.setup_models_status)
        inner.addWidget(button('Check model files',self.w.check_assets,True),0,Qt.AlignLeft)
        inner.addWidget(button('Open model settings',lambda:self.navigate(3)),0,Qt.AlignLeft)
        inner.addWidget(label('Missing files? Follow SETUP.md or “Setup models and engines.ps1”. This flow never starts a download.','muted'));layout.addWidget(box);layout.addStretch()
        layout=self.setup_stack.widget(3).layout();box,inner=card('Your shortcut. Your first words.','Choose a hold shortcut, e.g. Ctrl+Alt+F9. An optional press-to-start / stop shortcut is available in Settings → Dictation. Try: “This is my first dictation with Vowely.”')
        self.setup_hotkey=ShortcutEdit(name='Setup shortcut');inner.addWidget(self.setup_hotkey)
        self.setup_use_hotkey=button('Use this shortcut',self.use_setup_shortcut);inner.addWidget(self.setup_use_hotkey,0,Qt.AlignLeft)
        self.setup_sample=button('Record a sample · preview only',self.w.manual_record,True);inner.addWidget(self.setup_sample,0,Qt.AlignLeft)
        self.setup_result=QTextEdit();self.setup_result.setReadOnly(True);self.setup_result.setDocument(self.w.preview.document());self.setup_result.setMinimumHeight(100);self.setup_result.setMaximumHeight(190);inner.addWidget(self.setup_result)
        self.setup_sample_status=label('Sample recording uses the real local dictation pipeline.','muted');inner.addWidget(self.setup_sample_status);layout.addWidget(box);layout.addStretch()
        self.setup_notice=label('','muted');body.addWidget(self.setup_notice)
        row=QHBoxLayout();self.setup_back=button('Back',lambda:self.setup_step(self.onboarding_step-1));row.addWidget(self.setup_back)
        self.setup_cancel=button('Cancel current operation',self.w.abort);self.setup_cancel.hide();row.addWidget(self.setup_cancel)
        self.setup_skip=button('Skip setup for now',self.finish_onboarding);row.addWidget(self.setup_skip);row.addStretch()
        self.setup_next=button('Get started',self.advance_setup,True);row.addWidget(self.setup_next);body.addLayout(row)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(page);self.stack.addWidget(scroll)

    def open_onboarding(self):
        if self.w.needs_onboarding:
            try:
                (self.w.root/'ui-state.json').write_text(json.dumps({'version':1,'onboarding_completed':False}),encoding='utf-8')
            except OSError:self.setup_notice.setText('Setup progress cannot be saved in this folder.')
        self.w.reveal();self.stack.setCurrentIndex(6);self.breadcrumb.setText('GETTING STARTED / LOCAL SETUP')
        self.setup_mic.clear()
        for i in range(self.w.mic.count()):self.setup_mic.addItem(self.w.mic.itemText(i),self.w.mic.itemData(i))
        self.setup_mic.setCurrentIndex(max(0,self.setup_mic.findData(self.w.mic.currentData())))
        self.setup_hotkey.setText(self.w.hotkey.text());self.setup_step(0)

    def setup_step(self,index):
        self.onboarding_step=max(0,min(3,index));self.setup_stack.setCurrentIndex(self.onboarding_step)
        self.setup_title.setText(('Welcome to Vowely','Make sure we can hear you','Keep your models on this PC','Give it a try')[self.onboarding_step])
        self.setup_progress.setText(f'SETUP / {self.onboarding_step+1} OF 4')
        self.setup_back.setEnabled(self.onboarding_step>0)
        self.setup_next.setText('Finish setup' if self.onboarding_step==3 else 'Get started' if self.onboarding_step==0 else 'Continue')
        if self.onboarding_step==2:self.w.check_assets()

    def advance_setup(self):
        if self.onboarding_step==3:self.finish_onboarding()
        else:self.setup_step(self.onboarding_step+1)

    def finish_onboarding(self):
        if self.w.state!='idle':
            self.setup_notice.setText('Finish or cancel the current operation before closing setup.');return
        try:
            self.w.settings().save(self.w.config_path)
            path=self.w.root/'ui-state.json';temporary=path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'version':1,'onboarding_completed':True}),encoding='utf-8');temporary.replace(path)
        except (OSError,ValueError) as error:
            self.setup_notice.setText('Could not save setup. '+str(error));return
        self.w.needs_onboarding=False;self.navigate(0);self.w.start_automatically()

    def use_setup_microphone(self):
        if self.w.win.registered or self.w.state!='idle':self.setup_notice.setText('Pause dictation from Home before changing the microphone.');return
        self.w.mic.setCurrentIndex(self.w.mic.findData(self.setup_mic.currentData()))
        self.w.apply_settings();self.setup_audio_status.setText(self.w.status.text())

    def use_setup_shortcut(self):
        if self.w.win.registered or self.w.state!='idle':self.setup_notice.setText('Pause dictation from Home before changing the shortcut.');return
        self.w.hotkey.setText(self.setup_hotkey.text());self.w.apply_settings();self.setup_notice.setText(self.w.status.text())

    def navigate(self,index):
        self.stack.setCurrentIndex(index);self.nav[index].setChecked(True)
        self.breadcrumb.setText('WORKSPACE / '+self.NAMES[index].upper())
        if index==2:self.sync_words()
        if index==3 and not self.assets:self.w.check_assets()
        self.footer.setVisible(index in (2,3) or (index==4 and self.settings_tabs.currentIndex()!=4))

    def show_settings(self,index):
        self.navigate(4);self.settings_tabs.setCurrentIndex(index)

    def sync_words(self):
        signature=tuple(self.w.dictionary.words)
        if signature!=getattr(self,'_word_signature',None):
            self._word_signature=signature;self.word_list.clear();self.word_list.addItems(signature);self.filter_words()
            self.w.dictionary_button.setText(f'Learned words ({len(signature)})')
        self.word_empty.setVisible(not signature);self.refresh_word_actions()

    def filter_words(self):
        query=self.word_search.text().casefold()
        for i in range(self.word_list.count()):
            item=self.word_list.item(i);item.setHidden(query not in item.text().casefold())

    def refresh_word_actions(self):
        self.remove_words.setEnabled(self.w.state=='idle' and bool(self.word_list.selectedItems()) and self.w.dictionary.available)

    def remove_selected_words(self):
        self.w.stop_learning()
        try:
            self.w.dictionary.remove([item.text() for item in self.word_list.selectedItems()])
            self.w.dictionary_button.setText(f'Learned words ({len(self.w.dictionary.words)})')
            self.w.dictionary_status.setText('Selected words removed from future spelling hints.');self.sync_words()
        except OSError:self.w.dictionary_status.setText('Could not update the local dictionary.')

    def result_changed(self):
        self.character_count.setText(f'{len(self.w.preview.toPlainText()):,} characters · current session only')

    def asset_results(self,rows):
        self.assets=rows;self.asset_list.clear()
        for name,present,size in rows:
            self.asset_list.addItem(f'{"Present" if present else "Missing"}   {name}'+(f'   ·   {size/1024/1024:.1f} MB' if present and size else ''))
        missing=[name for name,present,_ in rows if not present]
        message='Local check complete. '+('Missing: '+', '.join(missing) if missing else 'All checked files are present.')
        self.asset_status.setText(message);self.help_checks.setText(message);self.setup_models_status.setText(message)
        self.asset_check.setEnabled(True)

    def microphone_result(self,result):
        self.audio_status.setText(result['message']);self.setup_audio_status.setText(result['message']);self.microphone_level(0)

    def microphone_level(self,level):
        self.audio_level.setValue(round(level*100));self.setup_level.setValue(round(level*100))

    def adapt(self):
        narrow=self.w.width()<950
        self.sidebar.setFixedWidth(68 if narrow else 196)
        self.brand_name.setVisible(not narrow);self.side_privacy.setVisible(not narrow);self.version.setVisible(not narrow)
        self.update_notice.set_compact(narrow)
        if hasattr(self.w,'updates'):self.update_notice.refresh(self.w.updates)
        for i,item in enumerate(self.nav):item.setText('' if narrow else '  '+self.NAMES[i])
        if hasattr(self,'summary_grid'):
            for i,box in enumerate(self.summary_cards):self.summary_grid.addWidget(box,0,i)

    def refresh(self):
        w=self.w;busy=w.state!='idle';active=w.win.registered
        paste=w.win.formatted_paste
        self.restore_clipboard.setEnabled(not busy and paste is not None and paste.recovery_available)
        w.updates.refresh()
        state={'recording':'Listening…','processing':'Finishing…','replaying':'Replaying audio','preparing':'Loading models…',
               'audio_testing':'Checking microphone','stopping_audio':'Stopping microphone','inserting':'Inserting text…','stopping':'Closing models…'}.get(w.state,'Ready' if active else 'Paused')
        self.home_state.setText(state)
        self.home_busy.setVisible(busy and w.state!='recording')
        self.shortcut_label.setText('Hold · '+w.c.hotkey+ ('\nStart / stop · '+w.c.toggle_hotkey if w.c.toggle_hotkey else ''))
        self.summary_values[0].setText(w.c.mode);self.summary_values[1].setText('Whisper '+w.c.asr_model.title());self.summary_values[2].setText('Automatic' if w.c.language=='auto' else w.c.language.upper())
        self.home_microphone.setText('Input · '+w.mic.currentText())
        self.editor_state.setText(state+' · '+w.status.text())
        self.editor_meter.setValue(round(getattr(w.recorder,'input_level',0)*100))
        self.help_sample_status.setText(w.status.text());self.setup_sample_status.setText(w.status.text())
        for item in self.edit_buttons:item.setText('Pause to edit' if active else 'Dictation paused');item.setEnabled(active)
        for item in (self.vocab_save,self.settings_save,self.model_save):item.setEnabled(not busy and not active)
        self.refresh_mics.setEnabled(not busy and not active)
        for item in (self.audio_test,self.setup_mic_test):item.setEnabled(not busy and w.pool.activeThreadCount()==0)
        self.setup_use_mic.setEnabled(not busy and not active);self.setup_use_hotkey.setEnabled(not busy and not active)
        self.setup_sample.setEnabled(w.state in ('idle','recording'))
        self.setup_sample.setText('Stop recording' if w.state=='recording' else 'Record a sample · preview only')
        self.setup_next.setEnabled(not busy);self.setup_skip.setEnabled(not busy)
        self.setup_cancel.setVisible(busy)
        self.footer_save.setEnabled(not busy and not active)
        self.footer_status.setText(w.status.text())
        if w.last_metrics:
            metrics=w.last_metrics
            timing=f"After Stop: {metrics['tail_ms']:,} ms" if 'tail_ms' in metrics else f"Local processing: {metrics.get('total_ms',0):,} ms (includes loading)"
            if 'asr_ms' in metrics:timing+=f" · Recognition: {metrics['asr_ms']:,} ms"
            timing+='\nWhisper GPU used: '+('yes' if metrics.get('gpu_used') else 'no')
            if 'cleanup_gpu_used' in metrics:timing+=' · Qwen GPU used: '+('yes' if metrics['cleanup_gpu_used'] else 'no')
            if metrics.get('cpu_fallback'):timing+=' · CPU fallback used'
            self.performance_summary.setText(timing)
        else:self.performance_summary.setText('Complete a dictation to see its processing time and actual backend outcome.')
        if hasattr(w,'tray_cancel'):
            w.tray_cancel.setEnabled(busy)
            w.tray_free.setEnabled(not busy and w.runtime is not None)
        self.sync_words()
