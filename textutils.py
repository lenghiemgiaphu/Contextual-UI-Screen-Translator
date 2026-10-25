"""Chuẩn hoá chữ, nhận diện ngôn ngữ, pinyin."""
import re
import unicodedata

try:
    from pypinyin import Style, lazy_pinyin
except ImportError:  # tuỳ chọn
    lazy_pinyin = None
    Style = None

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
HANGUL_RE = re.compile(r"[\uac00-\ud7af]")
VI_CHARS = set("ăâđêôơưàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ")
_CJK_GAP = re.compile(
    r"(?<=[\u3000-\u9fff\uf900-\ufaff\uff00-\uffef])\s+(?=[\u3000-\u9fff\uf900-\ufaff\uff00-\uffef])"
)


def has_cjk(text):
    return bool(CJK_RE.search(text))


def fix_cjk_spaces(text):
    """Tesseract hay chèn dấu cách giữa các chữ Hán: '历 史 记 录' -> '历史记录'."""
    return _CJK_GAP.sub("", text)


def join_lines(lines):
    return fix_cjk_spaces(" ".join(line.strip() for line in lines if line.strip()))


def _fold_latin_accents(text):
    out = []
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.category(ch) == "Mn" and out and ord(out[-1]) < 0x250:
            continue
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out)).replace("đ", "d")


def normalize(text):
    """Dạng so khớp: bỏ dấu câu, khoảng trắng thừa, hoa/thường và dấu tiếng Việt."""
    t = unicodedata.normalize("NFKC", text).casefold()
    t = _fold_latin_accents(t)
    t = re.sub(r"[\W_]+", " ", t).strip()
    if has_cjk(t):
        t = t.replace(" ", "")
    return t


def guess_lang(text):
    if KANA_RE.search(text):
        return "ja"
    if HANGUL_RE.search(text):
        return "ko"
    if CJK_RE.search(text):
        return "zh"
    if any(ch in VI_CHARS for ch in text.lower()):
        return "vi"
    return "en"


def to_pinyin(text):
    if lazy_pinyin is None or not CJK_RE.search(text):
        return ""
    return " ".join(lazy_pinyin(text, style=Style.TONE))
