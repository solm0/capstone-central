from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random


BASE_DIR = Path(__file__).resolve().parent.parent
CATALOG_PATH = BASE_DIR / "data" / "reading_catalog.json"

CATEGORY_DEFINITIONS = {
    "classic_fiction": {
        "label": "Classic fiction",
        "description": "Novels, short stories, and literary classics.",
    },
    "adventure_travel": {
        "label": "Adventure & travel",
        "description": "Voyages, movement, and writing with momentum.",
    },
    "history_biography": {
        "label": "History & biography",
        "description": "Lives, memoir, public memory, and historical reflection.",
    },
    "philosophy_psychology": {
        "label": "Philosophy & psychology",
        "description": "Ideas, self-observation, ethics, and interior life.",
    },
    "religion_spirituality": {
        "label": "Religion & spirituality",
        "description": "Spiritual reflection, faith, and inner practice.",
    },
    "science_nature": {
        "label": "Science & nature",
        "description": "Natural observation, popular science, and the physical world.",
    },
    "society_politics": {
        "label": "Society & politics",
        "description": "Social life, education, public thought, and political writing.",
    },
    "essays_speeches": {
        "label": "Essays & speeches",
        "description": "Reflective prose, criticism, and public address.",
    },
    "myth_folklore": {
        "label": "Myth & folklore",
        "description": "Legends, symbolic writing, and traditional imagination.",
    },
}

DIFFICULTY_ORDER = {
    "easy": 0,
    "normal": 1,
    "hard": 2,
}

LANGUAGE_LABELS = {
    "de": "German",
    "en": "English",
}


@dataclass(frozen=True)
class CatalogEntry:
    id: int
    source: str
    title: str
    author: str
    language: str
    categories: tuple[str, ...]
    difficulty: str
    summary: str
    excerpt: str
    source_url: str


@dataclass
class RecommendationCandidate:
    language: str
    gutenberg_id: int
    title: str
    author: str
    summary: str
    excerpt: str
    source_url: str
    category_key: str | None
    matched_categories: list[str]


_catalog_cache: list[CatalogEntry] | None = None


def dumps_json_list(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=True)


def loads_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    return [value for value in parsed if isinstance(value, str)]


def load_catalog() -> list[CatalogEntry]:
    global _catalog_cache

    if _catalog_cache is not None:
        return _catalog_cache

    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    entries: list[CatalogEntry] = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        language = str(item.get("language", "")).strip().lower()
        difficulty = str(item.get("difficulty", "normal")).strip().lower()
        categories = tuple(
            category
            for category in item.get("categories", [])
            if isinstance(category, str) and category in CATEGORY_DEFINITIONS
        )

        if (
            not isinstance(item.get("id"), int)
            or not language
            or not categories
            or difficulty not in DIFFICULTY_ORDER
        ):
            continue

        entries.append(
            CatalogEntry(
                id=item["id"],
                source=str(item.get("source", "local")),
                title=str(item.get("title", "")).strip(),
                author=str(item.get("author", "")).strip(),
                language=language,
                categories=categories,
                difficulty=difficulty,
                summary=str(item.get("summary", "")).strip(),
                excerpt=str(item.get("excerpt", "")).strip(),
                source_url=str(item.get("source_url", "")).strip(),
            )
        )

    _catalog_cache = entries
    return entries


def catalog_languages() -> list[str]:
    return sorted({entry.language for entry in load_catalog()})


def supported_language_payload() -> list[dict[str, str]]:
    return [
        {
            "code": code,
            "label": LANGUAGE_LABELS.get(code, code),
        }
        for code in catalog_languages()
    ]


def category_payload() -> list[dict[str, str]]:
    present = {
        category
        for entry in load_catalog()
        for category in entry.categories
    }

    return [
        {
            "key": key,
            "label": value["label"],
            "description": value["description"],
        }
        for key, value in CATEGORY_DEFINITIONS.items()
        if key in present
    ]


def normalize_preference_languages(languages: list[str]) -> list[str]:
    available = set(catalog_languages())
    normalized: list[str] = []
    seen: set[str] = set()

    for language in languages:
        code = language.strip().lower()
        if code in available and code not in seen:
            seen.add(code)
            normalized.append(code)

    return normalized


def normalize_preference_categories(categories: list[str]) -> list[str]:
    available = {
        option["key"]
        for option in category_payload()
    }
    normalized: list[str] = []
    seen: set[str] = set()

    for category in categories:
        key = category.strip()
        if key in available and key not in seen:
            seen.add(key)
            normalized.append(key)

    return normalized


def choose_language_order(preferred_languages: list[str], available_languages: list[str]) -> list[str]:
    available_set = set(available_languages)
    eligible = [language for language in preferred_languages if language in available_set]
    random.shuffle(eligible)
    return eligible


def category_match(entry: CatalogEntry, selected_categories: list[str]) -> tuple[bool, int]:
    entry_categories = set(entry.categories)
    overlap = [category for category in selected_categories if category in entry_categories]
    return len(overlap) == len(selected_categories), len(overlap)


def rank_candidates(
    entries: list[CatalogEntry],
    selected_categories: list[str],
) -> list[tuple[CatalogEntry, bool, int]]:
    ranked: list[tuple[CatalogEntry, bool, int]] = []

    for entry in entries:
        is_and_match, overlap = category_match(entry, selected_categories)
        if overlap == 0:
            continue

        ranked.append((entry, is_and_match, overlap))

    ranked.sort(
        key=lambda item: (
            item[1],
            item[2],
            -DIFFICULTY_ORDER.get(item[0].difficulty, 1),
        ),
        reverse=True,
    )
    return ranked


def pick_best_entry(
    ranked: list[tuple[CatalogEntry, bool, int]],
) -> CatalogEntry | None:
    if not ranked:
        return None

    and_matches = [item for item in ranked if item[1]]
    pool = and_matches[:3] if and_matches else ranked[:4]
    return random.choice(pool)[0]


def generate_recommendation(
    preferred_languages: list[str],
    selected_categories: list[str],
    available_languages: list[str],
    excluded_book_ids: set[int] | None = None,
) -> RecommendationCandidate:
    excluded = excluded_book_ids or set()
    eligible_languages = choose_language_order(preferred_languages, available_languages)

    if not eligible_languages:
        raise ValueError("No installed language currently has curated reading excerpts.")

    if not selected_categories:
        raise ValueError("Pick at least one category to receive recommendations.")

    catalog = load_catalog()

    for language in eligible_languages:
        language_entries = [
            entry
            for entry in catalog
            if entry.language == language
            and entry.id not in excluded
            and entry.difficulty != "hard"
        ]

        ranked = rank_candidates(language_entries, selected_categories)
        chosen = pick_best_entry(ranked)

        if chosen is None:
            continue

        matched_categories = [
            category
            for category in selected_categories
            if category in chosen.categories
        ]

        return RecommendationCandidate(
            language=chosen.language,
            gutenberg_id=chosen.id,
            title=chosen.title,
            author=chosen.author,
            summary=chosen.summary,
            excerpt=chosen.excerpt,
            source_url=chosen.source_url,
            category_key=matched_categories[0] if matched_categories else chosen.categories[0],
            matched_categories=matched_categories,
        )

    raise RuntimeError("No curated excerpt matched your current language and category choices.")
