"""Shared postcode parsing helpers."""
import re

_UNIT_RE = re.compile(r"^([A-Z]{1,2}[0-9][A-Z0-9]?)([0-9][A-Z]{2})$")
_AREA_RE = re.compile(r"^[A-Z]{1,2}")


def normalise(raw: str):
    """Return (postcode 'SW1A 2AA', area, district, sector) or None if not a
    valid geographic-looking unit postcode."""
    s = raw.upper().replace(" ", "").strip()
    m = _UNIT_RE.match(s)
    if not m:
        return None
    outward, inward = m.group(1), m.group(2)
    area = _AREA_RE.match(outward).group(0)
    return (f"{outward} {inward}", area, outward, f"{outward} {inward[0]}")
