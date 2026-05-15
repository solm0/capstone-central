from .registry import load_language


def get_config(lang: str):
    return load_language(lang)


def get_ocr(lang: str):
    return load_language(lang)["get_ocr"]()


def get_nlp(lang: str):
    return load_language(lang)["get_nlp"]()
