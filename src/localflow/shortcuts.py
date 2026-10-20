"""Keyboard shortcut picker; captures only while its field has explicit focus."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QWidget, QLineEdit, QPushButton, QHBoxLayout, QVBoxLayout, QLabel

from .windows import parse_hotkey


class KeyField(QLineEdit):
    def keyPressEvent(self, event):
        owner = self.parentWidget()
        if not owner.capturing:
            return super().keyPressEvent(event)
        event.accept()
        if event.key() == Qt.Key_Escape:
            owner.finish_capture()
            return
        if event.key() in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, Qt.Key_AltGr):
            return
        if event.isAutoRepeat(): return
        text = QKeySequence(event.keyCombination()).toString(QKeySequence.PortableText)
        try:
            parse_hotkey(text)
        except ValueError as error:
            owner.notice.setText(str(error))
            return
        self.setText(text)
        owner.finish_capture()

    def focusOutEvent(self, event):
        if self.parentWidget().capturing: self.parentWidget().finish_capture()
        super().focusOutEvent(event)


class ShortcutEdit(QWidget):
    def __init__(self, text='', optional=False, name='Shortcut'):
        super().__init__()
        self.capturing = False
        self.field = KeyField(self)
        self.field.setText(text)
        self.field.setAccessibleName(name)
        self.field.setPlaceholderText('Disabled · leave empty' if optional else 'e.g. Ctrl+Alt+F9')
        self.setFocusProxy(self.field)
        self.capture = QPushButton('Set keys')
        self.capture.setAccessibleName('Set '+name.lower())
        self.capture.clicked.connect(self.start_capture)
        row = QHBoxLayout();row.setContentsMargins(0,0,0,0)
        row.addWidget(self.field,1);row.addWidget(self.capture)
        body = QVBoxLayout(self);body.setContentsMargins(0,0,0,0);body.addLayout(row)
        self.notice = QLabel();self.notice.setWordWrap(True);self.notice.hide();body.addWidget(self.notice)
        if optional:
            clear = QPushButton('Disable');clear.clicked.connect(lambda:self.setText(''));row.addWidget(clear)

    def text(self): return self.field.text()

    def setText(self, text):
        self.finish_capture()
        self.field.setText(text)

    def start_capture(self):
        self.capturing = True
        self.field.setReadOnly(True)
        self.field.setFocus(Qt.OtherFocusReason)
        self.notice.setText('Press your combination now. Escape cancels.');self.notice.show()

    def finish_capture(self):
        self.capturing = False
        self.field.setReadOnly(False)
        self.notice.hide()
