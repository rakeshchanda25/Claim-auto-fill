"""Guidewire ClaimCenter REST client.

Scoped to what document generation actually needs: the claim, its policy, its
contacts, the adjuster's notes, and text excerpts from PDFs already attached to
the claim. Everything is returned in the shape the caller consumes, so nothing
is built only to be thrown away.
"""

import base64
import io
import json
import logging
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


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


def _nested(value: Any, *keys: str) -> Any:
    """Guidewire returns many fields as {id, displayName, code, ...} objects.
    Pulls the first present key, or passes a plain value straight through."""
    if not isinstance(value, dict):
        return value
    for key in keys:
        if value.get(key):
            return value[key]
    return None


class GuidewireClient:
    """Read-only HTTP client for ClaimCenter."""

    # Categories searched for in the claim's attached PDFs. Each is an
    # alternation of related terms; the whole set becomes one similarity query.
    DOCUMENT_QUERIES = (
        "estimate|appraisal|repair estimate",
        "photo|photos|image|inspection",
        "police report|accident report",
        "tow|towing|storage",
        "rental",
        "injury|medical|bodily injury",
        "total loss|salvage|title",
        "payment|settlement|release",
    )

    def __init__(self, base_url: str, username: str, password: str, timeout_seconds: int = 60):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._auth = f"Basic {credentials}"

    # -- HTTP ---------------------------------------------------------------

    def _get(self, path: str) -> Any:
        """GET a JSON endpoint. Network and HTTP errors are returned as an
        {"error": ...} dict rather than raised, so one failing sub-request
        degrades that section instead of failing the whole claim lookup."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", self._auth)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                if "application/json" in (resp.headers.get("Content-Type") or "").lower():
                    return json.loads(raw.decode("utf-8"))
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            logger.warning(f"guidewire {url} -> HTTP {exc.code}")
            return {"error": "http_error", "url": url, "status": exc.code}
        except Exception as exc:
            logger.warning(f"guidewire {url} -> {exc}")
            return {"error": "request_failed", "url": url, "detail": str(exc)}

    @staticmethod
    def _records(response: Any) -> list[dict]:
        """The `data` list of a collection response, or empty on any error."""
        if not isinstance(response, dict) or response.get("error"):
            return []
        data = response.get("data")
        return data if isinstance(data, list) else []

    @staticmethod
    def _attributes(response: Any) -> dict:
        """The `data.attributes` object of a single-record response."""
        if not isinstance(response, dict) or response.get("error"):
            return {}
        data = response.get("data")
        return data.get("attributes", {}) if isinstance(data, dict) else {}

    # -- Claim lookup -------------------------------------------------------

    def resolve_claim_id(self, claim_number: str) -> str:
        """Claim numbers ("000-00-053109") and public IDs ("cc:123") both reach
        us from free-text input; the REST API only accepts the latter."""
        if str(claim_number).startswith("cc:"):
            return claim_number
        safe = urllib.parse.quote(str(claim_number), safe="%")
        records = self._records(self._get(f"rest/claim/v1/claims?filter=claimNumber:eq:{safe}"))
        if records:
            claim_id = records[0].get("attributes", {}).get("id") or records[0].get("id")
            if claim_id:
                logger.info(f"claim {claim_number!r} resolved to {claim_id!r}")
                return claim_id
        logger.warning(f"could not resolve claim {claim_number!r}; using it as-is")
        return claim_number

    def fetch_claim_context(self, claim_number: str) -> ClaimContext:
        """Loads everything one claim contributes, fetching the independent
        sections concurrently - they were five serial round-trips before."""
        claim_id = self.resolve_claim_id(claim_number)
        safe = urllib.parse.quote(str(claim_id), safe="%")

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {
                "details": pool.submit(self._claim_details, safe),
                "policy": pool.submit(self._policy, safe),
                "contacts": pool.submit(self._contacts, safe),
                "notes": pool.submit(self._notes, safe),
                "excerpts": pool.submit(self._document_excerpts, claim_id, safe),
            }
            sections = {name: f.result() for name, f in futures.items()}

        context = ClaimContext(**sections)
        logger.info(
            f"claim {claim_id}: {len(context.details)} detail field(s), "
            f"{len(context.notes)} note(s), {len(context.excerpts)} excerpt(s)"
        )
        return context

    def _claim_details(self, safe_claim: str) -> dict:
        attrs = self._attributes(self._get(f"rest/claim/v1/claims/{safe_claim}"))
        return {
            "claim_number": attrs.get("claimNumber"),
            "policy_number": attrs.get("policyNumber"),
            "status": _nested(attrs.get("state"), "displayName", "name", "code"),
            "loss_type": _nested(attrs.get("lossType"), "displayName", "name", "code"),
            "loss_cause": _nested(attrs.get("lossCause"), "displayName", "name", "code"),
            "loss_date": attrs.get("lossDate"),
            "reported_date": attrs.get("reportedDate"),
            "insured": _nested(attrs.get("insured"), "displayName", "name"),
            "reporter": _nested(attrs.get("reporter"), "displayName", "name"),
            "main_contact": _nested(attrs.get("mainContact"), "displayName", "name"),
            "assigned_adjuster": _nested(attrs.get("assignedUser"), "displayName", "name"),
            "jurisdiction": _nested(attrs.get("jurisdiction"), "displayName", "name", "code"),
            "line_of_business": _nested(attrs.get("lobCode"), "displayName", "name", "code"),
            "how_reported": _nested(attrs.get("howReported"), "displayName", "name", "code"),
            "loss_location": _nested(attrs.get("lossLocation"), "displayName", "name"),
            "policy_address": self._addresses(attrs.get("policyAddresses")),
        }

    @staticmethod
    def _addresses(value: Any) -> Optional[str]:
        if isinstance(value, list):
            names = [a.get("displayName") for a in value if isinstance(a, dict) and a.get("displayName")]
            return ", ".join(names) or None
        return _nested(value, "displayName")

    def _policy(self, safe_claim: str) -> dict:
        attrs = self._attributes(self._get(f"rest/claim/v1/claims/{safe_claim}/policy"))
        return {
            "policy_number": attrs.get("policyNumber"),
            "policy_type": _nested(attrs.get("policyType"), "name", "code"),
            "policy_effective_date": attrs.get("effectiveDate"),
            "policy_expiration_date": attrs.get("expirationDate"),
            "currency": _nested(attrs.get("currency"), "name", "code"),
        }

    def _contacts(self, safe_claim: str) -> list[dict]:
        contacts = []
        for record in self._records(self._get(f"rest/claim/v1/claims/{safe_claim}/contacts")):
            attrs = record.get("attributes", {})
            contacts.append({
                "display_name": attrs.get("displayName"),
                "first_name": attrs.get("firstName"),
                "last_name": attrs.get("lastName"),
                "roles": [
                    {"role": (r.get("role") or {}).get("name"), "active": r.get("active")}
                    for r in attrs.get("roles") or []
                ],
            })
        return contacts

    def _notes(self, safe_claim: str) -> list[str]:
        return [
            summary
            for record in self._records(self._get(f"rest/claim/v1/claims/{safe_claim}/notes"))
            if (summary := record.get("attributes", {}).get("bodySummary"))
        ]

    # -- Attached-document excerpts -----------------------------------------

    def _document_excerpts(self, claim_id: str, safe_claim: str) -> list[dict]:
        """Text excerpts from PDFs already on the claim, tagged with the query
        category that matched them, so a caller can pick only what is relevant
        to the document it is generating.

        Document text is fetched concurrently: each PDF is a separate download
        plus a text extraction, and claims routinely carry several.
        """
        pdf_ids = [
            (attrs["id"], attrs.get("name") or "an attached document")
            for record in self._records(self._get(f"rest/claim/v1/claims/{safe_claim}/documents"))
            if (attrs := record.get("attributes", {})).get("mimeType") == "application/pdf"
            and attrs.get("id")
        ]
        if not pdf_ids:
            return []

        with ThreadPoolExecutor(max_workers=min(8, len(pdf_ids))) as pool:
            texts = pool.map(lambda d: self._document_text(safe_claim, d[0]), pdf_ids)
        documents = [(name, text) for (_, name), text in zip(pdf_ids, texts) if text]

        excerpts = []
        for pattern in self.DOCUMENT_QUERIES:
            query = re.sub(r"\s*\|\s*", " ", pattern).strip()
            for name, text in documents:
                for snippet in _relevant_chunks(query, text):
                    excerpts.append({"category": pattern, "source": name, "text": snippet})
        return excerpts

    def _document_text(self, safe_claim: str, document_id: str) -> Optional[str]:
        safe_doc = urllib.parse.quote(str(document_id), safe="%")
        response = self._get(f"rest/claim/v1/claims/{safe_claim}/documents/{safe_doc}/content")
        contents = self._attributes(response).get("contents")
        if not contents:
            return None
        try:
            from pypdf import PdfReader
        except ImportError:
            logger.warning("pypdf is not installed - claim document excerpts unavailable")
            return None
        try:
            reader = PdfReader(io.BytesIO(base64.b64decode(contents)))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip() or None
        except Exception as exc:
            logger.warning(f"could not extract text from document {document_id}: {exc}")
            return None


# ---------------------------------------------------------------------------
# Chunk relevance (TF-IDF cosine similarity)
# ---------------------------------------------------------------------------
#
# Splits a document into chunks and returns those most similar to the query.
# Plain substring matching is not enough here: the queries are topics ("injury
# medical bodily injury"), not literal phrases, and a report rarely uses the
# exact wording. TF-IDF weighting keeps a chunk from scoring highly just for
# repeating common words.

_MIN_SNIPPET_CHARS = 40  # below this a "chunk" is a heading or label, not content


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def _chunk(text: str, max_chars: int = 1200) -> list[str]:
    """Paragraphs, with over-long ones split into overlapping 3-line windows so
    a passage spanning the split still matches as a unit."""
    chunks = []
    for paragraph in (p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()):
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
            continue
        lines = paragraph.splitlines()
        for i in range(0, len(lines), 2):  # window 3, step 2 -> one line of overlap
            if chunk := "\n".join(lines[i:i + 3]).strip():
                chunks.append(chunk)
    return chunks


def _tfidf(terms: Counter, doc_frequency: Counter, corpus_size: int) -> dict[str, float]:
    return {
        term: count * (math.log((1 + corpus_size) / (1 + doc_frequency[term])) + 1)
        for term, count in terms.items()
    }


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    shared = set(left) & set(right)
    if not shared:
        return 0.0
    left_norm = math.sqrt(sum(v * v for v in left.values()))
    right_norm = math.sqrt(sum(v * v for v in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return sum(left[t] * right[t] for t in shared) / (left_norm * right_norm)


def _relevant_chunks(query: str, text: str, *, max_matches: int = 8, min_score: float = 0.08) -> list[str]:
    chunks = [c for c in _chunk(text) if len(c) > _MIN_SNIPPET_CHARS]
    if not query or not chunks:
        return []

    chunk_terms = [Counter(_tokenize(c)) for c in chunks]
    doc_frequency = Counter(term for terms in chunk_terms for term in terms)
    query_vector = _tfidf(Counter(_tokenize(query)), doc_frequency, len(chunk_terms))
    if not query_vector:
        return []

    scored = [
        (chunk, score)
        for chunk, terms in zip(chunks, chunk_terms)
        if (score := _cosine(query_vector, _tfidf(terms, doc_frequency, len(chunk_terms)))) >= min_score
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [chunk for chunk, _ in scored[:max_matches]]
