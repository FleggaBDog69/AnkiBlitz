"""Spotting picture note types, so the picture-card list can fill itself in.

A note type counts as a picture type when any of these hold:
  * it is Anki's built-in Image Occlusion (its template uses {{image-occlusion:})
  * its name says so: "Image Occlusion", "occlusion", "Image Q/A", or starts "IO"
  * it has a mask / occluded-image field ("Question Mask", "OccludedImage")

One-by-one cards need no list: they're found on every card by the AnKing
"One by one" field, whatever the note type.
"""

import re

_NAME = re.compile(r"image\s*occlusion|occlusion|image\s*q\s*/\s*a|^io\b", re.I)
_FIELDS = {"question mask", "occludedimage", "occluded image", "image occlusion"}


def is_picture_notetype(nt: dict) -> bool:
    try:
        if _NAME.search(nt.get("name", "")):
            return True
        if any(f.get("name", "").strip().lower() in _FIELDS for f in nt.get("flds", [])):
            return True
        return any("{{image-occlusion:" in (t.get("qfmt", "") + t.get("afmt", ""))
                   for t in nt.get("tmpls", []))
    except Exception:
        return False


def picture_notetypes(col) -> list:
    """Names of the picture note types in this collection, sorted."""
    if col is None:
        return []
    try:
        return sorted(nt["name"] for nt in col.models.all() if is_picture_notetype(nt))
    except Exception:
        return []
