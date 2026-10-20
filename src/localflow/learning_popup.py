"""Nonactivating local feedback listing only newly learned spellings."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget


class LearningPopup(QWidget):
    def __init__(self):
        super().__init__(None,Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowTitle('Vowely • words added')
        self.setStyleSheet('QWidget {background:#252130; color:#f3edff; border-radius:12px;} QLabel {background:transparent;}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18,14,18,14)
        self.title = QLabel('Added to your dictionary')
        self.title.setStyleSheet('font-weight:600; color:#cfbfff;')
        layout.addWidget(self.title)
        self.words = QLabel()
        self.words.setTextFormat(Qt.PlainText)
        self.words.setWordWrap(True)
        layout.addWidget(self.words)
        self.setFixedWidth(440)
        self.dismiss = QTimer(self)
        self.dismiss.setSingleShot(True)
        self.dismiss.timeout.connect(self.hide)

    def show_words(self,words):
        if not words: return
        self.words.setText(' · '.join(words))
        self.setAccessibleDescription('Added to your dictionary: '+', '.join(words))
        self.adjustSize()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.right()-self.width()-20,area.bottom()-self.height()-20)
        self.show()
        self.dismiss.start(8000)

    def clear(self):
        self.dismiss.stop()
        self.words.clear()
        self.hide()
