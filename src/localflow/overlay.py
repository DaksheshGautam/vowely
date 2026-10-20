"""Small, click-through dictation indicator. Never activates a typing target."""
import math
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget


class DictationOverlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowTitle('Vowely dictation indicator')
        self.setAccessibleName('Vowely dictation indicator')
        self.setFixedSize(220, 130)
        self.phase = 'hidden'
        self.label = ''
        self.level = self.target_level = 0.0
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.animate)
        self.dismiss = QTimer(self)
        self.dismiss.setSingleShot(True)
        self.dismiss.timeout.connect(self.clear)

    def show_phase(self, phase, label='', duration=0):
        self.dismiss.stop()
        if self.phase=='hidden':
            screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
            if screen:
                area = screen.availableGeometry()
                self.move(area.center().x()-self.width()//2, area.bottom()-self.height()-35)
        self.phase = phase
        self.label = label or {'listening':'Listening', 'processing':'Finishing…'}.get(phase,'')
        self.setAccessibleDescription(self.label)
        if phase!='listening': self.target_level = 0
        self.show()  # WA_ShowWithoutActivating keeps the original editor focused.
        self.timer.start()
        if duration: self.dismiss.start(duration)
        self.update()

    def set_level(self, value):
        self.target_level = max(0.0,min(1.0,float(value)))

    def animate(self):
        self.level += (self.target_level-self.level)*(.45 if self.target_level>self.level else .16)
        if self.target_level==0 and self.level<.015: self.level = 0.0
        if self.phase=='processing': self.angle = (self.angle+7)%360
        self.update()

    def clear(self):
        self.dismiss.stop()
        self.timer.stop()
        self.phase = 'hidden'
        self.level = self.target_level = 0.0
        self.hide()

    def paintEvent(self,event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(24,22,33,240))
        painter.drawRoundedRect(QRectF(19,3,182,120),28,28)
        color = QColor('#bba4ff') if self.phase in ('listening','processing') else QColor('#72dfb1' if self.phase=='done' else '#ffbc86')
        center_x,center_y = self.width()/2,49
        radius = 19+15*self.level if self.phase=='listening' else 26
        glow = QRadialGradient(center_x,center_y,radius+14)
        glow.setColorAt(0,QColor(color.red(),color.green(),color.blue(),110))
        glow.setColorAt(1,QColor(color.red(),color.green(),color.blue(),0))
        painter.setBrush(glow)
        painter.drawEllipse(QRectF(center_x-radius-14,center_y-radius-14,2*radius+28,2*radius+28))
        if self.phase=='processing':
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(255,255,255,28),5))
            ring = QRectF(center_x-25,center_y-25,50,50)
            painter.drawEllipse(ring)
            pen = QPen(color,5)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            # Indeterminate: the engines do not report a reliable percentage.
            span = 95+55*(1+math.sin(math.radians(self.angle)))/2
            painter.drawArc(ring,int(-self.angle*16),int(span*16))
        else:
            fill = QRadialGradient(center_x-radius*.3,center_y-radius*.4,radius*1.8)
            fill.setColorAt(0,color.lighter(125))
            fill.setColorAt(1,color.darker(135))
            painter.setBrush(fill)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(center_x-radius,center_y-radius,2*radius,2*radius))
        painter.setPen(QColor('#f5f1ff'))
        painter.setFont(QFont('Segoe UI',9))
        painter.drawText(QRectF(23,89,174,23),Qt.AlignCenter,self.label)
