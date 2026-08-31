"""Turns a claim ID/number mentioned in the frontend's free-text "User Input"
box into live claim facts from Guidewire, reusing GuidewireClient (guidewire.py)
- the same client main.py's standalone /claims/{claim_id} endpoint uses. Kept
separate from main.py so app.py can call the client in-process without also
booting main.py's own FastAPI app.

The returned facts are merged into custom_fields by app.py's ai_generate_document,
which already feeds custom_fields to the LLM as "authoritative - use verbatim
wherever it fits a field, only invent the rest" (see prompt_builder.py's
_custom_fields_block) - so any claim field Guidewire doesn't have simply falls
through to that existing Faker-backed generation, with no extra plumbing needed.
"""
import logging
import os
import re
from typing import Optional

from guidewire import GuidewireClient

logger = logging.getLogger(__name__)

GUIDEWIRE_BASE_URL = os.getenv(
    "GUIDEWIRE_BASE_URL",
    "https://cc-dev-gwcpdev.valuemom.zeta1-andromeda.guidewire.net:443",
)
GUIDEWIRE_USERNAME = os.getenv("GUIDEWIRE_USERNAME", "su")
GUIDEWIRE_PASSWORD = os.getenv("GUIDEWIRE_PASSWORD", "gw")
GUIDEWIRE_TIMEOUT = int(os.getenv("GUIDEWIRE_TIMEOUT", "60"))

_client: Optional[GuidewireClient] = None


def _get_client() -> GuidewireClient:
    global _client
    if _client is None:
        _client = GuidewireClient(
            base_url=GUIDEWIRE_BASE_URL,
            username=GUIDEWIRE_USERNAME,
            password=GUIDEWIRE_PASSWORD,
            timeout_seconds=GUIDEWIRE_TIMEOUT,
        )
    return _client


# Checked in this order so an explicit Guidewire public ID or a labelled
# "claim id/number: X" is never shadowed by some other digit run in the text.
# The bare-number pattern matches the shape Guidewire's own claim_number
# field uses (see response.json: "000-00-053109").
_PUBLIC_ID_RE = re.compile(r"\bcc:[A-Za-z0-9_-]+\b")
_LABELLED_RE = re.compile(
    r"claim\s*(?:id|number|#)?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9:_\-]{4,})", re.IGNORECASE
)
_BARE_NUMBER_RE = re.compile(r"\b\d{3}-\d{2}-\d{6}\b")


def extract_claim_id(text: str) -> Optional[str]:
    """Best-effort claim ID/number pulled out of free-form user text."""
    if not text:
        return None
    for pattern in (_PUBLIC_ID_RE, _LABELLED_RE, _BARE_NUMBER_RE):
        m = pattern.search(text)
        if m:
            return (m.group(1) if m.groups() else m.group(0)).strip().rstrip(".,;")
    return None


def fetch_claim_facts(claim_id_or_number: str) -> dict:
    """Fetches the claim from Guidewire and flattens it into claim-level facts.
    Field names are picked to match what these documents' skills already call
    fields by (claim_number, policy_number, loss_date, etc.) so the LLM can map
    them the same way it already maps custom_fields/carried_values - it is not
    a per-doc-type mapping table, because doc types vary too much for a static
    map to stay correct (see prompt_builder.py's _custom_fields_block).

    Raises on failure - the caller (app.py) decides whether that should block
    generation or just log a warning and fall back to pure Faker generation."""
    client = _get_client()
    resolved_id = client.resolve_claim_id_by_number(claim_id_or_number)
    data = client.get_claim_background_context(resolved_id)

    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"Guidewire lookup failed: {data}")

    claim = data.get("claim_details", {}) if isinstance(data, dict) else {}
    policy = data.get("policy_details", {}) if isinstance(data, dict) else {}

    facts = {
        "claim_number": claim.get("claim_number"),
        "policy_number": claim.get("policy_number") or policy.get("policy_number"),
        "claim_status": claim.get("status"),
        "loss_type": claim.get("loss_type"),
        "loss_cause": claim.get("loss_cause"),
        "loss_date": claim.get("loss_date"),
        "insured_name": claim.get("insured"),
        "reporter_name": claim.get("reporter"),
        "adjuster_name": claim.get("assigned_adjuster"),
        "jurisdiction": claim.get("jurisdiction"),
        "line_of_business": claim.get("line_of_business"),
        "loss_location": claim.get("loss_location"),
        "policy_address": claim.get("policy_address"),
        "policy_type": policy.get("policy_type"),
        "policy_effective_date": policy.get("policy_effective_date"),
        "policy_expiration_date": policy.get("policy_expiration_date"),
    }
    return {k: v for k, v in facts.items() if v not in (None, "")}
