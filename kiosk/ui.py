"""Camera-first kiosk surface, drawn locally without web or image dependencies."""
import math
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

COLORS = {'idle':'#73c9ac','checking':'#89c7e8','success':'#7de1ac','unknown':'#f1bc78',
          'multiple':'#f1bc78','error':'#ee9e97'}

STYLESHEET = '''
QMainWindow, QDialog { background: #101e1a; }
QWidget { color: #eef6f1; font-family: 'Avenir Next', 'Segoe UI', sans-serif; font-size: 13px; }
QLabel { background: transparent; }
QLabel#Brand { font-size: 16px; font-weight: 600; }
QLabel#BrandIcon { color: #9cdec3; background: #213f32; border: 1px solid #355c47; border-radius: 11px; font-size: 24px; }
QLabel#Eyebrow { color: #7e9e8e; font-size: 10px; letter-spacing: 2px; }
QLabel#Clock { font-size: 19px; font-weight: 500; }
QLabel#Date { color: #7f9a8c; font-size: 11px; }
QLabel#Welcome { font-size: 26px; font-weight: 600; }
QLabel#Subtitle { color: #8da798; font-size: 12px; }
QWidget#StatusCard { background: #1a3026; border: 1px solid #2c493a; border-radius: 16px; }
QLabel#StatusSymbol { border-radius: 23px; background: #294d3b; color: #94d8b8; font-size: 24px; }
QLabel#StatusTitle { font-size: 21px; font-weight: 600; }
QLabel#StatusDetail { font-size: 12px; color: #9eb6a8; }
QLabel#StepTag { background: #233c2f; color: #8caa99; border: 1px solid #345040; border-radius: 6px; font-size: 10px; padding: 7px 10px; }
QLabel#Connection { font-size: 10px; color: #829d8d; }
QLabel#Privacy { font-size: 10px; color: #638171; }
QPushButton { background: #233d30; color: #b7d1c1; padding: 10px 15px; border: 1px solid #385442; border-radius: 8px; font-size: 12px; }
QPushButton:hover { background: #2e503c; }
QPushButton:focus { border: 1px solid #8ac8a3; }
QPushButton#Settings { font-size: 19px; padding: 5px; background: transparent; border: 0; color: #7e9c8b; }
QPushButton#Primary { background: #83c9a4; color: #14281d; border: 0; font-weight: 600; }
QLineEdit { background: #162b20; border: 1px solid #375340; border-radius: 7px; padding: 10px; selection-background-color: #40745a; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 18px; height: 18px; }
QInputDialog QLabel, QMessageBox QLabel { color: #dfede3; }
'''


class CameraView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage()
        self.mode = 'idle'
        self.phase = 0
        self.setMinimumSize(500, 285)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(45)

    def animate(self):
        self.phase += .035
        if self.mode in ('idle', 'checking'):
            self.update()

    def setFrame(self, image):
        self.image = image
        self.update()

    def setMode(self, mode):
        self.mode = mode
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        clip = QPainterPath(); clip.addRoundedRect(rect, 18, 18)
        p.setClipPath(clip)
        p.fillRect(rect, QColor('#08120f'))
        if not self.image.isNull():
            size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF((self.width()-size.width())/2, (self.height()-size.height())/2, size.width(), size.height())
            p.drawImage(target, self.image)
        else:
            gradient = QLinearGradient(0, 0, self.width(), self.height())
            gradient.setColorAt(0, QColor('#18352a')); gradient.setColorAt(1, QColor('#0b1913'))
            p.fillRect(rect, gradient)
            p.setPen(QPen(QColor('#254134'), 1))
            for x in range(0, self.width(), 40):
                p.drawLine(x, 0, x, self.height())
            for y in range(0, self.height(), 40):
                p.drawLine(0, y, self.width(), y)
        shade = QLinearGradient(0, 0, 0, self.height())
        shade.setColorAt(0, QColor(3, 13, 8, 170)); shade.setColorAt(.3, QColor(0,0,0,0))
        shade.setColorAt(.7, QColor(0,0,0,0)); shade.setColorAt(1, QColor(3,13,8,190))
        p.fillRect(rect, shade)
        color = QColor(COLORS.get(self.mode, COLORS['idle']))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(7, 22, 15, 175))
        p.drawRoundedRect(QRectF(18, 16, 128, 28), 7, 7)
        p.setBrush(color); p.drawEllipse(QRectF(29, 27, 5, 5))
        p.setPen(QColor('#d1e9dc')); p.setFont(QFont('Arial', 9))
        p.drawText(QRectF(42, 17, 102, 27), Qt.AlignmentFlag.AlignVCenter, 'LIVE CAMERA' if not self.image.isNull() else 'CAMERA PREVIEW')
        p.setPen(QColor('#a3b9ad')); p.setFont(QFont('Arial', 8))
        p.drawText(QRectF(160, 17, self.width()-182, 27), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, 'LOCAL FACE RECOGNITION')
        width, height = min(210, self.width()*.29), min(238, self.height()*.63)
        focus = QRectF((self.width()-width)/2, (self.height()-height)/2+5, width, height)
        p.setPen(QPen(color, 2.5)); p.setBrush(Qt.BrushStyle.NoBrush)
        # Soft corner brackets make room for the live camera image.
        for x, y, dx, dy in [(focus.left(),focus.top(),1,1), (focus.right(),focus.top(),-1,1),
                             (focus.left(),focus.bottom(),1,-1), (focus.right(),focus.bottom(),-1,-1)]:
            p.drawLine(int(x),int(y+dy*23),int(x),int(y)); p.drawLine(int(x),int(y),int(x+dx*23),int(y))
        if self.mode in ('idle','checking'):
            y = focus.top() + (math.sin(self.phase)+1)/2 * height
            line = QColor(color); line.setAlpha(90)
            p.setPen(QPen(line, 1)); p.drawLine(int(focus.left()+8),int(y),int(focus.right()-8),int(y))
        if self.image.isNull():
            p.setPen(QColor('#89aa97')); p.setFont(QFont('Arial', 11))
            p.drawText(focus, Qt.AlignmentFlag.AlignCenter, 'Your face goes here')
        caption = {'success':'YOU’RE ALL SET', 'unknown':'LET’S TRY AGAIN', 'multiple':'PLEASE GIVE EACH OTHER SPACE',
                   'error':'ASK AN ADMINISTRATOR'}.get(self.mode, 'LOOK AT THE CAMERA · KEEP YOUR FACE VISIBLE')
        p.setPen(QColor('#bdd5c7')); p.setFont(QFont('Arial', 8))
        p.drawText(QRectF(10,self.height()-35,self.width()-20,20),Qt.AlignmentFlag.AlignCenter,caption)
        p.setClipping(False); p.setPen(QPen(QColor('#34513f'),1)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect,18,18)
