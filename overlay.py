"""Popup kết quả: OCR và dịch chạy nền, hiển thị từng dòng song song."""
import time
import uuid

from PyQt5.QtCore import QObject, QPoint, QRect, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QGuiApplication, QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from config import LANG_MAP, MODES, OCR_PROFILES
from textutils import join_lines
from theme import BLUE, CRUST, GREEN, OVERLAY, OVERLAY_STYLE, RED, SKY, SUBTEXT, YELLOW
from translator import Result

POOL = QThreadPool()
POOL.setMaxThreadCount(4)

BADGE_COLORS = {"DB": GREEN, "Cache": SKY, "Google": YELLOW, "Lỗi": RED, "Không": RED}


class _Signals(QObject):
    ocr_done = pyqtSignal(int, int, object)
    ocr_failed = pyqtSignal(int, int, str)
    tr_done = pyqtSignal(int, int, object)
    tr_failed = pyqtSignal(int, int, str)


class _Task(QRunnable):
    def __init__(self, fn, done, failed, gen, idx, is_current):
        super().__init__()
        self.fn, self.done, self.failed = fn, done, failed
        self.gen, self.idx, self.is_current = gen, idx, is_current

    def run(self):
        if not self.is_current(self.gen):
            return
        try:
            result = self.fn()
        except Exception as exc:
            self.failed.emit(self.gen, self.idx, str(exc))
            return
        self.done.emit(self.gen, self.idx, result)


class LineRow(QFrame):
    edit_requested = pyqtSignal(object)

    def __init__(self, raw):
        super().__init__()
        self.setObjectName("Row")
        self.raw = raw
        self.translated = ""
        self.source = ""
        self.pinyin = ""

        self.raw_label = QLabel(raw)
        self.raw_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.raw_label.setStyleSheet(f"color: {BLUE};")
        self.raw_label.setWordWrap(True)

        self.pinyin_label = QLabel()
        self.pinyin_label.setFont(QFont("Segoe UI", 8))
        self.pinyin_label.setStyleSheet(f"color: {OVERLAY}; font-style: italic;")
        self.pinyin_label.setWordWrap(True)
        self.pinyin_label.hide()

        self.trans_label = QLabel()
        self.trans_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.trans_label.setWordWrap(True)

        self.badge = QLabel()
        self.badge.setFont(QFont("Segoe UI", 7))
        self.badge.hide()

        left = QVBoxLayout()
        left.setSpacing(1)
        left.addWidget(self.raw_label)
        left.addWidget(self.pinyin_label)
        left.addStretch()

        right = QVBoxLayout()
        right.setSpacing(2)
        right.addWidget(self.trans_label)
        right.addWidget(self.badge, 0, Qt.AlignLeft)
        right.addStretch()

        arrow = QLabel("➔")
        arrow.setStyleSheet(f"color: {OVERLAY};")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        layout.addLayout(left, 4)
        layout.addWidget(self._tool("📋", "Copy từ gốc", lambda: self._copy(self.raw)), 0, Qt.AlignTop)
        layout.addWidget(arrow, 0, Qt.AlignTop)
        layout.addLayout(right, 5)
        layout.addWidget(self._tool("📋", "Copy bản dịch", lambda: self._copy(self.translated)), 0, Qt.AlignTop)
        layout.addWidget(
            self._tool("✏", "Sửa bản dịch và lưu vào database.json", lambda: self.edit_requested.emit(self)),
            0,
            Qt.AlignTop,
        )
        self.set_loading()

    @staticmethod
    def _tool(text, tooltip, slot):
        button = QPushButton(text)
        button.setFixedSize(24, 24)
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(slot)
        return button

    @staticmethod
    def _copy(text):
        QApplication.clipboard().setText(text)

    def set_loading(self):
        self.trans_label.setText("⏳ Đang dịch…")
        self.trans_label.setStyleSheet(f"color: {SUBTEXT};")
        self.badge.hide()

    def set_result(self, result):
        self.translated = result.text
        self.source = result.source
        self.pinyin = result.pinyin
        self.trans_label.setText(result.text)
        self.trans_label.setStyleSheet(f"color: {'#A6E3A1' if result.ok else RED};")
        self.pinyin_label.setText(result.pinyin)
        self.pinyin_label.setVisible(bool(result.pinyin))
        color = BADGE_COLORS.get(result.source.split(" ")[0], OVERLAY)
        self.badge.setText(result.source)
        self.badge.setStyleSheet(
            f"color: {CRUST}; background: {color}; border-radius: 3px; padding: 0 5px;"
        )
        self.badge.setVisible(bool(result.source) and result.source != "N/A")


class TranslationOverlay(QWidget):
    closed = pyqtSignal(object)

    def __init__(self, ctx, image, anchor_rect):
        super().__init__()
        self.ctx = ctx
        self.cfg = ctx.cfg
        self.image = image
        self.anchor = anchor_rect
        self.pinned = bool(self.cfg.get("pin_popup"))
        self._gen = 0
        self._rows = []
        self._lines = []
        self._missing = []
        self._summary = ""
        self._history_id = uuid.uuid4().hex
        self._autosized = False
        self._drag_origin = None

        self.signals = _Signals()
        self.signals.ocr_done.connect(self._on_ocr_done)
        self.signals.ocr_failed.connect(self._on_ocr_failed)
        self.signals.tr_done.connect(self._on_tr_done)
        self.signals.tr_failed.connect(self._on_tr_failed)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(max(0.5, min(1.0, int(self.cfg.get("popup_opacity")) / 100)))
        self.setMinimumSize(360, 150)
        self.setStyleSheet(OVERLAY_STYLE)

        self._build_ui()
        QShortcut(QKeySequence.Copy, self, activated=self.copy_translations)
        self.setGeometry(self._compute_geometry(560, 220))
        self.run_ocr()

    # ----- giao diện -----
    def _build_ui(self):
        self.container = QFrame(self)
        self.container.setObjectName("MainContainer")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.container)

        main = QVBoxLayout(self.container)
        main.setContentsMargins(10, 8, 10, 6)
        main.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        self.ocr_combo = QComboBox()
        self.ocr_combo.addItems(list(OCR_PROFILES.keys()))
        self.ocr_combo.setCurrentText(self.cfg.get("ocr_profile"))
        self.ocr_combo.setToolTip("Ngôn ngữ chữ trong ảnh (OCR). Chọn đúng ngôn ngữ sẽ chính xác hơn 'Tự động'.")

        self.lang_combo = QComboBox()
        self.lang_combo.addItems(list(LANG_MAP.keys()))
        self.lang_combo.setCurrentText(self.cfg.get("default_target"))
        self.lang_combo.setToolTip("Ngôn ngữ đích")

        self.mode_combo = QComboBox()
        for label, value in MODES:
            self.mode_combo.addItem(label, value)
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(self.cfg.get("mode"))))
        self.mode_combo.setToolTip("Từng dòng: menu/nút bấm. Đoạn văn: gộp các dòng để dịch đúng ngữ cảnh.")

        self.pin_btn = QPushButton("📌")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(self.pinned)
        self.pin_btn.setFixedSize(24, 24)
        self.pin_btn.setToolTip("Ghim: giữ popup khi chụp vùng mới")
        self.pin_btn.toggled.connect(lambda checked: setattr(self, "pinned", checked))

        close_btn = QPushButton("✕")
        close_btn.setObjectName("CloseBtn")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.close)

        header.addWidget(QLabel("OCR:"))
        header.addWidget(self.ocr_combo)
        header.addWidget(QLabel("➔"))
        header.addWidget(self.lang_combo)
        header.addWidget(self.mode_combo)
        header.addStretch()
        header.addWidget(self.pin_btn)
        header.addWidget(close_btn)
        main.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.lines_layout = QVBoxLayout(self.scroll_content)
        self.lines_layout.setContentsMargins(0, 0, 4, 0)
        self.lines_layout.setSpacing(6)
        self.scroll.setWidget(self.scroll_content)
        main.addWidget(self.scroll, 1)

        footer = QHBoxLayout()
        footer.setSpacing(6)
        self.status = QLabel()
        self.status.setObjectName("Status")
        copy_raw = QPushButton("📋 Gốc")
        copy_trans = QPushButton("📋 Dịch")
        redo = QPushButton("🔄")
        copy_raw.clicked.connect(self.copy_originals)
        copy_trans.clicked.connect(self.copy_translations)
        redo.setToolTip("Nhận diện lại ảnh đã chụp")
        redo.clicked.connect(self.run_ocr)
        footer.addWidget(self.status, 1)
        footer.addWidget(copy_raw)
        footer.addWidget(copy_trans)
        footer.addWidget(redo)
        footer.addSpacing(14)
        main.addLayout(footer)

        self.sizegrip = QSizeGrip(self)
        self.sizegrip.setStyleSheet("background: transparent;")

        self.ocr_combo.currentIndexChanged.connect(self._on_ocr_profile_changed)
        self.lang_combo.currentIndexChanged.connect(self._on_target_or_mode_changed)
        self.mode_combo.currentIndexChanged.connect(self._on_target_or_mode_changed)

    def _compute_geometry(self, width, height):
        screen = QGuiApplication.screenAt(self.anchor.center()) or QGuiApplication.primaryScreen()
        avail = screen.availableGeometry()
        width = min(width, avail.width() - 20)
        height = min(height, avail.height() - 20)
        x = self.anchor.right() + 10
        y = self.anchor.top()
        if x + width > avail.right():
            x = self.anchor.left() - width - 10
        if x < avail.left():
            x = max(avail.left() + 10, min(self.anchor.left(), avail.right() - width - 10))
            below = self.anchor.bottom() + 10
            y = below if below + height <= avail.bottom() else max(avail.top() + 10, self.anchor.top() - height - 10)
        y = max(avail.top() + 10, min(y, avail.bottom() - height - 10))
        return QRect(x, y, width, height)

    def _autosize(self, row_count):
        if self._autosized:
            return
        self._autosized = True
        screen = QGuiApplication.screenAt(self.anchor.center()) or QGuiApplication.primaryScreen()
        height = min(max(row_count * 62 + 120, 170), int(screen.availableGeometry().height() * 0.8))
        self.setGeometry(self._compute_geometry(self.width(), height))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sizegrip.move(self.width() - 20, self.height() - 20)

    # ----- kéo thả cửa sổ -----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_origin = event.globalPos()

    def mouseMoveEvent(self, event):
        if self._drag_origin is not None:
            delta = QPoint(event.globalPos() - self._drag_origin)
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._drag_origin = event.globalPos()

    def mouseReleaseEvent(self, _event):
        self._drag_origin = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def closeEvent(self, event):
        self._gen += 1
        self.closed.emit(self)
        super().closeEvent(event)

    # ----- OCR và dịch -----
    def _dispatch(self, fn, done, failed, idx):
        gen = self._gen
        POOL.start(_Task(fn, done, failed, gen, idx, lambda g: g == self._gen))

    def _clear_rows(self):
        self._rows = []
        while self.lines_layout.count():
            item = self.lines_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_message(self, text, color=SUBTEXT):
        self._clear_rows()
        label = QLabel(text)
        label.setObjectName("Empty")
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {color};")
        self.lines_layout.addWidget(label)
        self.lines_layout.addStretch()

    def _set_summary(self, text):
        self._summary = text
        self.status.setText(text)

    def run_ocr(self):
        self._gen += 1
        self._show_message("⏳ Đang nhận diện chữ…")
        self._set_summary("Đang nhận diện…")
        profile = self.ocr_combo.currentText()
        self._dispatch(lambda: self.ctx.ocr.recognize(self.image, profile), self.signals.ocr_done, self.signals.ocr_failed, 0)

    def _on_ocr_profile_changed(self):
        self.cfg.update(ocr_profile=self.ocr_combo.currentText())
        self.run_ocr()

    def _on_target_or_mode_changed(self):
        self.cfg.update(default_target=self.lang_combo.currentText(), mode=self.mode_combo.currentData())
        if self._lines:
            self.start_translation()

    def _on_ocr_done(self, gen, _idx, result):
        if gen != self._gen:
            return
        self._lines = result.lines
        self._missing = result.missing
        if not self._lines:
            hint = f"\nThiếu gói ngôn ngữ Tesseract: {', '.join(result.missing)}." if result.missing else ""
            self._show_message(
                "Không nhận diện được chữ. Hãy thử chọn đúng ngôn ngữ OCR hoặc khoanh vùng lớn hơn." + hint
            )
            self._set_summary("Không có chữ")
            return
        self._autosize(len(self._lines))
        self.start_translation()

    def _on_ocr_failed(self, gen, _idx, message):
        if gen != self._gen:
            return
        self._lines = []
        self._show_message(message, RED)
        self._set_summary("Lỗi OCR")

    def start_translation(self):
        self._gen += 1
        self._clear_rows()
        target = self.lang_combo.currentText()
        mode = self.mode_combo.currentData()
        units = [join_lines(self._lines)] if mode == "paragraph" else list(self._lines)
        self._pending = len(units)
        self._set_summary(f"Đang dịch {len(units)} mục…")
        for index, unit in enumerate(units):
            row = LineRow(unit)
            row.edit_requested.connect(self._edit_row)
            self.lines_layout.addWidget(row)
            self._rows.append(row)
            self._dispatch(
                lambda text=unit: self.ctx.translator.translate(text, target),
                self.signals.tr_done,
                self.signals.tr_failed,
                index,
            )
        self.lines_layout.addStretch()

    def _on_tr_done(self, gen, idx, result):
        if gen != self._gen or idx >= len(self._rows):
            return
        self._rows[idx].set_result(result)
        self._row_finished()

    def _on_tr_failed(self, gen, idx, _message):
        if gen != self._gen or idx >= len(self._rows):
            return
        row = self._rows[idx]
        row.set_result(Result(row.raw, "Lỗi dịch", ok=False))
        self._row_finished()

    def _row_finished(self):
        self._pending -= 1
        if self._pending > 0:
            return
        counts = {}
        for row in self._rows:
            counts[row.source.split(" ")[0]] = counts.get(row.source.split(" ")[0], 0) + 1
        parts = [f"{len(self._rows)} mục"] + [f"{name} {n}" for name, n in counts.items()]
        if self._missing:
            parts.append(f"thiếu OCR: {', '.join(self._missing)}")
        self._set_summary(" • ".join(parts))
        self._save_history()
        if self.cfg.get("auto_copy"):
            self.copy_translations()

    def _save_history(self):
        self.ctx.history.upsert(
            {
                "id": self._history_id,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "target": self.lang_combo.currentText(),
                "mode": self.mode_combo.currentData(),
                "lines": [{"raw": r.raw, "trans": r.translated, "source": r.source} for r in self._rows],
            }
        )

    # ----- thao tác -----
    def _flash(self, message):
        self.status.setText(message)
        QTimer.singleShot(1600, lambda: self.status.setText(self._summary))

    def copy_originals(self):
        QApplication.clipboard().setText("\n".join(r.raw for r in self._rows))
        self._flash("✔ Đã sao chép văn bản gốc")

    def copy_translations(self):
        QApplication.clipboard().setText("\n".join(r.translated for r in self._rows))
        self._flash("✔ Đã sao chép bản dịch")

    def _edit_row(self, row):
        target_name = self.lang_combo.currentText()
        text, ok = QInputDialog.getText(
            self, "Sửa bản dịch", f"{row.raw}\n➔ {target_name} (sẽ lưu vào database.json):", text=row.translated
        )
        text = text.strip()
        if not ok or not text:
            return
        self.ctx.db.add_or_update(row.raw, LANG_MAP[target_name]["db"], text)
        row.set_result(Result(text, "DB (đã lưu)", 100, row.pinyin))
        self._save_history()
        self._flash("💾 Đã lưu vào database.json")
