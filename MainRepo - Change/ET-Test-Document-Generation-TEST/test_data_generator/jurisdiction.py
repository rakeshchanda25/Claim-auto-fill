import re

from ai_doc_generator.registry import US_STATES, layout_axis

STATE_NAMES = {s["name"].lower(): s["code"] for s in US_STATES}
STATE_CODES = {s["code"] for s in US_STATES}

_TRAILING_CODE = re.compile(r",\s*([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?\s*$")
_ANY_CODE = re.compile(r"\b([A-Z]{2})\b(?:\s+\d{5})?")

_HOSPITAL = re.compile(
    r"\b([A-Z][\w'&.\-]*(?:\s+[A-Z][\w'&.\-]*){0,4}\s+"
    r"(?:Hospital|Medical Center|Health System|Healthcare|Clinic|Memorial|Regional Medical Center))\b"
)


def _from_text(text: str):
    if not text:
        return None
    if match := _TRAILING_CODE.search(text.strip()):
        if match.group(1) in STATE_CODES:
            return match.group(1)
    lowered = text.lower()
    for name, code in STATE_NAMES.items():
        if re.search(r"\b" + re.escape(name) + r"\b", lowered):
            return code
    for match in _ANY_CODE.finditer(text):
        if match.group(1) in STATE_CODES:
            return match.group(1)
    return None


def normalize_state(value):
    if not value:
        return None
    candidate = str(value).strip()
    if candidate.upper() in STATE_CODES:
        return candidate.upper()
    return STATE_NAMES.get(candidate.lower()) or _from_text(candidate)


def resolve_jurisdiction(doc_type: str, explicit=None, claim=None, user_input: str = ""):
    if layout_axis(doc_type) != "state":
        return None
    if code := normalize_state(explicit):
        return code
    if claim is not None:
        for value in (claim.details.get("jurisdiction"),
                      claim.details.get("loss_location"),
                      claim.details.get("policy_address")):
            if code := normalize_state(value):
                return code
    return _from_text(user_input)


def resolve_issuer(doc_type: str, explicit=None, claim=None, user_input: str = ""):
    if layout_axis(doc_type) != "issuer":
        return None
    if explicit:
        return str(explicit).strip()
    sources = []
    if claim is not None:
        sources.append(claim.description or "")
        sources += [e.get("text", "") for e in claim.excerpts]
    sources.append(user_input)
    for text in sources:
        if match := _HOSPITAL.search(text or ""):
            return match.group(1).strip()
    return None
