"""Hộp thoại Cài đặt và Lịch sử."""
import csv
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from config import LANG_MAP, MODES, OCR_PROFILES
from theme import DIALOG_STYLE


class SettingsDialog(QDialog):
    def __init__(self, cfg, ocr, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.ocr = ocr
        self.setWindowTitle("Screen Translator — Cài đặt")
        self.setStyleSheet(DIALOG_STYLE)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)

        # Phím tắt
        hotkeys = QGroupBox("Phím tắt toàn cục")
        form = QFormLayout(hotkeys)
        self.hk_snip = QLineEdit(cfg.get("hotkey_snip"))
        self.hk_repeat = QLineEdit(cfg.get("hotkey_repeat"))
        self.hk_history = QLineEdit(cfg.get("hotkey_history"))
        for edit in (self.hk_snip, self.hk_repeat, self.hk_history):
            edit.setPlaceholderText("ví dụ: f8, ctrl+shift+t (để trống = tắt)")
        form.addRow("Khoanh vùng & dịch", self.hk_snip)
        form.addRow("Dịch lại vùng gần nhất", self.hk_repeat)
        form.addRow("Mở lịch sử", self.hk_history)
        layout.addWidget(hotkeys)

        # Dịch thuật
        translate = QGroupBox("Dịch thuật")
        form = QFormLayout(translate)
        self.target = QComboBox()
        self.target.addItems(list(LANG_MAP.keys()))
        self.target.setCurrentText(cfg.get("default_target"))
        self.profile = QComboBox()
        self.profile.addItems(list(OCR_PROFILES.keys()))
        self.profile.setCurrentText(cfg.get("ocr_profile"))
        self.mode = QComboBox()
        for label, value in MODES:
            self.mode.addItem(label, value)
        self.mode.setCurrentIndex(max(0, self.mode.findData(cfg.get("mode"))))
        self.threshold = QSpinBox()
        self.threshold.setRange(50, 100)
        self.threshold.setSuffix(" %")
        self.threshold.setValue(int(cfg.get("fuzzy_threshold")))
        self.min_conf = QSpinBox()
        self.min_conf.setRange(0, 90)
        self.min_conf.setValue(int(cfg.get("ocr_min_conf")))
        form.addRow("Ngôn ngữ đích mặc định", self.target)
        form.addRow("Ngôn ngữ OCR mặc định", self.profile)
        form.addRow("Chế độ dịch", self.mode)
        form.addRow("Ngưỡng khớp database", self.threshold)
        form.addRow("Độ tin cậy OCR tối thiểu", self.min_conf)
        self.google = QCheckBox("Dùng Google Translate khi database không có")
        self.google.setChecked(bool(cfg.get("google_fallback")))
        self.pinyin = QCheckBox("Hiện pinyin dưới chữ Hán")
        self.pinyin.setChecked(bool(cfg.get("show_pinyin")))
        form.addRow(self.google)
        form.addRow(self.pinyin)
        layout.addWidget(translate)

        # Tesseract
        ocr_box = QGroupBox("Tesseract OCR")
        ocr_layout = QVBoxLayout(ocr_box)
        row = QHBoxLayout()
        self.tess_path = QLineEdit(cfg.get("tesseract_path"))
        self.tess_path.setPlaceholderText("Để trống để tự dò (PATH / Program Files)")
        browse = QPushButton("Chọn…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.tess_path, 1)
        row.addWidget(browse)
        ocr_layout.addLayout(row)
        self.tess_info = QLabel()
        self.tess_info.setObjectName("Hint")
        self.tess_info.setWordWrap(True)
        ocr_layout.addWidget(self.tess_info)
        self._refresh_tess_info()
        self.tess_path.editingFinished.connect(self._refresh_tess_info)
        layout.addWidget(ocr_box)

        # Giao diện & hành vi
        behavior = QGroupBox("Popup & hành vi")
        form = QFormLayout(behavior)
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(50, 100)
        self.opacity.setValue(int(cfg.get("popup_opacity")))
        self.opacity_label = QLabel(f"{self.opacity.value()}%")
        self.opacity.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.opacity, 1)
        opacity_row.addWidget(self.opacity_label)
        form.addRow("Độ mờ popup", opacity_row)
        self.pin = QCheckBox("Ghim popup mặc định")
        self.pin.setChecked(bool(cfg.get("pin_popup")))
        self.keep_old = QCheckBox("Giữ các popup cũ khi chụp vùng mới")
        self.keep_old.setChecked(bool(cfg.get("keep_old_popups")))
        self.auto_copy = QCheckBox("Tự sao chép bản dịch vào clipboard")
        self.auto_copy.setChecked(bool(cfg.get("auto_copy")))
        self.save_capture = QCheckBox("Lưu ảnh đã chụp vào thư mục captures/")
        self.save_capture.setChecked(bool(cfg.get("save_capture")))
        self.autostart = QCheckBox("Khởi động cùng Windows")
        self.autostart.setChecked(bool(cfg.get("autostart")))
        self.autostart.setEnabled(sys.platform == "win32")
        for box in (self.pin, self.keep_old, self.auto_copy, self.save_capture, self.autostart):
            form.addRow(box)
        layout.addWidget(behavior)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Huỷ")
        save = QPushButton("Lưu")
        save.setObjectName("Primary")
        save.setDefault(True)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn tesseract.exe", "", "Tesseract (tesseract*);;Tất cả (*)")
        if path:
            self.tess_path.setText(path)
            self._refresh_tess_info()

    def _refresh_tess_info(self):
        original = self.cfg.get("tesseract_path")
        self.cfg._data["tesseract_path"] = self.tess_path.text().strip()
        try:
            self.ocr.apply_path()
            if not self.ocr.available:
                self.tess_info.setText("⚠ Chưa tìm thấy Tesseract. Cài từ github.com/UB-Mannheim/tesseract/wiki")
                return
            langs = sorted(self.ocr.installed_languages() - {"osd"})
            self.tess_info.setText(f"✔ {self.ocr.path}\nGói ngôn ngữ đã cài: {', '.join(langs) or 'không rõ'}")
        finally:
            self.cfg._data["tesseract_path"] = original

    def values(self):
        return {
            "hotkey_snip": self.hk_snip.text().strip().lower(),
            "hotkey_repeat": self.hk_repeat.text().strip().lower(),
            "hotkey_history": self.hk_history.text().strip().lower(),
            "default_target": self.target.currentText(),
            "ocr_profile": self.profile.currentText(),
            "mode": self.mode.currentData(),
            "fuzzy_threshold": self.threshold.value(),
            "ocr_min_conf": self.min_conf.value(),
            "google_fallback": self.google.isChecked(),
            "show_pinyin": self.pinyin.isChecked(),
            "tesseract_path": self.tess_path.text().strip(),
            "popup_opacity": self.opacity.value(),
            "pin_popup": self.pin.isChecked(),
            "keep_old_popups": self.keep_old.isChecked(),
            "auto_copy": self.auto_copy.isChecked(),
            "save_capture": self.save_capture.isChecked(),
            "autostart": self.autostart.isChecked(),
        }


class HistoryDialog(QDialog):
    COLUMNS = ["Thời gian", "Văn bản gốc", "Bản dịch", "Nguồn", "Ngôn ngữ đích"]

    def __init__(self, history, parent=None):
        super().__init__(parent)
        self.history = history
        self._entries = []
        self.setWindowTitle("Screen Translator — Lịch sử")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(900, 560)

        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm trong lịch sử (gốc hoặc bản dịch)…")
        self.search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(lambda *_: self._copy_selected())
        layout.addWidget(self.table, 1)

        self.count_label = QLabel()
        self.count_label.setObjectName("Hint")
        buttons = QHBoxLayout()
        copy_btn = QPushButton("Sao chép bản dịch")
        delete_btn = QPushButton("Xoá mục đã chọn")
        clear_btn = QPushButton("Xoá tất cả")
        clear_btn.setObjectName("Danger")
        export_btn = QPushButton("Xuất CSV…")
        close_btn = QPushButton("Đóng")
        copy_btn.clicked.connect(self._copy_selected)
        delete_btn.clicked.connect(self._delete_selected)
        clear_btn.clicked.connect(self._clear_all)
        export_btn.clicked.connect(self._export)
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(self.count_label, 1)
        for button in (copy_btn, delete_btn, export_btn, clear_btn, close_btn):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.reload()

    def reload(self):
        self._entries = self.history.items()
        self.table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            lines = entry.get("lines", [])
            raw = "\n".join(line.get("raw", "") for line in lines)
            trans = "\n".join(line.get("trans", "") for line in lines)
            sources = sorted({line.get("source", "").split(" ")[0] for line in lines if line.get("source")})
            cells = [entry.get("time", ""), raw, trans, ", ".join(sources), entry.get("target", "")]
            for col, text in enumerate(cells):
                self.table.setItem(row, col, QTableWidgetItem(text))
            self.table.item(row, 0).setData(Qt.UserRole, f"{raw}\n{trans}".lower())
        self.table.resizeRowsToContents()
        self._apply_filter()

    def _apply_filter(self):
        needle = self.search.text().strip().lower()
        visible = 0
        for row in range(self.table.rowCount()):
            haystack = self.table.item(row, 0).data(Qt.UserRole) or ""
            hidden = bool(needle) and needle not in haystack
            self.table.setRowHidden(row, hidden)
            visible += 0 if hidden else 1
        self.count_label.setText(f"{visible}/{len(self._entries)} mục")

    def _selected_rows(self):
        return sorted({index.row() for index in self.table.selectedIndexes()})

    def _copy_selected(self):
        rows = self._selected_rows()
        if rows:
            QApplication.clipboard().setText("\n".join(self.table.item(r, 2).text() for r in rows))

    def _delete_selected(self):
        rows = self._selected_rows()
        if rows:
            self.history.delete(self._entries[r]["id"] for r in rows)
            self.reload()

    def _clear_all(self):
        if not self._entries:
            return
        answer = QMessageBox.question(self, "Xoá lịch sử", "Xoá toàn bộ lịch sử dịch?")
        if answer == QMessageBox.Yes:
            self.history.clear()
            self.reload()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Xuất lịch sử", "lich_su_dich.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Thời gian", "Ngôn ngữ đích", "Văn bản gốc", "Bản dịch", "Nguồn"])
            for entry in reversed(self._entries):
                for line in entry.get("lines", []):
                    writer.writerow(
                        [entry.get("time", ""), entry.get("target", ""), line.get("raw", ""), line.get("trans", ""), line.get("source", "")]
                    )
