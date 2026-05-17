from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import random
import re
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SUPPORTED_LANGUAGE_LABELS = {
    "ca": "Catalan",
    "zh": "Chinese",
    "da": "Danish",
    "nl": "Dutch",
    "en": "English",
    "eo": "Esperanto",
    "fi": "Finnish",
    "fr": "French",
    "de": "German",
    "el": "Greek",
    "hu": "Hungarian",
    "it": "Italian",
    "la": "Latin",
    "pt": "Portuguese",
    "es": "Spanish",
    "sv": "Swedish",
    "tl": "Tagalog",
}

SUPPORTED_LANGUAGE_CODES = set(SUPPORTED_LANGUAGE_LABELS.keys())

CATEGORY_DEFINITIONS = {
    "classic_fiction": {
        "label": "Classic fiction",
        "description": "Novels, short stories, and literary classics.",
        "topics": [
            "Classics Bookshelf",
            "Classics of Literature",
            "General Fiction",
            "Novels",
        ],
        "keywords": [
            "classics",
            "classic",
            "fiction",
            "novel",
            "short stories",
            "literature",
            "bildungsromans",
            "domestic fiction",
            "historical fiction",
            "psychological fiction",
        ],
    },
    "adventure_travel": {
        "label": "Adventure & travel",
        "description": "Voyages, sea stories, exploration, and adventure.",
        "topics": [
            "Adventure",
            "Travel Writing",
            "Sea stories",
            "Geography",
        ],
        "keywords": [
            "adventure",
            "travel",
            "voyages",
            "sea stories",
            "explorers",
            "description and travel",
            "geography",
            "expeditions",
        ],
    },
    "history_biography": {
        "label": "History & biography",
        "description": "History, memoir, public figures, and lives.",
        "topics": [
            "History Bookshelf",
            "Biographies",
            "History - Ancient",
            "History - Modern (1750+)",
        ],
        "keywords": [
            "history",
            "biography",
            "memoir",
            "civilization",
            "war",
            "historical",
            "kings and rulers",
            "statesmen",
        ],
    },
    "philosophy_psychology": {
        "label": "Philosophy & psychology",
        "description": "Ideas, ethics, mind, and self-reflection.",
        "topics": [
            "Psychology and Philosophy",
            "Philosophy & Ethics",
            "Psychology",
        ],
        "keywords": [
            "philosophy",
            "ethics",
            "psychology",
            "conduct of life",
            "mind",
            "consciousness",
            "dreams",
            "psychoanalysis",
            "stoicism",
        ],
    },
    "religion_spirituality": {
        "label": "Religion & spirituality",
        "description": "Religious thought, spiritual practice, and reflection.",
        "topics": [
            "Religion Bookshelf",
            "Religion/Spirituality",
            "Hinduism",
            "Buddhism",
        ],
        "keywords": [
            "religion",
            "spiritual",
            "devotional",
            "mysticism",
            "christian life",
            "buddhism",
            "hinduism",
            "mythology",
        ],
    },
    "science_nature": {
        "label": "Science & nature",
        "description": "Popular science, natural history, and the physical world.",
        "topics": [
            "Science Bookshelf",
            "Science",
            "Astronomy",
            "Natural history",
        ],
        "keywords": [
            "science",
            "astronomy",
            "physics",
            "chemistry",
            "biology",
            "natural history",
            "nature",
            "plants",
            "animals",
            "evolution",
        ],
    },
    "society_politics": {
        "label": "Society & politics",
        "description": "Government, education, economics, and public life.",
        "topics": [
            "Social Sciences Bookshelf",
            "Law Bookshelf",
            "Political science",
            "Education Bookshelf",
        ],
        "keywords": [
            "political science",
            "government",
            "democracy",
            "law",
            "economics",
            "education",
            "social",
            "women",
            "labor",
            "liberty",
        ],
    },
    "essays_speeches": {
        "label": "Essays & speeches",
        "description": "Shorter reflective prose, criticism, and public address.",
        "topics": [
            "Essays, Letters & Speeches",
            "General Works",
            "Criticism",
        ],
        "keywords": [
            "essays",
            "letters",
            "speeches",
            "criticism",
            "literary criticism",
            "oratory",
            "lectures",
        ],
    },
    "myth_folklore": {
        "label": "Myth & folklore",
        "description": "Legends, fairy tales, folklore, and mythic writing.",
        "topics": [
            "Mythology, Legends & Folklore",
            "Folklore",
            "Fairy tales",
        ],
        "keywords": [
            "mythology",
            "legends",
            "folklore",
            "fairy tales",
            "epic literature",
            "gods",
            "heroes",
        ],
    },
}

ARCHAIC_MARKERS = {
    "en": {
        "thou",
        "thee",
        "thy",
        "thine",
        "hath",
        "doth",
        "wherefore",
        "whilst",
    }
}

HEADER_PATTERNS = [
    re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", re.IGNORECASE | re.DOTALL),
    re.compile(r"START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK", re.IGNORECASE),
]
FOOTER_PATTERNS = [
    re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*", re.IGNORECASE | re.DOTALL),
    re.compile(r"END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*", re.IGNORECASE | re.DOTALL),
]
HEADING_PATTERN = re.compile(
    r"^(chapter|book|part|contents|illustrations|preface|introduction)\b",
    re.IGNORECASE,
)
ROMAN_HEADING_PATTERN = re.compile(r"^[IVXLCDM]{1,8}$")
WORD_PATTERN = re.compile(r"[^\W\d_]+(?:['-][^\W\d_]+)?", re.UNICODE)


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


def supported_language_payload() -> list[dict[str, str]]:
    return [
        {"code": code, "label": label}
        for code, label in SUPPORTED_LANGUAGE_LABELS.items()
    ]


def category_payload() -> list[dict[str, str]]:
    return [
        {
            "key": key,
            "label": value["label"],
            "description": value["description"],
        }
        for key, value in CATEGORY_DEFINITIONS.items()
    ]


def normalize_preference_languages(languages: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []

    for language in languages:
        code = language.strip().lower()
        if code in SUPPORTED_LANGUAGE_CODES and code not in seen:
            seen.add(code)
            normalized.append(code)

    return normalized


def normalize_preference_categories(categories: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []

    for category in categories:
        key = category.strip()
        if key in CATEGORY_DEFINITIONS and key not in seen:
            seen.add(key)
            normalized.append(key)

    return normalized


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


def fetch_gutendex_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": "NautilusReadingRecommendations/1.0",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=6) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, socket.timeout, json.JSONDecodeError) as error:
        raise RuntimeError("Could not fetch Gutenberg catalog data right now.") from error


def fetch_remote_text(url: str) -> str | None:
    request = Request(
        url,
        headers={
            "User-Agent": "NautilusReadingRecommendations/1.0",
            "Accept": "text/plain,text/html;q=0.9,*/*;q=0.8",
        },
    )

    try:
        with urlopen(request, timeout=8) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="ignore")
    except (HTTPError, URLError, TimeoutError, socket.timeout, UnicodeDecodeError):
        return None


def build_gutendex_url(language: str, topic: str | None = None) -> str:
    params = {
        "languages": language,
        "mime_type": "text/",
        "sort": "popular",
    }

    if topic:
        params["topic"] = topic

    return f"https://gutendex.com/books?{urlencode(params)}"


def fetch_books_for_language(language: str, categories: list[str]) -> list[dict[str, Any]]:
    seen_ids: set[int] = set()
    results: list[dict[str, Any]] = []
    urls: list[str] = []

    for category in categories:
        for topic in CATEGORY_DEFINITIONS[category]["topics"][:2]:
            urls.append(build_gutendex_url(language, topic))

    if not urls:
        urls.append(build_gutendex_url(language))

    urls.append(build_gutendex_url(language))

    for url in urls:
        if len(results) >= 60:
            break

        try:
            payload = fetch_gutendex_json(url)
        except RuntimeError:
            continue

        for book in payload.get("results", []):
            book_id = book.get("id")
            if not isinstance(book_id, int) or book_id in seen_ids:
                continue

            seen_ids.add(book_id)
            results.append(book)

            if len(results) >= 60:
                break

    return results


def normalize_text_for_match(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def score_book(book: dict[str, Any], categories: list[str]) -> tuple[int, list[str]]:
    fields = [
        *book.get("subjects", []),
        *book.get("bookshelves", []),
        book.get("title", ""),
        *book.get("summaries", []),
    ]
    haystack = " || ".join(normalize_text_for_match(str(field)) for field in fields if field)

    total_score = 0
    matched_categories: list[str] = []

    for category in categories:
        definition = CATEGORY_DEFINITIONS[category]
        score = 0

        for topic in definition["topics"]:
            if normalize_text_for_match(topic) in haystack:
                score += 4

        for keyword in definition["keywords"]:
            if normalize_text_for_match(keyword) in haystack:
                score += 2

        if score > 0:
            matched_categories.append(category)
            total_score += score

    total_score += min(int(book.get("download_count", 0)) // 250, 12)

    return total_score, matched_categories


def pick_text_url(book: dict[str, Any]) -> str | None:
    formats = book.get("formats", {})

    if not isinstance(formats, dict):
        return None

    preferred_order = [
        "text/plain; charset=utf-8",
        "text/plain; charset=us-ascii",
        "text/plain",
        "text/plain; charset=iso-8859-1",
    ]

    for key in preferred_order:
        value = formats.get(key)
        if isinstance(value, str):
            return value

    for key, value in formats.items():
        if isinstance(key, str) and key.startswith("text/plain") and isinstance(value, str):
            return value

    return None


def strip_gutenberg_boilerplate(raw_text: str) -> str:
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")

    for pattern in HEADER_PATTERNS:
        match = pattern.search(text)
        if match:
            text = text[match.end():]
            break

    for pattern in FOOTER_PATTERNS:
        match = pattern.search(text)
        if match:
            text = text[:match.start()]
            break

    return text.strip()


def normalize_paragraph(raw_paragraph: str) -> str:
    paragraph = re.sub(r"\s+", " ", raw_paragraph).strip()
    paragraph = paragraph.replace("_", "")
    return paragraph


def looks_like_heading(paragraph: str) -> bool:
    if len(paragraph) > 120:
        return False

    stripped = paragraph.strip(" .:-")

    if HEADING_PATTERN.match(stripped):
        return True

    if ROMAN_HEADING_PATTERN.fullmatch(stripped):
        return True

    upper_ratio = (
        sum(1 for char in stripped if char.isupper()) / max(1, sum(1 for char in stripped if char.isalpha()))
    )
    return upper_ratio > 0.8 and len(stripped) < 60


def extract_candidate_paragraphs(raw_text: str) -> list[str]:
    cleaned = strip_gutenberg_boilerplate(raw_text)
    paragraphs: list[str] = []

    for chunk in re.split(r"\n\s*\n+", cleaned):
        paragraph = normalize_paragraph(chunk)
        if len(paragraph) < 40:
            continue
        if looks_like_heading(paragraph):
            continue
        if paragraph.lower().startswith("produced by "):
            continue
        paragraphs.append(paragraph)

    return paragraphs


def split_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def difficulty_score(text: str, language: str) -> float:
    words = WORD_PATTERN.findall(text.lower())
    if not words:
        return 999.0

    sentences = split_sentences(text)
    sentence_lengths = [len(WORD_PATTERN.findall(sentence)) for sentence in sentences if sentence]

    avg_sentence_words = sum(sentence_lengths) / max(1, len(sentence_lengths))
    long_sentence_ratio = (
        sum(1 for length in sentence_lengths if length >= 28) / max(1, len(sentence_lengths))
    )
    long_word_ratio = sum(1 for word in words if len(word) >= 9) / len(words)
    archaic_markers = ARCHAIC_MARKERS.get(language, set())
    archaic_ratio = sum(1 for word in words if word in archaic_markers) / len(words)
    footnote_hits = len(re.findall(r"\[\d+\]|\(\d+\)|\bchapter\s+[ivxlcdm]+\b", text, re.IGNORECASE))
    footnote_ratio = footnote_hits / max(1, len(sentences))
    dialogue_ratio = sum(1 for sentence in sentences if '"' in sentence or "“" in sentence or "”" in sentence) / max(1, len(sentences))
    all_caps_lines = [
        line for line in text.splitlines()
        if len(line.strip()) >= 6 and any(char.isalpha() for char in line)
    ]
    all_caps_ratio = (
        sum(1 for line in all_caps_lines if line.strip().upper() == line.strip()) / max(1, len(all_caps_lines))
    )

    score = 0.0
    score += max(avg_sentence_words - 18, 0) * 1.15
    score += long_sentence_ratio * 20
    score += long_word_ratio * 22
    score += archaic_ratio * 28
    score += footnote_ratio * 18
    score += all_caps_ratio * 10
    score -= dialogue_ratio * 6

    return max(score, 0.0)


def score_excerpt_window(window_text: str, language: str) -> float:
    length_penalty = abs(len(window_text) - 1000) / 75
    return length_penalty + difficulty_score(window_text, language)


def build_excerpt_from_paragraphs(paragraphs: list[str], language: str) -> str | None:
    best_window: str | None = None
    best_score: float | None = None

    for start in range(len(paragraphs)):
        combined: list[str] = []

        for end in range(start, min(start + 6, len(paragraphs))):
            combined.append(paragraphs[end])
            window_text = "\n\n".join(combined)

            if len(window_text) < 600:
                continue
            if len(window_text) > 1700:
                break

            score = score_excerpt_window(window_text, language)
            if difficulty_score(window_text, language) > 48:
                continue

            if best_score is None or score < best_score:
                best_score = score
                best_window = window_text

    if best_window:
        return best_window

    fallback: str | None = None
    fallback_score: float | None = None

    for start in range(len(paragraphs)):
        combined: list[str] = []

        for end in range(start, min(start + 5, len(paragraphs))):
            combined.append(paragraphs[end])
            window_text = "\n\n".join(combined)

            if len(window_text) < 450:
                continue
            if len(window_text) > 1800:
                break

            score = score_excerpt_window(window_text, language)
            if fallback_score is None or score < fallback_score:
                fallback_score = score
                fallback = window_text

    return fallback


def summarize_book(book: dict[str, Any], language: str, matched_categories: list[str]) -> str:
    summaries = book.get("summaries", [])
    if summaries:
        first_summary = str(summaries[0]).strip()
        first_sentence = split_sentences(first_summary)[0] if split_sentences(first_summary) else first_summary
        if first_sentence:
            return first_sentence[:220]

    language_label = SUPPORTED_LANGUAGE_LABELS.get(language, language)
    author = extract_author(book)
    category_label = (
        CATEGORY_DEFINITIONS[matched_categories[0]]["label"].lower()
        if matched_categories else "classic writing"
    )

    return f"A short {category_label} recommendation in {language_label} from {author}."


def extract_author(book: dict[str, Any]) -> str:
    authors = book.get("authors", [])
    if not authors:
        return "an unknown author"

    first_author = authors[0]
    name = first_author.get("name") if isinstance(first_author, dict) else None
    return name if isinstance(name, str) and name.strip() else "an unknown author"


def choose_language(preferred_languages: list[str], available_languages: list[str]) -> list[str]:
    available_set = set(available_languages)
    eligible = [language for language in preferred_languages if language in available_set]
    random.shuffle(eligible)
    return eligible


def generate_recommendation(
    preferred_languages: list[str],
    selected_categories: list[str],
    available_languages: list[str],
    excluded_book_ids: set[int] | None = None,
) -> RecommendationCandidate:
    eligible_languages = choose_language(preferred_languages, available_languages)
    excluded = excluded_book_ids or set()

    if not eligible_languages:
        raise ValueError("No supported installed language matches your reading preferences.")

    if not selected_categories:
        raise ValueError("Pick at least one category to receive recommendations.")

    for language in eligible_languages:
        books = fetch_books_for_language(language, selected_categories)
        ranked: list[tuple[int, dict[str, Any], list[str]]] = []

        for book in books:
            book_id = book.get("id")
            if not isinstance(book_id, int) or book_id in excluded:
                continue

            text_url = pick_text_url(book)
            if not text_url:
                continue

            score, matched_categories = score_book(book, selected_categories)
            if score <= 0:
                continue

            ranked.append((score, book, matched_categories))

        ranked.sort(
            key=lambda item: (
                len(item[2]) == len(selected_categories),
                len(item[2]),
                item[0],
                item[1].get("download_count", 0),
            ),
            reverse=True,
        )

        for _, book, matched_categories in ranked[:6]:
            text_url = pick_text_url(book)
            if not text_url:
                continue

            raw_text = fetch_remote_text(text_url)
            if not raw_text:
                continue

            paragraphs = extract_candidate_paragraphs(raw_text)
            excerpt = build_excerpt_from_paragraphs(paragraphs, language)
            if not excerpt:
                continue

            book_id = int(book["id"])
            return RecommendationCandidate(
                language=language,
                gutenberg_id=book_id,
                title=str(book.get("title") or f"Project Gutenberg #{book_id}"),
                author=extract_author(book),
                summary=summarize_book(book, language, matched_categories),
                excerpt=excerpt,
                source_url=f"https://www.gutenberg.org/ebooks/{book_id}",
                category_key=matched_categories[0] if matched_categories else None,
                matched_categories=matched_categories,
            )

    raise RuntimeError("Could not find a suitable Gutenberg excerpt right now.")
