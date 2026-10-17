"""Deterministic identities for sets of evaluated sample IDs."""

import hashlib
import json


def sample_fingerprint(sample_ids):
    """Hash a nonempty set of unique string IDs, independent of input order.

    The caller must provide stable IDs from the pinned dataset revision.
    This verifies reported identities, not the contents of those samples.
    """
    if not isinstance(sample_ids, list) or not sample_ids:
        raise ValueError("sample_ids must be a nonempty list")
    if any(not isinstance(item, str) or not item.strip() for item in sample_ids):
        raise ValueError("sample_ids must contain nonempty strings")
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError("sample_ids must be unique")
    # JSON preserves ID boundaries; joining with a delimiter would be ambiguous.
    payload = json.dumps(sorted(sample_ids), ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("ascii")).hexdigest()
