import random
from pathlib import Path
from typing import Dict

from language_config.registry import get_latest_version_path
from language_config.sqlite_pack import LanguagePackDB, find_pack_db

BASE_DIR = Path("./data/static")

_registry: Dict[str, dict] = {}


def _load_language(lang: str):
    if lang in _registry:
        return _registry[lang]

    lang_dir = BASE_DIR / lang
    version_path = get_latest_version_path(lang_dir)
    db_path = find_pack_db(version_path)
    pack_db = LanguagePackDB(db_path) if db_path else None

    data = {
        "pack_db": pack_db,
    }

    _registry[lang] = data
    return data


def has_key(key: str, lang: str):
    data = _load_language(lang)
    pack_db = data["pack_db"]
    return pack_db.has_lemma_key(key) if pack_db else False


def get_related(key: str, lang: str, k=5):
    data = _load_language(lang)
    pack_db = data["pack_db"]
    return pack_db.get_related(key, k) if pack_db else []


def get_line_ids(key: str, lang: str):
    data = _load_language(lang)
    pack_db = data["pack_db"]
    return pack_db.get_line_ids(key) if pack_db else []


def find_match_indices(tokens, lemma, pos):
    indices = []
    for i, token in enumerate(tokens):
        if token["lemma"] == lemma and token["pos"] == pos:
            indices.append(i)
    return indices


def sample_kwic(line_ids, lemma, pos, lang: str, max_k=20):
    data = _load_language(lang)
    pack_db = data["pack_db"]

    if pack_db is None:
        return []

    short, mid, long = [], [], []

    for line in pack_db.get_lines(line_ids):
        tokens = line["tokens"]
        length = len(tokens)

        if length <= 8:
            short.append(line)
        elif length <= 15:
            mid.append(line)
        else:
            long.append(line)

    def pick(bucket, k):
        if len(bucket) <= k:
            return bucket
        return random.sample(bucket, k)

    result = []
    per_bucket = max_k // 3

    result.extend(pick(short, per_bucket))
    result.extend(pick(mid, per_bucket))
    result.extend(pick(long, per_bucket))

    if len(result) < max_k:
        remaining = [line for line in (short + mid + long) if line not in result]
        if remaining:
            result.extend(
                random.sample(remaining, min(len(remaining), max_k - len(result)))
            )

    kwic = []

    for line in result[:max_k]:
        tokens = line["tokens"]
        indices = find_match_indices(tokens, lemma, pos)

        if not indices:
            continue

        kwic.append({
            "line_id": line["line_id"],
            "tokens": tokens,
            "match_indices": indices,
        })

    return kwic
