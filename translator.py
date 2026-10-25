"""Engine dịch lai: Database cục bộ -> Cache -> Google Translate."""
import logging
import threading
import time
from typing import NamedTuple

from config import CACHE_PATH, LANG_MAP, atomic_write_json, read_json
from textutils import guess_lang, has_cjk, to_pinyin

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

log = logging.getLogger(__name__)


class Result(NamedTuple):
    text: str
    source: str
    score: int = 0
    pinyin: str = ""
    ok: bool = True


def _chunks(text, size=4500):
    if len(text) <= size:
        return [text]
    parts, current = [], ""
    for word in text.split(" "):
        if len(current) + len(word) + 1 > size and current:
            parts.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        parts.append(current)
    return parts


class TranslationEngine:
    CACHE_MAX = 5000

    def __init__(self, cfg, db):
        self.cfg = cfg
        self.db = db
        self._lock = threading.Lock()
        stored = read_json(CACHE_PATH, {})
        self._cache = stored if isinstance(stored, dict) else {}
        self._dirty = 0

    def _pinyin(self, text):
        if not self.cfg.get("show_pinyin") or not has_cjk(text):
            return ""
        return self.db.pinyin(text) or to_pinyin(text)

    def translate(self, text, target_name) -> Result:
        text = (text or "").strip()
        if not text:
            return Result("", "N/A")
        info = LANG_MAP.get(target_name, LANG_MAP["Tiếng Việt"])
        pinyin = self._pinyin(text)

        if not any(ch.isalpha() for ch in text):
            return Result(text, "Giữ nguyên", pinyin=pinyin)

        self.db.threshold = self.cfg.get("fuzzy_threshold")
        match = self.db.lookup(text, info["db"])
        if match:
            return Result(match.text, f"DB ({match.score}%)", match.score, pinyin)

        source_lang = guess_lang(text)
        if source_lang in ("vi", "zh", "ja", "ko") and source_lang == info["db"]:
            return Result(text, "Cùng ngôn ngữ", pinyin=pinyin)

        if not self.cfg.get("google_fallback") or GoogleTranslator is None:
            return Result(text, "Không có trong DB", pinyin=pinyin, ok=False)

        cache_key = f"{info['gt']}|{text}"
        with self._lock:
            cached = self._cache.get(cache_key)
        if cached:
            return Result(cached, "Cache", pinyin=pinyin)

        try:
            translated = self._google(text, info["gt"])
        except Exception as exc:  # mạng lỗi, bị chặn, ...
            log.warning("Google Translate lỗi: %s", exc)
            return Result(text, "Lỗi Google", pinyin=pinyin, ok=False)

        with self._lock:
            self._cache[cache_key] = translated
            self._dirty += 1
            should_flush = self._dirty >= 10
        if should_flush:
            self.flush()
        return Result(translated, "Google", pinyin=pinyin)

    @staticmethod
    def _google(text, target):
        last_error = None
        for attempt in range(3):
            try:
                parts = [GoogleTranslator(source="auto", target=target).translate(c) or c for c in _chunks(text)]
                return " ".join(parts)
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.4 * (attempt + 1))
        raise last_error

    def flush(self):
        with self._lock:
            items = list(self._cache.items())[-self.CACHE_MAX:]
            self._cache = dict(items)
            self._dirty = 0
            snapshot = dict(self._cache)
        try:
            atomic_write_json(CACHE_PATH, snapshot)
        except OSError:
            pass
