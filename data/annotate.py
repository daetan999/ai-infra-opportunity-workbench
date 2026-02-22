# data/annotate.py
from __future__ import annotations
from typing import Any, Mapping


def annotate_keys(obj: Any, glossary: Mapping[str, str]) -> Any:
    """
    Recursively returns a copy of obj where dict keys that match glossary entries
    are annotated like:
      key -> "key (explanation)"
    Leaves values untouched.
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            k_str = str(k)
            expl = glossary.get(k_str)
            new_key = f"{k_str} ({expl})" if expl else k_str
            out[new_key] = annotate_keys(v, glossary)
        return out

    if isinstance(obj, list):
        return [annotate_keys(x, glossary) for x in obj]

    return obj
