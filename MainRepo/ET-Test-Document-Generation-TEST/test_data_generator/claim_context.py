"""Adapts Guidewire claim data onto the fields these documents use.

guidewire.py is kept exactly as delivered - this module is the whole adaptation
layer, so nothing in the client has to change.

It deliberately does NOT call get_claim_background_context(): that fans out to
twelve endpoints serially, and document generation only needs five of them.
Calling those five directly, in parallel, is one wall-clock round-trip instead
of twelve sequential ones - using only the client's own public methods.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Snippets shorter than this are headings or label fragments, not content.
_MIN_SNIPPET_CHARS = 40

# Checked in this order so an explicit public ID or a labelled "claim id: X" is
# never shadowed by some other run of digits in the text. The bare pattern is
# the shape Guidewire's own claim numbers use, e.g. 000-00-053109.
_CLAIM_PATTERNS = (
    re.compile(r"\bcc:[A-Za-z0-9_-]+\b"),
    re.compile(r"claim\s*(?:id|number|#)?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9:_\-]{4,})", re.IGNORECASE),
    re.compile(r"\b\d{3}-\d{2}-\d{6}\b"),
)


def extract_claim_id(text: str) -> Optional[str]:
    """Best-effort claim ID or number pulled out of free-form user text."""
    for pattern in _CLAIM_PATTERNS:
        if m := pattern.search(text or ""):
            return (m.group(1) if m.groups() else m.group(0)).strip().rstrip(".,;")
    return None


def _section(value) -> dict:
    """The client returns an {"error": ...} dict for a failed sub-request, and
    occasionally a bare string. Either way, treat it as an empty section so one
    failing endpoint degrades that section instead of the whole lookup."""
    if not isinstance(value, dict) or value.get("error"):
        return {}
    return value


@dataclass
class ClaimContext:
    """Everything one claim contributes to a generated document."""

    details: dict = field(default_factory=dict)
    policy: dict = field(default_factory=dict)
    contacts: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)      # adjuster note summaries
    excerpts: list[dict] = field(default_factory=list)  # {category, source, text}

    def contact_name(self, role: str) -> Optional[str]:
        """The first active contact holding `role` - e.g. the producing agent."""
        for contact in self.contacts:
            if any(r.get("role") == role and r.get("active") for r in contact.get("roles", [])):
                name = contact.get("display_name") or " ".join(
                    filter(None, [contact.get("first_name"), contact.get("last_name")])
                )
                if name:
                    return name
        return None

    @property
    def description(self) -> Optional[str]:
        """The adjuster's own account of what happened - the closest thing the
        claim has to a narrative, as opposed to structured field values."""
        return " ".join(self.notes) if self.notes else None


def fetch_claim_context(client, claim_number: str) -> ClaimContext:
    """Loads the five claim sections document generation needs, concurrently."""
    claim_id = client.resolve_claim_id_by_number(claim_number)

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            "details": pool.submit(client.get_claim_details_summary, claim_id),
            "policy": pool.submit(client.get_claim_policy_summary, claim_id),
            "contacts": pool.submit(client.get_claim_contacts_summary, claim_id),
            "notes": pool.submit(client.get_claim_notes_summary, claim_id),
            "documents": pool.submit(client.get_claim_document_searches_summary, claim_id),
        }
        raw = {name: f.result() for name, f in futures.items()}

    context = ClaimContext(
        details=_section(raw["details"]),
        policy=_section(raw["policy"]),
        contacts=_section(raw["contacts"]).get("contacts", []),
        notes=[
            note["body_summary"]
            for note in _section(raw["notes"]).get("notes", [])
            if note.get("body_summary")
        ],
        excerpts=_document_excerpts(_section(raw["documents"])),
    )
    logger.info(
        f"claim {claim_id}: {len(context.details)} detail field(s), "
        f"{len(context.notes)} note(s), {len(context.excerpts)} excerpt(s)"
    )
    return context


def _document_excerpts(documents: dict) -> list[dict]:
    """Flattens the client's per-pattern search results into plain excerpts, each
    tagged with the category that matched it so a consumer can pick only what is
    relevant to the document being generated."""
    excerpts = []
    for result in documents.get("results", []):
        if result.get("no_matches") or not result.get("matches"):
            continue
        category = result.get("pattern", "")
        for match in result["matches"]:
            source = match.get("name") or "an attached document"
            for snippet in match.get("snippets", []):
                if len(snippet) > _MIN_SNIPPET_CHARS:
                    excerpts.append({"category": category, "source": source, "text": snippet})
    return excerpts


def claim_to_fields(claim: ClaimContext) -> dict:
    """Maps a claim onto the field names these documents actually use, so each
    value lands on the field it belongs to. Empty values are dropped so they
    fall through to generated data rather than blanking a field."""
    fields = {
        "claim_number": claim.details.get("claim_number"),
        "policy_number": claim.details.get("policy_number") or claim.policy.get("policy_number"),
        "claim_status": claim.details.get("status"),
        "loss_type": claim.details.get("loss_type"),
        "loss_cause": claim.details.get("loss_cause"),
        "loss_date": claim.details.get("loss_date"),
        "reported_date": claim.details.get("reported_date"),
        "insured_name": claim.details.get("insured"),
        "reporter_name": claim.details.get("reporter"),
        "main_contact": claim.details.get("main_contact"),
        "adjuster_name": claim.details.get("assigned_adjuster"),
        "how_reported": claim.details.get("how_reported"),
        "jurisdiction": claim.details.get("jurisdiction"),
        "line_of_business": claim.details.get("line_of_business"),
        "loss_location": claim.details.get("loss_location"),
        "policy_address": claim.details.get("policy_address"),
        "policy_type": claim.policy.get("policy_type"),
        "policy_currency": claim.policy.get("currency"),
        "policy_effective_date": claim.policy.get("policy_effective_date"),
        "policy_expiration_date": claim.policy.get("policy_expiration_date"),
        # The producing agent - carried only by the role-tagged contacts list.
        # Maps onto ACORD-25's producer_name, the one field it applies to.
        "producer_name": claim.contact_name("Agent"),
    }
    return {k: v for k, v in fields.items() if v not in (None, "")}


def claim_narrative(claim: ClaimContext) -> str:
    """The claim's prose - the adjuster's description and excerpts from attached
    documents - as free text for the model to apply with its own judgment."""
    lines = []
    if claim.description:
        lines.append(f"Adjuster's claim description: {claim.description}")
    if claim.excerpts:
        lines.append("Excerpts from documents already attached to this claim:")
        lines += ['- [{}] {}: "{}"'.format(e["category"], e["source"], e["text"]) for e in claim.excerpts]
    return "\n".join(lines)
