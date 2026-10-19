"""Versioned, whole-response parsing; never search prose for an answer."""


RESPONSE_POLICIES = ("strict", "numeric-text-v1", "numeric-text-count-v1")


class UnparseableResponse(ValueError):
    """A nonblank text response outside the numeric grammar or conversion bound."""


def numeric_text(prediction, kind, index, *, policy="numeric-text-v1"):
    if prediction is None:
        return None
    if not isinstance(prediction, str):
        raise ValueError(f"record {index}: {policy} prediction must be a string or null")
    text = prediction.strip(" \t\r\n\v\f")
    if not text:
        return None
    digits = text[1:] if kind == "arithmetic" and text[0] in "+-" else text
    if not digits or any(char not in "0123456789" for char in digits):
        raise UnparseableResponse(f"record {index}: {policy} requires one complete ASCII numeric answer")
    if kind == "digits":
        return text
    # Bound conversion work before calling Python's integer parser.
    if len(digits) > 1000:
        raise UnparseableResponse(f"record {index}: {policy} arithmetic answer exceeds 1000 digits")
    return int(text)
