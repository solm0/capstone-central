from __future__ import annotations

import re
import subprocess
import unicodedata
from functools import lru_cache
from typing import Any


ESPEAK_VOICE_MAP = {
    "en": "en-us",
    "de": "de",
    "ru": "ru",
    "ko": "ko",
    "ja": "ja",
    "zh": "cmn",
    "fr": "fr",
    "es": "es",
    "sr": "sr",
    "mk": "mk",
}

IPA_STRESS_MARKS = {"ˈ", "ˌ", ".", "|"}
IPA_LENGTH_MARKS = {"ː", "ˑ"}
IPA_MODIFIER_MARKS = {"ʲ", "ʷ", "ˠ", "ˤ", "˞"}
IPA_VOWELS = {
    "i", "y", "ɨ", "ʉ", "ɯ", "u", "ɪ", "ʏ", "ʊ",
    "e", "ø", "ɘ", "ɵ", "ɤ", "o", "ə", "ɛ", "œ",
    "ɜ", "ɞ", "ɚ", "ɝ", "ʌ", "ɔ", "æ", "ɐ", "a",
    "ɶ", "ɑ", "ɒ",
}

BASE_IPA_FEATURES: dict[str, dict[str, Any]] = {
    "p": {"kind": "consonant", "place": "bilabial", "manner": "plosive", "voiced": False},
    "b": {"kind": "consonant", "place": "bilabial", "manner": "plosive", "voiced": True},
    "t": {"kind": "consonant", "place": "alveolar", "manner": "plosive", "voiced": False},
    "d": {"kind": "consonant", "place": "alveolar", "manner": "plosive", "voiced": True},
    "ʈ": {"kind": "consonant", "place": "retroflex", "manner": "plosive", "voiced": False},
    "ɖ": {"kind": "consonant", "place": "retroflex", "manner": "plosive", "voiced": True},
    "c": {"kind": "consonant", "place": "palatal", "manner": "plosive", "voiced": False},
    "ɟ": {"kind": "consonant", "place": "palatal", "manner": "plosive", "voiced": True},
    "k": {"kind": "consonant", "place": "velar", "manner": "plosive", "voiced": False},
    "ɡ": {"kind": "consonant", "place": "velar", "manner": "plosive", "voiced": True},
    "q": {"kind": "consonant", "place": "uvular", "manner": "plosive", "voiced": False},
    "ɢ": {"kind": "consonant", "place": "uvular", "manner": "plosive", "voiced": True},
    "ʔ": {"kind": "consonant", "place": "glottal", "manner": "plosive", "voiced": False},
    "m": {"kind": "consonant", "place": "bilabial", "manner": "nasal", "voiced": True},
    "ɱ": {"kind": "consonant", "place": "labiodental", "manner": "nasal", "voiced": True},
    "n": {"kind": "consonant", "place": "alveolar", "manner": "nasal", "voiced": True},
    "ɳ": {"kind": "consonant", "place": "retroflex", "manner": "nasal", "voiced": True},
    "ɲ": {"kind": "consonant", "place": "palatal", "manner": "nasal", "voiced": True},
    "ŋ": {"kind": "consonant", "place": "velar", "manner": "nasal", "voiced": True},
    "ɴ": {"kind": "consonant", "place": "uvular", "manner": "nasal", "voiced": True},
    "ʙ": {"kind": "consonant", "place": "bilabial", "manner": "trill", "voiced": True},
    "r": {"kind": "consonant", "place": "alveolar", "manner": "trill", "voiced": True},
    "ʀ": {"kind": "consonant", "place": "uvular", "manner": "trill", "voiced": True},
    "ɾ": {"kind": "consonant", "place": "alveolar", "manner": "tap", "voiced": True},
    "ɽ": {"kind": "consonant", "place": "retroflex", "manner": "tap", "voiced": True},
    "ɸ": {"kind": "consonant", "place": "bilabial", "manner": "fricative", "voiced": False},
    "β": {"kind": "consonant", "place": "bilabial", "manner": "fricative", "voiced": True},
    "f": {"kind": "consonant", "place": "labiodental", "manner": "fricative", "voiced": False},
    "v": {"kind": "consonant", "place": "labiodental", "manner": "fricative", "voiced": True},
    "θ": {"kind": "consonant", "place": "dental", "manner": "fricative", "voiced": False},
    "ð": {"kind": "consonant", "place": "dental", "manner": "fricative", "voiced": True},
    "s": {"kind": "consonant", "place": "alveolar", "manner": "fricative", "voiced": False},
    "z": {"kind": "consonant", "place": "alveolar", "manner": "fricative", "voiced": True},
    "ʃ": {"kind": "consonant", "place": "postalveolar", "manner": "fricative", "voiced": False},
    "ʒ": {"kind": "consonant", "place": "postalveolar", "manner": "fricative", "voiced": True},
    "ʂ": {"kind": "consonant", "place": "retroflex", "manner": "fricative", "voiced": False},
    "ʐ": {"kind": "consonant", "place": "retroflex", "manner": "fricative", "voiced": True},
    "ç": {"kind": "consonant", "place": "palatal", "manner": "fricative", "voiced": False},
    "ʝ": {"kind": "consonant", "place": "palatal", "manner": "fricative", "voiced": True},
    "x": {"kind": "consonant", "place": "velar", "manner": "fricative", "voiced": False},
    "ɣ": {"kind": "consonant", "place": "velar", "manner": "fricative", "voiced": True},
    "χ": {"kind": "consonant", "place": "uvular", "manner": "fricative", "voiced": False},
    "ʁ": {"kind": "consonant", "place": "uvular", "manner": "fricative", "voiced": True},
    "ħ": {"kind": "consonant", "place": "pharyngeal", "manner": "fricative", "voiced": False},
    "ʕ": {"kind": "consonant", "place": "pharyngeal", "manner": "fricative", "voiced": True},
    "h": {"kind": "consonant", "place": "glottal", "manner": "fricative", "voiced": False},
    "ɦ": {"kind": "consonant", "place": "glottal", "manner": "fricative", "voiced": True},
    "ɬ": {"kind": "consonant", "place": "alveolar", "manner": "lateral_fricative", "voiced": False},
    "ɮ": {"kind": "consonant", "place": "alveolar", "manner": "lateral_fricative", "voiced": True},
    "ʋ": {"kind": "consonant", "place": "labiodental", "manner": "approximant", "voiced": True},
    "ɹ": {"kind": "consonant", "place": "alveolar", "manner": "approximant", "voiced": True},
    "ɻ": {"kind": "consonant", "place": "retroflex", "manner": "approximant", "voiced": True},
    "j": {"kind": "consonant", "place": "palatal", "manner": "approximant", "voiced": True},
    "ɰ": {"kind": "consonant", "place": "velar", "manner": "approximant", "voiced": True},
    "l": {"kind": "consonant", "place": "alveolar", "manner": "lateral_approximant", "voiced": True},
    "ɭ": {"kind": "consonant", "place": "retroflex", "manner": "lateral_approximant", "voiced": True},
    "ʎ": {"kind": "consonant", "place": "palatal", "manner": "lateral_approximant", "voiced": True},
    "ʟ": {"kind": "consonant", "place": "velar", "manner": "lateral_approximant", "voiced": True},
    "w": {"kind": "consonant", "place": "labial-velar", "manner": "approximant", "voiced": True},
    "ʍ": {"kind": "consonant", "place": "labial-velar", "manner": "fricative", "voiced": False},
    "ɥ": {"kind": "consonant", "place": "labial-palatal", "manner": "approximant", "voiced": True},
    "ɫ": {"kind": "consonant", "place": "alveolar", "manner": "lateral_approximant", "voiced": True},
    "i": {"kind": "vowel", "height": "close", "backness": "front", "rounded": False},
    "y": {"kind": "vowel", "height": "close", "backness": "front", "rounded": True},
    "ɨ": {"kind": "vowel", "height": "close", "backness": "central", "rounded": False},
    "ʉ": {"kind": "vowel", "height": "close", "backness": "central", "rounded": True},
    "ɯ": {"kind": "vowel", "height": "close", "backness": "back", "rounded": False},
    "u": {"kind": "vowel", "height": "close", "backness": "back", "rounded": True},
    "ɪ": {"kind": "vowel", "height": "near-close", "backness": "front", "rounded": False},
    "ʏ": {"kind": "vowel", "height": "near-close", "backness": "front", "rounded": True},
    "ʊ": {"kind": "vowel", "height": "near-close", "backness": "back", "rounded": True},
    "e": {"kind": "vowel", "height": "close-mid", "backness": "front", "rounded": False},
    "ø": {"kind": "vowel", "height": "close-mid", "backness": "front", "rounded": True},
    "ɘ": {"kind": "vowel", "height": "close-mid", "backness": "central", "rounded": False},
    "ɵ": {"kind": "vowel", "height": "close-mid", "backness": "central", "rounded": True},
    "ɤ": {"kind": "vowel", "height": "close-mid", "backness": "back", "rounded": False},
    "o": {"kind": "vowel", "height": "close-mid", "backness": "back", "rounded": True},
    "ə": {"kind": "vowel", "height": "mid", "backness": "central", "rounded": False},
    "ɛ": {"kind": "vowel", "height": "open-mid", "backness": "front", "rounded": False},
    "œ": {"kind": "vowel", "height": "open-mid", "backness": "front", "rounded": True},
    "ɜ": {"kind": "vowel", "height": "open-mid", "backness": "central", "rounded": False},
    "ɞ": {"kind": "vowel", "height": "open-mid", "backness": "central", "rounded": True},
    "ɚ": {"kind": "vowel", "height": "mid", "backness": "central", "rounded": False},
    "ɝ": {"kind": "vowel", "height": "open-mid", "backness": "central", "rounded": False},
    "ʌ": {"kind": "vowel", "height": "open-mid", "backness": "back", "rounded": False},
    "ɔ": {"kind": "vowel", "height": "open-mid", "backness": "back", "rounded": True},
    "æ": {"kind": "vowel", "height": "near-open", "backness": "front", "rounded": False},
    "ɐ": {"kind": "vowel", "height": "near-open", "backness": "central", "rounded": False},
    "a": {"kind": "vowel", "height": "open", "backness": "front", "rounded": False},
    "ɶ": {"kind": "vowel", "height": "open", "backness": "front", "rounded": True},
    "ɑ": {"kind": "vowel", "height": "open", "backness": "back", "rounded": False},
    "ɒ": {"kind": "vowel", "height": "open", "backness": "back", "rounded": True},
}


def resolve_espeak_voice(language: str) -> str:
    language = (language or "en").strip().lower()
    return ESPEAK_VOICE_MAP.get(language, language)


def should_generate_ipa(surface: str) -> bool:
    return any(ch.isalpha() for ch in surface)


def is_ipa_vowel_char(char: str) -> bool:
    return char in IPA_VOWELS


def strip_espeak_language_tags(ipa: str) -> str:
    return re.sub(r"\([A-Za-z-]+\)", "", ipa)


def postprocess_german_ipa(ipa: str) -> str:
    # espeak-ng sometimes emits German eu/äu as a front rounded sequence.
    # Normalize it to the standard diphthong used in broad German IPA.
    ipa = ipa.replace("ɔø", "ɔʏ")

    chars = list(ipa)
    ignored_chars = IPA_STRESS_MARKS | IPA_LENGTH_MARKS | IPA_MODIFIER_MARKS

    for index, char in enumerate(chars):
        if char not in {"r", "ɾ"}:
            continue

        prev_char = next(
            (chars[probe] for probe in range(index - 1, -1, -1) if chars[probe] not in ignored_chars),
            None,
        )
        next_char = next(
            (chars[probe] for probe in range(index + 1, len(chars)) if chars[probe] not in ignored_chars),
            None,
        )

        prev_is_vowel = bool(prev_char and is_ipa_vowel_char(prev_char))
        next_is_vowel = bool(next_char and is_ipa_vowel_char(next_char))

        # Standard German onset / intervocalic consonantal r is typically uvular.
        if next_is_vowel and not prev_is_vowel:
            chars[index] = "ʁ"
            continue

        if next_is_vowel and prev_is_vowel:
            chars[index] = "ʁ"
            continue

        # Post-vocalic syllable-final/word-final r is often vocalized.
        if prev_is_vowel and not next_is_vowel:
            chars[index] = "ɐ"

    return "".join(chars)


def postprocess_russian_ipa(ipa: str) -> str:
    # Keep Russian conservative for now. Sample outputs looked broadly usable,
    # and lexical rewrites like "его" are common but not globally safe enough yet.
    return ipa


def postprocess_serbian_ipa(ipa: str) -> str:
    # Current espeak-ng output already handles Serbian palatal digraphs well.
    # Avoid rewriting until we have stronger corpus-based evidence.
    return ipa


def postprocess_macedonian_ipa(ipa: str) -> str:
    # Macedonian is left conservative for now for the same reason.
    return ipa


@lru_cache(maxsize=8192)
def surface_to_ipa(surface: str, language: str) -> str | None:
    if not surface or not should_generate_ipa(surface):
        return None

    voice = resolve_espeak_voice(language)

    proc = subprocess.run(
        ["espeak-ng", "--ipa", "-q", "-v", voice, surface],
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.returncode != 0:
        return None

    ipa = strip_espeak_language_tags(proc.stdout.strip())

    if ipa:
        if language == "de":
            ipa = postprocess_german_ipa(ipa)
        elif language == "ru":
            ipa = postprocess_russian_ipa(ipa)
        elif language == "sr":
            ipa = postprocess_serbian_ipa(ipa)
        elif language == "mk":
            ipa = postprocess_macedonian_ipa(ipa)

    return ipa or None


def attach_token_ipa(blocks: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    enriched_blocks: list[dict[str, Any]] = []

    for block in blocks:
        tokens = block.get("tokens") or []
        enriched_tokens: list[dict[str, Any]] = []

        for token in tokens:
            token_copy = dict(token)
            token_copy["ipa"] = surface_to_ipa(token.get("surface", ""), language)
            enriched_tokens.append(token_copy)

        enriched_blocks.append({
            **block,
            "tokens": enriched_tokens,
        })

    return enriched_blocks


def tokenize_ipa(ipa: str | None) -> list[str]:
    if not ipa:
        return []

    segments: list[str] = []
    current = ""

    for char in ipa:
        if char in IPA_STRESS_MARKS:
            continue

        if unicodedata.combining(char) or char in IPA_LENGTH_MARKS or char in IPA_MODIFIER_MARKS:
            if current:
                current += char
            continue

        if current:
            segments.append(current)

        current = char

    if current:
        segments.append(current)

    return segments


def consonant_visuals(place: str, manner: str, voiced: bool) -> dict[str, Any]:
    tongue_front_map = {
        "bilabial": 0.12,
        "labiodental": 0.18,
        "dental": 0.26,
        "alveolar": 0.35,
        "postalveolar": 0.42,
        "retroflex": 0.45,
        "palatal": 0.58,
        "velar": 0.72,
        "labial-velar": 0.7,
        "labial-palatal": 0.58,
        "uvular": 0.82,
        "pharyngeal": 0.9,
        "glottal": 0.95,
    }
    tongue_height_map = {
        "bilabial": 0.32,
        "labiodental": 0.35,
        "dental": 0.38,
        "alveolar": 0.42,
        "postalveolar": 0.5,
        "retroflex": 0.55,
        "palatal": 0.72,
        "velar": 0.68,
        "labial-velar": 0.58,
        "labial-palatal": 0.7,
        "uvular": 0.56,
        "pharyngeal": 0.34,
        "glottal": 0.28,
    }
    closure_map = {
        "plosive": "closed",
        "nasal": "closed",
        "fricative": "narrow",
        "lateral_fricative": "narrow",
        "approximant": "open",
        "lateral_approximant": "open",
        "tap": "tap",
        "trill": "narrow",
    }
    lip_map = {
        "bilabial": {"closure": 1, "rounding": 0.15},
        "labiodental": {"closure": 0.45, "rounding": 0.12},
        "labial-velar": {"closure": 0.2, "rounding": 0.85},
        "labial-palatal": {"closure": 0.15, "rounding": 0.75},
    }
    airflow_map = {
        "plosive": "stopped",
        "nasal": "nasal",
        "fricative": "oral_frication",
        "lateral_fricative": "lateral_frication",
        "approximant": "oral",
        "lateral_approximant": "lateral",
        "tap": "tap",
        "trill": "trill",
    }

    return {
        "tongue_height": tongue_height_map.get(place, 0.45),
        "tongue_frontness": tongue_front_map.get(place, 0.4),
        "lip_closure": lip_map.get(place, {}).get("closure", 0),
        "lip_rounding": lip_map.get(place, {}).get("rounding", 0.1),
        "velum": "open" if manner == "nasal" else "closed",
        "glottis": "voiced" if voiced else "spread",
        "constriction": closure_map.get(manner, "open"),
        "airflow": airflow_map.get(manner, "oral"),
    }


def vowel_visuals(height: str, backness: str, rounded: bool) -> dict[str, Any]:
    height_map = {
        "close": 0.84,
        "near-close": 0.76,
        "close-mid": 0.64,
        "mid": 0.52,
        "open-mid": 0.4,
        "near-open": 0.28,
        "open": 0.18,
    }
    backness_map = {
        "front": 0.32,
        "central": 0.55,
        "back": 0.78,
    }

    return {
        "tongue_height": height_map.get(height, 0.5),
        "tongue_frontness": backness_map.get(backness, 0.55),
        "lip_closure": 0,
        "lip_rounding": 0.8 if rounded else 0.1,
        "velum": "closed",
        "glottis": "voiced",
        "constriction": "open",
        "airflow": "oral",
    }


def enrich_feature(base_symbol: str, segment: str) -> dict[str, Any]:
    base = dict(BASE_IPA_FEATURES.get(base_symbol, {"kind": "unknown"}))

    if base["kind"] == "consonant":
        base["visual"] = consonant_visuals(
            place=base.get("place", "alveolar"),
            manner=base.get("manner", "approximant"),
            voiced=bool(base.get("voiced")),
        )
    elif base["kind"] == "vowel":
        base["visual"] = vowel_visuals(
            height=base.get("height", "mid"),
            backness=base.get("backness", "central"),
            rounded=bool(base.get("rounded")),
        )
    else:
        base["visual"] = {
            "tongue_height": 0.5,
            "tongue_frontness": 0.5,
            "lip_closure": 0,
            "lip_rounding": 0.1,
            "velum": "closed",
            "glottis": "neutral",
            "constriction": "open",
            "airflow": "oral",
        }

    base["symbol"] = segment
    base["base_symbol"] = base_symbol
    base["length"] = "normal"
    base["secondary_articulations"] = []

    for char in segment[1:]:
        if char == "ː":
            base["length"] = "long"
        elif char == "ˑ":
            base["length"] = "half-long"
        elif char == "ʲ":
            base["secondary_articulations"].append("palatalized")
            base["visual"]["tongue_height"] = min(0.92, base["visual"]["tongue_height"] + 0.1)
            base["visual"]["tongue_frontness"] = max(0.2, base["visual"]["tongue_frontness"] - 0.08)
        elif char == "ʷ":
            base["secondary_articulations"].append("labialized")
            base["visual"]["lip_rounding"] = max(0.75, base["visual"]["lip_rounding"])
        elif char == "ˠ":
            base["secondary_articulations"].append("velarized")
            base["visual"]["tongue_frontness"] = min(0.92, base["visual"]["tongue_frontness"] + 0.08)
        elif char == "ˤ":
            base["secondary_articulations"].append("pharyngealized")
            base["visual"]["tongue_frontness"] = min(0.95, base["visual"]["tongue_frontness"] + 0.1)
            base["visual"]["tongue_height"] = max(0.18, base["visual"]["tongue_height"] - 0.08)

    return base


def split_surface(surface: str, parts: int) -> list[str]:
    graphemes = list(surface)

    if parts <= 1 or len(graphemes) <= 1:
        return [surface] if parts > 0 else []

    base_size = len(graphemes) // parts
    remainder = len(graphemes) % parts
    out: list[str] = []
    cursor = 0

    for index in range(parts):
        size = base_size + (1 if index < remainder else 0)

        if size == 0:
            out.append("")
            continue

        out.append("".join(graphemes[cursor:cursor + size]))
        cursor += size

    if cursor < len(graphemes):
        out[-1] += "".join(graphemes[cursor:])

    return out


def describe_token_articulation(surface: str, ipa: str | None) -> list[dict[str, Any]]:
    segments = tokenize_ipa(ipa)
    described: list[dict[str, Any]] = []

    for segment in segments:
        base_symbol = segment[0]
        described.append({
            "surface": "",
            "token_surface": surface,
            "ipa": segment,
            "feature": enrich_feature(base_symbol, segment),
        })

    return described
