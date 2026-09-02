import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

_MIN_SNIPPET_CHARS = 40

_CLAIM_PATTERNS = (
    re.compile(r"\bcc:[A-Za-z0-9_-]+\b"),
    re.compile(r"claim\s*(?:id|number|#)?\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9:_\-]{4,})", re.IGNORECASE),
    re.compile(r"\b\d{3}-\d{2}-\d{6}\b"),
)


def extract_claim_id(text: str) -> Optional[str]:
    for pattern in _CLAIM_PATTERNS:
        if m := pattern.search(text or ""):
            return (m.group(1) if m.groups() else m.group(0)).strip().rstrip(".,;")
    return None


def _section(value) -> dict:
    if not isinstance(value, dict) or value.get("error"):
        return {}
    return value


@dataclass
class ClaimContext:

    details: dict = field(default_factory=dict)
    policy: dict = field(default_factory=dict)
    contacts: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    excerpts: list[dict] = field(default_factory=list)

    def contact_name(self, role: str) -> Optional[str]:
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
        return " ".join(self.notes) if self.notes else None


def fetch_claim_context(client, claim_number: str) -> ClaimContext:
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
    return context


def _document_excerpts(documents: dict) -> list[dict]:
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
        "producer_name": claim.contact_name("Agent"),
    }
    return {k: v for k, v in fields.items() if v not in (None, "")}


def claim_narrative(claim: ClaimContext) -> str:
    lines = []
    if claim.description:
        lines.append(f"Adjuster's claim description: {claim.description}")
    if claim.excerpts:
        lines.append("Excerpts from documents already attached to this claim:")
        lines += ['- [{}] {}: "{}"'.format(e["category"], e["source"], e["text"]) for e in claim.excerpts]
    return "\n".join(lines)
