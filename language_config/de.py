import re
import unicodedata

from pathlib import Path
from .sqlite_pack import LanguagePackDB, find_pack_db


def normalize(text: str):
    return unicodedata.normalize("NFC", text)


def tokenize(text: str):
    text = normalize(text)
    text = re.sub(r"[^A-Za-zÄÖÜäöüß\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = text.split()
    return [t for t in tokens if len(t) >= 2]


_nlp = None


def get_ocr():
    return None


def get_nlp():
    global _nlp

    if _nlp is None:
        import stanza

        _nlp = stanza.Pipeline(
            lang="de",
            processors="tokenize,pos,lemma,depparse",
            use_gpu=False,
            download_method=None,
        )

    return _nlp


def get_config(base_dir: Path):
    lang_dir = base_dir / "de"

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
