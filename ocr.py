"""OCR bằng Tesseract: tiền xử lý ảnh, lọc theo độ tin cậy, gom dòng đúng thứ tự."""
import logging
import re
from typing import List, NamedTuple

import pytesseract
from PIL import Image, ImageOps, ImageStat

from config import OCR_PROFILES, find_tesseract
from textutils import CJK_RE, fix_cjk_spaces

log = logging.getLogger(__name__)
_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


class OcrError(Exception):
    pass


class OcrResult(NamedTuple):
    lines: List[str]
    langs: str
    missing: List[str]


def preprocess(img):
    """Xám hoá, đảo màu nếu nền tối, phóng to theo kích thước, tăng tương phản, thêm viền."""
    gray = ImageOps.grayscale(img.convert("RGB"))
    if ImageStat.Stat(gray).mean[0] < 128:
        gray = ImageOps.invert(gray)
    width, height = gray.size
    scale = max(1, min(4, round(1000 / max(height, 1))))
    while width * scale > 6000 and scale > 1:
        scale -= 1
    if scale > 1:
        gray = gray.resize((width * scale, height * scale), _LANCZOS)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    return ImageOps.expand(gray, border=12, fill=255)


class OcrEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self._installed = None
        self.path = ""
        self.apply_path()

    def apply_path(self):
        self.path = find_tesseract(self.cfg.get("tesseract_path"))
        if self.path:
            pytesseract.pytesseract.tesseract_cmd = self.path
        self._installed = None
        return self.path

    @property
    def available(self):
        return bool(self.path)

    def installed_languages(self):
        if self._installed is None:
            try:
                self._installed = set(pytesseract.get_languages(config=""))
            except Exception:
                self._installed = set()
        return self._installed

    def resolve(self, profile):
        wanted = OCR_PROFILES.get(profile, OCR_PROFILES["Tự động"])
        installed = self.installed_languages()
        if not installed:
            return "eng", []
        usable = [lang for lang in wanted if lang in installed]
        missing = [lang for lang in wanted if lang not in installed]
        if not usable:
            fallback = "eng" if "eng" in installed else sorted(installed - {"osd"})[0]
            usable = [fallback]
        return "+".join(usable), missing

    def recognize(self, image, profile) -> OcrResult:
        if not self.available:
            raise OcrError("Chưa tìm thấy Tesseract OCR. Hãy cài đặt hoặc chọn đường dẫn trong Cài đặt.")
        langs, missing = self.resolve(profile)
        processed = preprocess(image)
        psm = int(self.cfg.get("ocr_psm"))
        try:
            data = pytesseract.image_to_data(
                processed, lang=langs, config=f"--psm {psm}", output_type=pytesseract.Output.DICT
            )
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrError("Không chạy được Tesseract. Kiểm tra lại đường dẫn trong Cài đặt.") from exc
        except Exception as exc:
            raise OcrError(f"OCR lỗi: {exc}") from exc

        grouped = {}
        for i, word in enumerate(data["text"]):
            word = (word or "").strip()
            if not word:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                continue
            if conf < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            grouped.setdefault(key, []).append((word, conf))

        min_conf = float(self.cfg.get("ocr_min_conf"))
        lines = []
        for key in sorted(grouped):
            words = grouped[key]
            text = fix_cjk_spaces(" ".join(w for w, _ in words))
            average = sum(c for _, c in words) / len(words)
            if average < min_conf or not re.search(r"\w", text):
                continue
            if len(text) == 1 and not CJK_RE.search(text):
                continue
            lines.append(text)
        return OcrResult(lines, langs, missing)
