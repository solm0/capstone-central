from language_config.registry import load_language


def tokenize(text: str, language: str):
    cfg = load_language(language)
    return cfg["tokenize"](text)


def normalize_predictions(preds, limit=10):
    if not preds:
        return []

    if isinstance(preds, dict):
        total = sum(preds.values()) or 1

        return [
            (word, freq / total)
            for word, freq in sorted(
                preds.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:limit]
        ]

    if isinstance(preds, list):
        return preds[:limit]

    return []


def predict_next(tokens, language: str):
    cfg = load_language(language)
    pack_db = cfg.get("pack_db")

    if pack_db is None:
        return []

    if tokens and tokens[-1] == "<s>":
        return normalize_predictions(pack_db.get_unigrams(limit=10))

    if len(tokens) >= 2:
        ctx = (tokens[-2], tokens[-1])
        tri = pack_db.get_trigram(ctx, limit=10)
        if tri:
            return normalize_predictions(tri)

    if len(tokens) >= 1:
        ctx = (tokens[-1],)
        bi = pack_db.get_bigram(ctx, limit=10)
        if bi:
            return normalize_predictions(bi)

    return normalize_predictions(pack_db.get_unigrams(limit=10))


def search_prefix(q: str, language: str):
    cfg = load_language(language)
    pack_db = cfg.get("pack_db")

    if pack_db is None:
        return []

    q = q.lower()

    if len(q) < 3:
        return []

    results = pack_db.get_prefix_matches(q)
    total = sum(freq for _, freq in results) or 1

    return [(word, freq / total) for word, freq in results]
