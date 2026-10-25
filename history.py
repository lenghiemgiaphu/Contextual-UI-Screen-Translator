"""Lịch sử dịch lưu ra history.json."""
import threading

from config import HISTORY_PATH, atomic_write_json, read_json


class HistoryStore:
    def __init__(self, cfg, path=HISTORY_PATH):
        self.cfg = cfg
        self.path = path
        self._lock = threading.Lock()
        stored = read_json(path, [])
        self._items = stored if isinstance(stored, list) else []

    def _save(self):
        try:
            atomic_write_json(self.path, self._items)
        except OSError:
            pass

    def upsert(self, entry):
        with self._lock:
            for i, item in enumerate(self._items):
                if item.get("id") == entry["id"]:
                    self._items[i] = entry
                    break
            else:
                self._items.append(entry)
            limit = int(self.cfg.get("history_limit"))
            self._items = self._items[-limit:]
            self._save()

    def items(self):
        with self._lock:
            return list(reversed(self._items))

    def delete(self, ids):
        ids = set(ids)
        with self._lock:
            self._items = [i for i in self._items if i.get("id") not in ids]
            self._save()

    def clear(self):
        with self._lock:
            self._items = []
            self._save()
