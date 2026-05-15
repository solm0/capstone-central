import re

from pathlib import Path
from .sqlite_pack import LanguagePackDB, find_pack_db


LATIN_TO_CYR = str.maketrans({
    "a": "а", "A": "А",
    "e": "е", "E": "Е",
    "o": "о", "O": "О",
    "p": "р", "P": "Р",
    "c": "с", "C": "С",
    "y": "у", "Y": "У",
    "x": "х", "X": "Х",
    "n": "п", "N": "П",
    "u": "и", "U": "И",
    "k": "к", "K": "К",
    "m": "м", "M": "М",
    "t": "т", "T": "Т",
    "b": "в", "B": "В",
    "h": "н", "H": "Н",
})


def normalize(text: str):
    return text.translate(LATIN_TO_CYR)


def tokenize(text: str):
    text = text.lower()
    text = text.replace("ё", "е")
    text = re.sub(r"[^а-яё0-9\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.split()


_nlp = None


def get_ocr():
    return None


def get_nlp():
    global _nlp

    if _nlp is None:
        import stanza

        _nlp = stanza.Pipeline(
            lang="ru",
            processors="tokenize,pos,lemma,depparse",
            use_gpu=False,
            download_method=None,
        )

    return _nlp


def get_config(base_dir: Path):
    lang_dir = base_dir / "ru"

    from .registry import get_latest_version_path

    version_path = get_latest_version_path(lang_dir)
    db_path = find_pack_db(version_path)
    pack_db = LanguagePackDB(db_path) if db_path else None

    return {
        "normalize": normalize,
        "tokenize": tokenize,
        "get_ocr": get_ocr,
        "get_nlp": get_nlp,
        "pack_db": pack_db,
        "db_path": db_path,
    }
