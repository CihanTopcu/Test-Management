"""Turning stored TestRail text into something this application can serve.

Rich-text fields were imported byte for byte, which means they still point at
``index.php?/attachments/get/<id>``. That URL belongs to TestRail and dies
with the subscription. Rather than rewriting 64k rows of user content at
import time -- irreversible, and it would destroy our ability to diff against
the source -- the substitution happens here, on the way out.

An attachment we could not rescue is marked rather than left as a broken
image, so that a gap in the data is visible instead of silent.
"""
import re

ATTACHMENT_REF = re.compile(r"index\.php\?/attachments/get/([0-9a-zA-Z\-]+)")


def rewrite(value, available: set[str]):
    """Point attachment references at our own route.

    ``available`` holds the ids whose bytes we actually hold.
    """
    if not isinstance(value, str) or "attachments/get/" not in value:
        return value

    def sub(match):
        att_id = match.group(1)
        if att_id in available:
            return f"/api/attachments/{att_id}"
        return f"/api/attachments/{att_id}?missing=1"

    return ATTACHMENT_REF.sub(sub, value)


def rewrite_deep(value, available: set[str]):
    """Apply `rewrite` through dicts and lists, leaving other types alone."""
    if isinstance(value, str):
        return rewrite(value, available)
    if isinstance(value, dict):
        return {k: rewrite_deep(v, available) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite_deep(v, available) for v in value]
    return value


def referenced_ids(value) -> set[str]:
    """Every attachment id mentioned in a value, at any depth."""
    found = set()
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            found.update(ATTACHMENT_REF.findall(item))
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found
