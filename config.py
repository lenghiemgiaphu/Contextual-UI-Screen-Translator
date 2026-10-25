"""Cấu hình, hằng số và tiện ích đọc/ghi JSON an toàn."""
import json
import os
import shutil
import sys
import threading

APP_NAME = "Screen Translator"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DB_PATH = os.path.join(BASE_DIR, "database.json")
HISTORY_PATH = os.path.join(BASE_DIR, "history.json")
CACHE_PATH = os.path.join(BASE_DIR, "translation_cache.json")
LOG_PATH = os.path.join(BASE_DIR, "screen_translator.log")
CAPTURE_DIR = os.path.join(BASE_DIR, "captures")

# db: khoá ngôn ngữ trong database.json | gt: mã Google Translate
LANG_MAP = {
    "Tiếng Việt": {"db": "vi", "gt": "vi"},
    "Tiếng Anh": {"db": "en", "gt": "en"},
    "Tiếng Trung (Simplified)": {"db": "zh", "gt": "zh-CN"},
    "Tiếng Pháp": {"db": "fr", "gt": "fr"},
    "Tiếng Đức": {"db": "de", "gt": "de"},
    "Tiếng Nhật": {"db": "ja", "gt": "ja"},
    "Tiếng Hàn": {"db": "ko", "gt": "ko"},
}

# Mỗi profile là danh sách gói ngôn ngữ Tesseract. Càng ít ngôn ngữ thì OCR càng chính xác.
OCR_PROFILES = {
    "Tự động": ["eng", "vie", "chi_sim"],
    "Anh": ["eng"],
    "Việt": ["vie", "eng"],
    "Trung": ["chi_sim", "eng"],
    "Pháp": ["fra", "eng"],
    "Đức": ["deu", "eng"],
    "Nhật": ["jpn", "eng"],
    "Hàn": ["kor", "eng"],
    "Tất cả (chậm)": ["eng", "vie", "chi_sim", "fra", "deu"],
}

MODES = [("Từng dòng", "line"), ("Đoạn văn", "paragraph")]

DEFAULTS = {
    "hotkey_snip": "f8",
    "hotkey_repeat": "f9",
    "hotkey_history": "",
    "tesseract_path": "",
    "default_target": "Tiếng Việt",
    "ocr_profile": "Tự động",
    "mode": "line",
    "fuzzy_threshold": 75,
    "ocr_min_conf": 30,
    "ocr_psm": 6,
    "google_fallback": True,
    "show_pinyin": True,
    "pin_popup": False,
    "keep_old_popups": False,
    "auto_copy": False,
    "save_capture": False,
    "popup_opacity": 97,
    "history_limit": 500,
    "autostart": False,
}

_write_lock = threading.Lock()


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def atomic_write_json(path, data):
    """Ghi qua file tạm rồi thay thế để không bao giờ làm hỏng file gốc."""
    tmp = path + ".tmp"
    with _write_lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


def find_tesseract(configured=""):
    """Tự dò đường dẫn tesseract.exe: cấu hình > biến môi trường > PATH > thư mục mặc định."""
    candidates = [configured or "", os.environ.get("TESSERACT_CMD", ""), shutil.which("tesseract") or ""]
    if os.name == "nt":
        candidates += [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ""


class Config:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self._data = dict(DEFAULTS)
        stored = read_json(path, {})
        if isinstance(stored, dict):
            self._data.update({k: v for k, v in stored.items() if k in DEFAULTS})
        if self._data["default_target"] not in LANG_MAP:
            self._data["default_target"] = DEFAULTS["default_target"]
        if self._data["ocr_profile"] not in OCR_PROFILES:
            self._data["ocr_profile"] = DEFAULTS["ocr_profile"]
        if self._data["mode"] not in ("line", "paragraph"):
            self._data["mode"] = "line"
        if not os.path.exists(path):
            self.save()

    def get(self, key):
        return self._data.get(key, DEFAULTS.get(key))

    def update(self, **values):
        self._data.update({k: v for k, v in values.items() if k in DEFAULTS})
        self.save()

    def save(self):
        try:
            atomic_write_json(self.path, self._data)
        except OSError:
            pass
