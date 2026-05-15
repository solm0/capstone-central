def align_tokens(sent):
    split_tokens = sent.text.split()
    stanza_words = sent.words

    tokens = []
    w_idx = 0

    for split_tok in split_tokens:
        buffer = ""
        matched_words = []

        while w_idx < len(stanza_words):
            word = stanza_words[w_idx]
            buffer += word.text
            matched_words.append(word)
            w_idx += 1

            if buffer == split_tok:
                break

        if buffer == split_tok and matched_words:
            main = matched_words[0]
            tokens.append({
                "surface": split_tok,
                "lemma": main.lemma.lower() if main.lemma else None,
                "pos": main.upos,
                "dep": main.deprel,
            })
        else:
            tokens.append({
                "surface": split_tok,
                "lemma": None,
                "pos": None,
                "dep": None,
            })

    return tokens
