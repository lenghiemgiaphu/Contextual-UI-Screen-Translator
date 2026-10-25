"""Database dịch cục bộ: chỉ mục chuẩn hoá, fuzzy matching, tự nạp lại khi file đổi, học từ người dùng."""
import os
import re
import shutil
import threading
from typing import NamedTuple, Optional

from config import atomic_write_json, read_json
from textutils import guess_lang, normalize, to_pinyin

try:
    from thefuzz import fuzz
except ImportError:
    try:
        from rapidfuzz import fuzz
    except ImportError:
        import difflib

        class fuzz:  # type: ignore
            @staticmethod
            def ratio(a, b):
                return round(100 * difflib.SequenceMatcher(None, a, b).ratio())


class Match(NamedTuple):
    text: str
    score: int
    key: str


class TranslationDB:
    def __init__(self, path, threshold=75):
        self.path = path
        self.threshold = threshold
        self.data = {}
        self._index = {}
        self._mtime = None
        self._lock = threading.RLock()
        self.reload(force=True)

    def reload(self, force=False):
        with self._lock:
            try:
                mtime = os.path.getmtime(self.path)
            except OSError:
                mtime = None
            if not force and mtime == self._mtime:
                return False
            raw = read_json(self.path, {}) if mtime is not None else {}
            if not isinstance(raw, dict):
                raw = {}
            self.data = {k: v for k, v in raw.items() if isinstance(v, dict)}
            self._mtime = mtime
            self._index = {}
            for key, entry in self.data.items():
                for lang, value in entry.items():
                    if lang == "pinyin" or not isinstance(value, str):
                        continue
                    norm = normalize(value)
                    if norm:
                        self._index.setdefault(norm, []).append((key, lang))
            return True

    def __len__(self):
        return len(self.data)

    def find_keys(self, text, limit=5):
        """Trả về [(điểm, key)] giảm dần: khớp tuyệt đối trước, sau đó fuzzy."""
        norm = normalize(text)
        if not norm:
            return []
        with self._lock:
            self.reload()
            found = {}
            for key, _ in self._index.get(norm, []):
                found[key] = 100
            if not found:
                threshold = self.threshold if len(norm) > 4 else max(self.threshold, 90)
                length = len(norm)
                candidates = []
                for other in self._index:
                    # Cận trên của ratio: loại nhanh các chuỗi chênh lệch độ dài quá lớn.
                    if 200 * min(length, len(other)) / (length + len(other)) < threshold:
                        continue
                    score = fuzz.ratio(norm, other)
                    if score >= threshold:
                        candidates.append((score, other))
                candidates.sort(reverse=True)
                for score, other in candidates[:limit]:
                    for key, _ in self._index[other]:
                        found.setdefault(key, score)
            return sorted(((s, k) for k, s in found.items()), reverse=True)[:limit]

    def lookup(self, text, target_lang) -> Optional[Match]:
        for score, key in self.find_keys(text):
            value = self.data.get(key, {}).get(target_lang)
            if isinstance(value, str) and value.strip():
                return Match(value, int(score), key)
        return None

    def pinyin(self, text):
        for _score, key in self.find_keys(text):
            value = self.data.get(key, {}).get("pinyin")
            if isinstance(value, str) and value.strip():
                return value
        return ""

    def _next_key(self):
        numbers = [int(m.group(1)) for k in self.data if (m := re.fullmatch(r"UI_(\d+)", k))]
        return f"UI_{(max(numbers) + 1 if numbers else 1):03d}"

    def add_or_update(self, raw_text, target_lang, translation):
        """Lưu/sửa bản dịch người dùng chỉnh. Có sao lưu .bak trước khi ghi."""
        raw_text = raw_text.strip()
        translation = translation.strip()
        with self._lock:
            self.reload()
            key = next((k for score, k in self.find_keys(raw_text) if score >= 90), None)
            if key is None:
                key = self._next_key()
                source_lang = guess_lang(raw_text)
                entry = {source_lang: raw_text}
                pinyin = to_pinyin(raw_text)
                if pinyin:
                    entry["pinyin"] = pinyin
                self.data[key] = entry
            self.data[key][target_lang] = translation
            if os.path.exists(self.path):
                shutil.copyfile(self.path, self.path + ".bak")
            atomic_write_json(self.path, self.data)
            self.reload(force=True)
            return key
