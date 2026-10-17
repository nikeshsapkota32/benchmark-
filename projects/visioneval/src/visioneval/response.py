"""Versioned, whole-response parsing; never search prose for an answer."""


def numeric_text(prediction, kind, index):
    if prediction is None:
        return None
    if not isinstance(prediction, str):
        raise ValueError(f"record {index}: numeric-text-v1 prediction must be a string or null")
    text = prediction.strip(" \t\r\n\v\f")
    if not text:
        return None
    digits = text[1:] if kind == "arithmetic" and text[0] in "+-" else text
    if not digits or any(char not in "0123456789" for char in digits):
        raise ValueError(f"record {index}: numeric-text-v1 requires one complete ASCII numeric answer")
    if kind == "digits":
        return text
    # Bound conversion work before calling Python's integer parser.
    if len(digits) > 1000:
        raise ValueError(f"record {index}: numeric-text-v1 arithmetic answer exceeds 1000 digits")
    return int(text)
