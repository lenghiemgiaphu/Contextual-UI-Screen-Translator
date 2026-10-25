"""Chụp đóng băng màn hình + khoanh vùng. Hỗ trợ nhiều màn hình và màn hình DPI cao."""
import io

from PIL import Image
from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QWidget

from theme import BLUE


def _crop(pixmap, screen_geometry, local_rect):
    """Cắt theo toạ độ logic, quy đổi sang điểm ảnh vật lý khi màn hình có DPI scaling."""
    rx = pixmap.width() / max(screen_geometry.width(), 1)
    ry = pixmap.height() / max(screen_geometry.height(), 1)
    source = QRect(
        round(local_rect.x() * rx),
        round(local_rect.y() * ry),
        round(local_rect.width() * rx),
        round(local_rect.height() * ry),
    )
    return pixmap.copy(source), source


def grab_region(global_rect):
    """Chụp lại một vùng đã biết (dùng cho phím 'dịch lại vùng gần nhất')."""
    screen = QGuiApplication.screenAt(global_rect.center()) or QGuiApplication.primaryScreen()
    geometry = screen.geometry()
    pixmap = screen.grabWindow(0)
    cropped, _ = _crop(pixmap, geometry, global_rect.translated(-geometry.topLeft()))
    return cropped


def pixmap_to_pil(pixmap):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    pixmap.save(buffer, "PNG")
    return Image.open(io.BytesIO(data.data())).convert("RGB")


class SnippingWidget(QWidget):
    captured = pyqtSignal(QPixmap, QRect)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setCursor(Qt.CrossCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pixmap = None
        self._screen = None
        self._begin = None
        self._end = None

    def start(self):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self._screen = screen
        self._pixmap = screen.grabWindow(0)
        self._begin = self._end = None
        self.setGeometry(screen.geometry())
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def _selection(self):
        if self._begin is None or self._end is None:
            return None
        return QRect(self._begin, self._end).normalized()

    def paintEvent(self, _event):
        if self._pixmap is None:
            return
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        selection = self._selection()
        if selection and selection.width() > 0 and selection.height() > 0:
            _, source = _crop(self._pixmap, self._screen.geometry(), selection)
            painter.drawPixmap(selection, self._pixmap, source)
            painter.setPen(QPen(QColor(BLUE), 2))
            painter.drawRect(selection)
            self._draw_pill(painter, f"{source.width()} × {source.height()} px", selection.left(), selection.top() - 28)
        else:
            self._draw_pill(
                painter,
                "Kéo chuột để chọn vùng cần dịch   •   Esc hoặc chuột phải: huỷ",
                max(self.width() // 2 - 230, 10),
                24,
            )

    @staticmethod
    def _draw_pill(painter, text, x, y):
        painter.setFont(QFont("Segoe UI", 10))
        width = painter.fontMetrics().horizontalAdvance(text) + 20
        rect = QRect(x, max(y, 4), width, 24)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(17, 17, 27, 220))
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(QColor("#CDD6F4"))
        painter.drawText(rect, Qt.AlignCenter, text)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.hide()
            return
        if event.button() == Qt.LeftButton:
            self._begin = self._end = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self._begin is not None:
            self._end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self._pixmap is None:
            return
        selection = self._selection()
        # Ẩn ngay để trả lại chuột cho ứng dụng bên dưới.
        self.hide()
        self._begin = self._end = None
        if not selection or selection.width() < 10 or selection.height() < 10:
            return
        cropped, _ = _crop(self._pixmap, self._screen.geometry(), selection)
        global_rect = selection.translated(self._screen.geometry().topLeft())
        self.captured.emit(cropped, global_rect)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
