import re
import unicodedata
from pathlib import Path

from .sqlite_pack import LanguagePackDB, find_pack_db


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return text.lower()


TOKEN_RE = re.compile(r"[а-шѓќжчџшљњјѕ0-9-]+", re.IGNORECASE)


def tokenize(text: str):
    return TOKEN_RE.findall(normalize(text))


_nlp = None
BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"


def get_ocr():
    return None


def get_nlp():
    global _nlp

    if _nlp is None:
        import classla

        _nlp = classla.Pipeline(
            lang="mk",
            processors="tokenize,pos,lemma",
            use_gpu=False,
            dir=str(MODEL_DIR),
            download_method=None,
        )

    return _nlp


def get_config(base_dir: Path):
    lang_dir = base_dir / "mk"

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
