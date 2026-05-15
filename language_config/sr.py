import re
import unicodedata
from pathlib import Path

from .sqlite_pack import LanguagePackDB, find_pack_db


CYR_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "ђ": "đ", "е": "e", "ж": "ž", "з": "z", "и": "i",
    "ј": "j", "к": "k", "л": "l", "љ": "lj", "м": "m",
    "н": "n", "њ": "nj", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "ћ": "ć", "у": "u", "ф": "f",
    "х": "h", "ц": "c", "ч": "č", "џ": "dž", "ш": "š",
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D",
    "Ђ": "Đ", "Е": "E", "Ж": "Ž", "З": "Z", "И": "I",
    "Ј": "J", "К": "K", "Л": "L", "Љ": "Lj", "М": "M",
    "Н": "N", "Њ": "Nj", "О": "O", "П": "P", "Р": "R",
    "С": "S", "Т": "T", "Ћ": "Ć", "У": "U", "Ф": "F",
    "Х": "H", "Ц": "C", "Ч": "Č", "Џ": "Dž", "Ш": "Š",
}


def cyr_to_lat(text: str) -> str:
    return "".join(CYR_MAP.get(ch, ch) for ch in text)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    return cyr_to_lat(text)


TOKEN_RE = re.compile(r"[a-zčćžšđ0-9-]+", re.IGNORECASE)


def tokenize(text: str):
    return TOKEN_RE.findall(normalize(text))


_nlp = None


def get_ocr():
    return None


def get_nlp():
    global _nlp

    if _nlp is None:
        import classla

        _nlp = classla.Pipeline(
            lang="sr",
            processors="tokenize,pos,lemma,depparse",
            use_gpu=False,
        )

    return _nlp


def get_config(base_dir: Path):
    lang_dir = base_dir / "sr"

    from .registry import get_latest_version_path

    version_path = get_latest_version_path(lang_dir)
    db_path = find_pack_db(version_path)

    return {
        "normalize": normalize,
        "tokenize": tokenize,
        "get_ocr": get_ocr,
        "get_nlp": get_nlp,
        "pack_db": LanguagePackDB(db_path) if db_path else None,
        "db_path": db_path,
    }
