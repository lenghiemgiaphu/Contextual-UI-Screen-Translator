"""Screen Translator — chụp màn hình, OCR và dịch song song. Chạy: python snipping_tool.py"""
import logging
import os
import sys
import tempfile
import time
from logging.handlers import RotatingFileHandler

from PyQt5.QtCore import QLockFile, QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QAction, QApplication, QDialog, QMenu, QSystemTrayIcon

from config import APP_NAME, BASE_DIR, CAPTURE_DIR, DB_PATH, LOG_PATH, Config
from database import TranslationDB
from dialogs import HistoryDialog, SettingsDialog
from history import HistoryStore
from ocr import OcrEngine
from overlay import POOL, TranslationOverlay
from snipper import SnippingWidget, grab_region, pixmap_to_pil
from theme import BLUE, CRUST
from translator import TranslationEngine

try:
    import keyboard
except ImportError:
    keyboard = None

log = logging.getLogger("screen_translator")


class HotkeySignals(QObject):
    snip = pyqtSignal()
    repeat = pyqtSignal()
    history = pyqtSignal()


class AppContext:
    def __init__(self):
        self.cfg = Config()
        self.db = TranslationDB(DB_PATH, self.cfg.get("fuzzy_threshold"))
        self.translator = TranslationEngine(self.cfg, self.db)
        self.ocr = OcrEngine(self.cfg)
        self.history = HistoryStore(self.cfg)


def setup_logging():
    handler = RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    def excepthook(exc_type, exc, tb):
        log.error("Lỗi chưa xử lý", exc_info=(exc_type, exc, tb))

    sys.excepthook = excepthook


def set_autostart(enabled):
    if sys.platform != "win32":
        return
    import winreg

    if getattr(sys, "frozen", False):
        command = f'"{sys.executable}"'
    else:
        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
        interpreter = pythonw if os.path.exists(pythonw) else sys.executable
        command = f'"{interpreter}" "{os.path.abspath(__file__)}"'
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE
    ) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def build_tray_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(BLUE))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
    painter.setPen(QColor(CRUST))
    painter.setFont(QFont("Segoe UI", 32, QFont.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "T")
    painter.end()
    return QIcon(pixmap)


class AppController(QObject):
    def __init__(self, app, ctx):
        super().__init__()
        self.app = app
        self.ctx = ctx
        self.cfg = ctx.cfg
        self.overlays = []
        self.last_rect = None
        self.history_dialog = None
        self._hotkey_handles = []

        self.snipper = SnippingWidget()
        self.snipper.captured.connect(self.on_captured)

        self.signals = HotkeySignals()
        self.signals.snip.connect(self.start_snip)
        self.signals.repeat.connect(self.repeat_last)
        self.signals.history.connect(self.show_history)

        self.tray = QSystemTrayIcon(build_tray_icon())
        self.tray.activated.connect(self._on_tray_activated)
        self._build_tray_menu()
        self.tray.show()

        self.register_hotkeys()
        if not ctx.ocr.available:
            QTimer.singleShot(800, self._warn_missing_tesseract)

    # ----- tray -----
    def _build_tray_menu(self):
        hk_snip = self.cfg.get("hotkey_snip").upper()
        hk_repeat = self.cfg.get("hotkey_repeat").upper()
        self.tray.setToolTip(f"{APP_NAME} ({hk_snip or 'chưa đặt phím tắt'})")
        menu = QMenu()
        entries = [
            (f"✂ Chụp & dịch ({hk_snip})" if hk_snip else "✂ Chụp & dịch", self.start_snip),
            (f"🔁 Dịch lại vùng gần nhất ({hk_repeat})" if hk_repeat else "🔁 Dịch lại vùng gần nhất", self.repeat_last),
            None,
            ("🕘 Lịch sử dịch", self.show_history),
            ("⚙ Cài đặt", self.show_settings),
            None,
            ("📂 Mở database.json", lambda: self._open_path(DB_PATH)),
            ("🔄 Tải lại database", self.reload_database),
            ("📁 Mở thư mục ứng dụng", lambda: self._open_path(BASE_DIR)),
            None,
            ("✕ Thoát hẳn", self.quit),
        ]
        for entry in entries:
            if entry is None:
                menu.addSeparator()
                continue
            action = QAction(entry[0], menu)
            action.triggered.connect(entry[1])
            menu.addAction(action)
        self._menu = menu
        self.tray.setContextMenu(menu)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.start_snip()

    def notify(self, message, icon=QSystemTrayIcon.Information):
        self.tray.showMessage(APP_NAME, message, icon, 5000)

    def _warn_missing_tesseract(self):
        self.notify(
            "Chưa tìm thấy Tesseract OCR. Mở Cài đặt để chọn đường dẫn tesseract.exe.", QSystemTrayIcon.Warning
        )

    @staticmethod
    def _open_path(path):
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def reload_database(self):
        self.ctx.db.reload(force=True)
        self.notify(f"Đã tải lại database ({len(self.ctx.db)} mục).")

    # ----- phím tắt -----
    def register_hotkeys(self):
        if keyboard is None:
            self.notify("Thiếu thư viện 'keyboard' nên không dùng được phím tắt toàn cục.", QSystemTrayIcon.Warning)
            return
        for handle in self._hotkey_handles:
            try:
                keyboard.remove_hotkey(handle)
            except (KeyError, ValueError):
                pass
        self._hotkey_handles = []
        bindings = (
            ("hotkey_snip", self.signals.snip),
            ("hotkey_repeat", self.signals.repeat),
            ("hotkey_history", self.signals.history),
        )
        for name, signal in bindings:
            combo = (self.cfg.get(name) or "").strip()
            if not combo:
                continue
            try:
                self._hotkey_handles.append(keyboard.add_hotkey(combo, signal.emit))
            except Exception as exc:
                log.warning("Phím tắt '%s' không hợp lệ: %s", combo, exc)
                self.notify(f"Phím tắt '{combo}' không hợp lệ hoặc cần quyền Administrator.", QSystemTrayIcon.Warning)

    # ----- chụp & dịch -----
    def start_snip(self):
        if not self.snipper.isVisible():
            self.snipper.start()

    def on_captured(self, pixmap, rect):
        self.last_rect = rect
        self.open_overlay(pixmap, rect)

    def repeat_last(self):
        if self.last_rect is None:
            self.notify("Chưa có vùng nào để dịch lại. Hãy khoanh vùng trước.")
            return
        for overlay in [o for o in self.overlays if not o.pinned]:
            overlay.close()
        # Đợi popup biến mất khỏi màn hình trước khi chụp lại.
        QTimer.singleShot(160, self._repeat_capture)

    def _repeat_capture(self):
        self.open_overlay(grab_region(self.last_rect), self.last_rect)

    def open_overlay(self, pixmap, rect):
        if not self.cfg.get("keep_old_popups"):
            for overlay in [o for o in self.overlays if not o.pinned]:
                overlay.close()
        if self.cfg.get("save_capture"):
            os.makedirs(CAPTURE_DIR, exist_ok=True)
            pixmap.save(os.path.join(CAPTURE_DIR, time.strftime("capture_%Y%m%d_%H%M%S.png")), "PNG")
        overlay = TranslationOverlay(self.ctx, pixmap_to_pil(pixmap), rect)
        overlay.closed.connect(self._overlay_closed)
        self.overlays.append(overlay)
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()

    def _overlay_closed(self, overlay):
        if overlay in self.overlays:
            self.overlays.remove(overlay)

    # ----- hộp thoại -----
    def show_history(self):
        if self.history_dialog is not None and self.history_dialog.isVisible():
            self.history_dialog.reload()
            self.history_dialog.raise_()
            self.history_dialog.activateWindow()
            return
        self.history_dialog = HistoryDialog(self.ctx.history)
        self.history_dialog.show()

    def show_settings(self):
        dialog = SettingsDialog(self.cfg, self.ctx.ocr)
        if dialog.exec_() != QDialog.Accepted:
            return
        values = dialog.values()
        self.cfg.update(**values)
        self.ctx.ocr.apply_path()
        self.ctx.db.threshold = self.cfg.get("fuzzy_threshold")
        try:
            set_autostart(bool(values["autostart"]))
        except OSError as exc:
            log.warning("Không đặt được autostart: %s", exc)
        self._build_tray_menu()
        self.register_hotkeys()
        self.notify("Đã lưu cài đặt.")

    def quit(self):
        if keyboard is not None:
            for handle in self._hotkey_handles:
                try:
                    keyboard.remove_hotkey(handle)
                except (KeyError, ValueError):
                    pass
        self.ctx.translator.flush()
        POOL.waitForDone(1500)
        self.tray.hide()
        self.app.quit()


def main():
    setup_logging()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    lock = QLockFile(os.path.join(tempfile.gettempdir(), "screen_translator.lock"))
    if not lock.tryLock(100):
        print("-> Screen Translator đang chạy rồi (xem khay hệ thống).")
        return 0

    controller = AppController(app, AppContext())
    hk = controller.cfg.get("hotkey_snip").upper()
    print("-> Ứng dụng đã chạy ngầm!")
    print(f"-> Bấm phím [{hk}] để khoanh vùng dịch, chuột phải vào biểu tượng khay để mở menu.")
    code = app.exec_()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
