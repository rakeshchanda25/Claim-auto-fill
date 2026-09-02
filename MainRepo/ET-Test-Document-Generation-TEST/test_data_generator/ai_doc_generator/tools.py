"""The tools the document-generation agent calls.

Everything a run needs is staged server-side in a RunContext rather than passed
through the model. That is deliberate: a prompt is text the model *interprets*,
not code it *executes*, so a large dict embedded in a prompt can be dropped,
truncated, or silently not passed back. Staging removes the model from the path
entirely - the tools read the context directly. Tool arguments still exist for
the same values, but only as an additive safety net: anything the model passes
merges on top of the staged values, and omitting them changes nothing.
"""

import functools
import logging
import random
import threading
import time
from dataclasses import dataclass, field

from faker import Faker

from renderers import render_html_to_pdf
from renderers.docx_parser import extract_docx_layout
from renderers.synthetic_data import _parse_anchor_date, build_synthetic_data, resolve_doc_type

from .registry import PACKET_REGISTRY

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-run state
# ---------------------------------------------------------------------------

@dataclass
class RunContext:
    """Everything staged for the duration of one generation run.

    Held as a single object so `begin_run` can guarantee a clean slate by
    replacing it, rather than by remembering to reset each field individually.
    """

    # Inputs, staged before the agent starts.
    reference_bytes: bytes | None = None
    custom_fields: dict = field(default_factory=dict)
    anchor_date: str | None = None

    # Outputs, staged by the tools as the run progresses.
    doc_data: dict | None = None            # generate/recreate: the document's fields
    packet_plan: list[dict] | None = None   # build_packet: components awaiting render
    artifact: tuple[bytes, str] | None = None   # rendered single document: (bytes, kind)
    packet: list[dict] | None = None        # rendered packet components


# Serialises runs against the shared context above. The agent is a single
# process-wide instance, so two concurrent requests would otherwise interleave
# their staged data.
run_lock = threading.Lock()

_ctx = RunContext()


def begin_run(reference_bytes: bytes | None = None, custom_fields: dict | None = None,
              anchor_date: str | None = None) -> None:
    global _ctx
    _ctx = RunContext(
        reference_bytes=reference_bytes,
        custom_fields=custom_fields or {},
        anchor_date=anchor_date,
    )


def end_run() -> None:
    global _ctx
    _ctx = RunContext()


def current_run() -> RunContext:
    return _ctx


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _summarize(value, maxlen: int = 120) -> str:
    """Log-safe representation - never dumps document bytes or a whole dict."""
    if isinstance(value, bytes):
        return f"<bytes: {len(value)}>"
    if isinstance(value, dict):
        return f"<dict: {len(value)} keys>"
    if isinstance(value, (list, tuple)):
        return f"<{type(value).__name__}: {len(value)} items>"
    r = repr(value)
    return r if len(r) <= maxlen else r[:maxlen] + f"...<+{len(r) - maxlen} chars>"


def _logged(func):
    """Logs each tool's call, result and full traceback on failure.

    This is the only place a real traceback survives: Andromeda's
    ToolErrorHandlerMiddleware catches every tool exception and reduces it to
    "Tool error: (exc)" before it reaches the model or the console - which for
    an IndexError is "list index out of range" with no file or line.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        parts = [_summarize(a) for a in args] + [f"{k}={_summarize(v)}" for k, v in kwargs.items()]
        logger.info(f"tool -> {func.__name__}({', '.join(parts)})")
        t0 = time.monotonic()
        try:
            result = func(*args, **kwargs)
        except Exception:
            logger.exception(f"tool {func.__name__!r} failed after {time.monotonic() - t0:.2f}s")
            raise
        logger.info(f"tool <- {func.__name__} ({time.monotonic() - t0:.2f}s) = {_summarize(result)}")
        return result
    return wrapper


# ---------------------------------------------------------------------------
# Applying claim facts to a document
# ---------------------------------------------------------------------------

def _overlay(dst: dict, src: dict, path: str = "", unmapped: list | None = None) -> list:
    """Merge `src` into `dst` in place, nested dicts key-by-key.

    Returns the dotted paths that could not be applied - either the key does not
    exist on this document type, or a structured field was handed a scalar.
    Those are rejected rather than applied, since replacing a nested dict with a
    string breaks every template line that reads a sub-field.
    """
    if unmapped is None:
        unmapped = []
    for key, value in (src or {}).items():
        full = f"{path}.{key}" if path else key
        if key not in dst:
            unmapped.append(full)
        elif isinstance(dst[key], dict):
            if isinstance(value, dict):
                _overlay(dst[key], value, full, unmapped)
            else:
                unmapped.append(full)
        else:
            dst[key] = value
    return unmapped


# Documents describing ONE claim name the same thing differently: a medical
# form's patient_name is a complaint's plaintiff_name; a police report's
# incident_date is an auto report's accident_date is a property notice's
# loss_date. A plain key-match overlay only reaches whichever document happens
# to use the matching name, which is why a packet's own documents could
# disagree with each other - even with no external claim data involved.
#
# So syncing works by CONCEPT, not by field name. Keep this in step with
# renderers/synthetic_data.py: a field missing here silently keeps its
# generated value while the rest of the packet moves.
_ALIASES = {
    "claimant": ("patient_name", "insured_name", "claimant_name", "plaintiff_name",
                 "driver_name", "subscriber_name", "benefit_patient_name",
                 "customer_name", "contact_person"),
    "location": ("location", "accident_location", "loss_location"),
    "incident_date": ("incident_date", "accident_date", "loss_date"),
    "dob": ("dob", "insured_dob"),
    "member_id": ("insurance_id", "insured_id"),
    "group_no": ("group_number", "insurance_group_no"),
    "physician": ("physician_name", "attending_physician_name",
                  "operating_physician_name", "prescriber_name"),
    "facility": ("hospital", "pay_to_name", "billing_provider_name"),
    "insurer": ("insurer_name", "payer_name"),
    "admission_date": ("date_of_admission", "admission_date"),
    "discharge_date": ("date_of_discharge", "discharge_date"),
}

# provider_name cannot live in a group above: on an EOB it is the treating
# clinician ("Dr. Mary Carlson"), on a UB-04 it is the facility ("Memorial
# Health System"). Syncing it blindly would put a doctor's name in a hospital
# field. These map one field to one concept, for one document type only.
_PER_DOC_ALIASES = {
    "eob-explanation": {"provider_name": "physician"},
    "ub-04": {"provider_name": "facility"},
}

# Identical field names that must agree across a packet. Concept aliases above
# handle the rest.
_PACKET_SHARED_FIELDS = (
    "gender", "address", "phone", "mrn", "npi", "specialty", "dea",
    "claim_number", "policy_number",
    "dos", "dos_from", "dos_to", "service_date",
)

# Claim values that are dates. Guidewire returns ISO timestamps
# ("2026-08-01T04:01:00.000Z"); these documents render MM/DD/YYYY, so applying
# the raw value would print a timestamp on the page.
_CLAIM_DATE_FIELDS = ("loss_date", "reported_date", "policy_effective_date",
                      "policy_expiration_date")


def _alias_fields(doc_type: str | None, concept: str) -> list[str]:
    """Every field name this document uses for `concept`. A name that is not a
    registered concept stands for itself, so _PACKET_SHARED_FIELDS (plain field
    names that must simply match) flows through the same path."""
    fields = list(_ALIASES.get(concept, ()))
    for field_name, mapped in _PER_DOC_ALIASES.get(doc_type or "", {}).items():
        if mapped == concept:
            fields.append(field_name)
    return fields or [concept]


def _apply_concept(data: dict, doc_type: str | None, concept: str, value) -> None:
    """Writes one concept's value onto every field this document uses for it."""
    if value is None:
        return
    for f in _alias_fields(doc_type, concept):
        if f in data:
            data[f] = value
    if concept != "claimant":
        return
    # police-report: parties_involved[0] is always the reporting/non-at-fault
    # party. The other party stays independently generated - claim data
    # describes the insured, not whoever they collided with.
    parties = data.get("parties_involved")
    if isinstance(parties, list) and parties:
        parties[0]["name"] = value
    # auto-accident-report's "STATE EMPLOYEE" block - the insured driver, as
    # distinct from vehicle2's driver. Nested, so the loop above never saw it.
    employee = data.get("employee")
    if isinstance(employee, dict):
        employee["name"] = value


def _read_concept(data: dict, doc_type: str | None, concept: str):
    """The value this document already holds for a concept, if any."""
    for f in _alias_fields(doc_type, concept):
        if data.get(f):
            return data[f]
    return None


def _normalize_claim_dates(fields: dict) -> dict:
    """Reformats claim date values to the MM/DD/YYYY these documents render."""
    out = dict(fields)
    for key in _CLAIM_DATE_FIELDS:
        parsed = _parse_anchor_date(out.get(key))
        if parsed:
            out[key] = parsed.strftime("%m/%d/%Y")
    return out


def _apply_claim_facts(data: dict, doc_type: str, custom_fields: dict) -> None:
    """Applies claim facts to one document: a literal field overlay plus concept
    aliasing, so a value lands on whatever this document type calls it.
    Deliberately narrow - only fields the document genuinely has are touched,
    and no summary prose is added anywhere.
    """
    if not custom_fields:
        return
    fields = _normalize_claim_dates(custom_fields)
    _overlay(data, fields)
    _apply_concept(data, doc_type, "claimant", fields.get("insured_name"))
    _apply_concept(data, doc_type, "location", fields.get("loss_location"))
    _apply_concept(data, doc_type, "incident_date", fields.get("loss_date"))


# Which claim-document categories are worth attaching to which document type.
# In generate/recreate mode the model reads the same material as free text and
# judges relevance itself; a packet has no per-component model step, so that
# judgment is made here instead. Types absent from this map get nothing - a
# certificate of insurance has no narrative section to put an excerpt in.
_RELEVANT_EXCERPTS = {
    "police-report": ("police report", "accident report", "tow"),
    "auto-accident-report": ("police report", "accident report", "tow"),
    "medical-record": ("injury", "medical", "bodily injury"),
    "medical-bill": ("injury", "medical", "bodily injury", "payment", "settlement"),
    "discharge-summary": ("injury", "medical", "bodily injury"),
    "property-loss-notice": ("estimate", "appraisal", "photo", "inspection",
                             "total loss", "salvage", "title"),
    "eob-explanation": ("payment", "settlement", "injury", "medical"),
    "demand-letter": ("police report", "accident report", "injury", "medical"),
    "litigation-document": ("police report", "accident report", "injury", "medical"),
    "ub-04": ("injury", "medical", "payment"),
    "pharmacy-invoice": ("injury", "medical"),
}


def _sync_component(data: dict, doc_type: str, shared: dict, custom_fields: dict,
                    claim_description: str | None, excerpts: list | None) -> None:
    """Makes one packet component agree with the rest of the packet.

    `shared` is concept -> value (see _ALIASES). Values come from the claim when
    there is one and otherwise from whichever component first produced them, so
    a packet with no external data still agrees with itself.
    """
    _apply_claim_facts(data, doc_type, custom_fields)
    for concept, value in shared.items():
        _apply_concept(data, doc_type, concept, value)

    # scenario_facts is the one place every document type already has for extra
    # detail. Types without it get nothing rather than growing a new section.
    if not isinstance(data.get("scenario_facts"), list):
        return
    extra = []
    if claim_description:
        extra.append({"label": "Claim Description", "value": claim_description})
    for ex in excerpts or []:
        if any(kw in ex.get("category", "") for kw in _RELEVANT_EXCERPTS.get(doc_type, ())):
            extra.append({
                "label": f"Claim File Excerpt ({ex.get('source', 'attached document')})",
                "value": ex.get("text", ""),
            })
    if extra:
        data["scenario_facts"] = data["scenario_facts"] + extra
        if not data.get("scenario_facts_title"):
            data["scenario_facts_title"] = "Claim File Details"


def _seed_shared(shared: dict, data: dict, doc_type: str) -> None:
    """Records any concept this component supplies that the packet has not
    pinned down yet, so a later component inherits it.

    Accumulating across components (rather than reading only the first) matters
    because no single document carries every concept: the first component may
    have no physician, and the third one would otherwise invent its own.
    """
    for concept in _ALIASES:
        if not shared.get(concept):
            value = _read_concept(data, doc_type, concept)
            if value:
                shared[concept] = value
    for field_name in _PACKET_SHARED_FIELDS:
        if not shared.get(field_name) and data.get(field_name):
            shared[field_name] = data[field_name]


def _merged_fields(custom_fields: dict | None) -> dict:
    """Staged claim facts, with anything the model passed merged on top."""
    return {**current_run().custom_fields, **(custom_fields or {})}


def _stage_doc_data(data: dict, doc_type: str, scenario: str) -> dict:
    current_run().doc_data = data
    return {
        "status": "staged",
        "doc_type": doc_type,
        "scenario": scenario,
        "field_count": len(data),
        "fields": sorted(k for k in data if not k.startswith("_")),
    }


def _require_doc_data() -> dict:
    data = current_run().doc_data
    if data is None:
        raise ValueError(
            "No document data staged yet - call generate_synthetic_data or "
            "recreate_document_data before rendering."
        )
    return data


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@_logged
def generate_synthetic_data(doc_type: str, scenario: str = "general", seed: int = None,
                            anchor_date: str = None, custom_fields: dict = None) -> dict:
    """Generate and stage synthetic insurance claim data for one document.

    Live claim facts and the loss date are already staged server-side and applied
    automatically. Passing `custom_fields`/`anchor_date` is optional: whatever you
    pass merges on top of the staged values and overrides them on conflict. Never
    re-apply the same values afterwards with revise_document_data.

    Returns field names only - the data is held server-side for
    render_document_to_pdf.
    """
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)
    data = build_synthetic_data(doc_type, scenario, anchor_date=anchor_date or current_run().anchor_date)
    _apply_claim_facts(data, resolve_doc_type(doc_type), _merged_fields(custom_fields))
    return _stage_doc_data(data, doc_type, scenario)


@_logged
def recreate_document_data(doc_type: str, scenario: str, carried_values: dict,
                           anchor_date: str = None, custom_fields: dict = None) -> dict:
    """Generate fresh data for `scenario` while preserving selected values read
    off the uploaded reference document.

    Pass only identity and identifier fields in `carried_values` - names, DOB,
    policy/claim/member/record numbers, provider, addresses. Scenario-driven
    fields stay newly generated. Nested dicts merge key-by-key.

    Claim facts are applied first and `carried_values` second, so the uploaded
    document's own values win on conflict - that is what "recreate" means: the
    same people as the upload, not a different claim's.

    Returns a field summary plus carried and unmapped key counts.
    """
    resolved = resolve_doc_type(doc_type)
    data = build_synthetic_data(resolved, scenario,
                                anchor_date=anchor_date or current_run().anchor_date)
    _apply_claim_facts(data, resolved, _merged_fields(custom_fields))
    unmapped = _overlay(data, carried_values or {})

    # Counted by top-level key: `unmapped` may hold nested paths ("address.street"),
    # which do not invalidate the parent key that did apply.
    carried_ok = sum(1 for k in (carried_values or {}) if k not in unmapped)
    logger.info(f"recreate {doc_type}/{scenario!r}: carried {carried_ok}/{len(carried_values or {})} value(s)")
    if unmapped:
        logger.warning(f"recreate: {len(unmapped)} unmapped key(s): {unmapped}")

    summary = _stage_doc_data(data, doc_type, scenario)
    summary["carried_keys"] = carried_ok
    summary["unmapped_keys"] = unmapped
    return summary


@_logged
def revise_document_data(changes: dict) -> dict:
    """Update specific fields on the staged document; nested dicts merge.
    Returns the changed and unmapped field names."""
    unmapped = _overlay(_require_doc_data(), changes)
    if unmapped:
        logger.warning(f"revise: {len(unmapped)} unmapped key(s): {unmapped}")
    return {
        "status": "revised",
        "changed": [k for k in (changes or {}) if k not in unmapped],
        "unmapped_keys": unmapped,
    }


# Minimum fields each document type needs before it is worth rendering. Keyed by
# resolved doc type; see renderers/synthetic_data.py's _DOC_TYPE_ALIASES.
_REQUIRED_FIELDS = {
    "medical-record": ["patient_name", "dob", "mrn", "dos", "diagnosis_codes", "physician_name"],
    "medical-bill": ["patient_name", "account_number", "service_date", "line_items", "total_amount"],
    "discharge-summary": ["patient_name", "date_of_admission", "date_of_discharge", "diagnosis",
                          "reason", "clinician_signature"],
    "acord-25": ["insured_name", "policy_number", "effective_date", "expiration_date", "insurer_name"],
    "cms-1500": ["patient_name", "insured_id", "dos_from", "diagnosis_codes", "procedure_codes",
                 "provider_npi"],
    "ub-04": ["patient_name", "admission_date", "discharge_date", "revenue_codes", "total_charges"],
    "eob-explanation": ["subscriber_name", "claim_number", "provider_name", "claims", "totals"],
    "litigation-document": ["plaintiff_name", "defendant_name", "case_number", "court_name",
                            "incident_date"],
    "demand-letter": ["claimant_name", "insurer_name", "claim_number", "incident_date", "demand_amount"],
    "police-report": ["incident_number", "incident_date", "location", "officer_name", "badge_number"],
    "pharmacy-invoice": ["invoice_number", "invoice_date", "company_gstin", "customer_name", "items",
                         "grand_total"],
    "property-loss-notice": ["insured_name", "policy_number", "loss_date", "loss_location", "cause_of_loss"],
    "auto-accident-report": ["accident_date", "employee", "vehicle1", "vehicle2"],
}


@_logged
def validate_document_structure(doc_type: str) -> dict:
    """Check the staged document has every field its type requires."""
    data = _require_doc_data()
    resolved = resolve_doc_type(doc_type)
    if resolved not in _REQUIRED_FIELDS:
        return {
            "valid": False,
            "missing_fields": [],
            "doc_type": doc_type,
            "error": (
                f"Unknown doc_type {doc_type!r}. Known types: {sorted(_REQUIRED_FIELDS)}. "
                f"If this is a new variant template, add it to _DOC_TYPE_ALIASES in "
                f"renderers/synthetic_data.py."
            ),
        }
    missing = [f for f in _REQUIRED_FIELDS[resolved] if data.get(f) is None]
    return {"valid": not missing, "missing_fields": missing, "doc_type": doc_type}


@_logged
def render_document_to_pdf(template_name: str) -> dict:
    """Render the staged document to a PDF. The result is staged automatically -
    it never passes through your output."""
    pdf_bytes = render_html_to_pdf(template_name, _require_doc_data())
    current_run().artifact = (pdf_bytes, "pdf")
    return {"status": "staged", "kind": "pdf", "size_bytes": len(pdf_bytes)}


def analyze_reference_document(file_bytes: bytes, file_type: str) -> dict:
    """Detect a reference document's structure. Supports PDF and DOCX."""
    file_type = file_type.lower().lstrip(".")

    if file_type in ("docx", "doc"):
        return extract_docx_layout(file_bytes)

    if file_type != "pdf":
        return {"file_type": file_type, "note": "image analysis requires a vision-capable model"}

    import pymupdf

    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    pages = []
    for page_num in range(min(3, len(doc))):
        page = doc[page_num]
        blocks = []
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:  # 0 = text; skip images
                continue
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if text:
                        blocks.append({
                            "text": text,
                            "font_size": round(span.get("size", 10), 1),
                            "bold": bool(span.get("flags", 0) & 2 ** 4),
                            "bbox": [round(v, 1) for v in span.get("bbox", [])],
                        })
        pages.append({"page": page_num + 1, "text": page.get_text().strip(), "text_blocks": blocks[:60]})
    return {"file_type": "pdf", "pages": pages}


@_logged
def analyze_uploaded_reference(file_type: str) -> dict:
    """Analyze the uploaded reference document. Its bytes are supplied
    automatically - do not attempt to pass them."""
    reference = current_run().reference_bytes
    if reference is None:
        raise ValueError(
            "No reference document is staged for this request. Recreate mode needs "
            "an uploaded file - there is nothing to analyze."
        )
    return analyze_reference_document(reference, file_type)


@_logged
def build_packet(packet_name: str, scenario: str = "general", seed: int = None,
                 custom_fields: dict = None) -> dict:
    """Plan every component of a named packet, giving them one shared claimant,
    claim number and incident date.

    Claim facts are applied to every component here - a packet has no
    per-component step where they could otherwise land. The loss date, if there
    is one, anchors every component's generated dates.
    """
    spec = PACKET_REGISTRY.get(packet_name)
    if not spec:
        raise ValueError(f"Unknown packet: {packet_name}. Available: {list(PACKET_REGISTRY)}")

    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)

    fields = _merged_fields(custom_fields)
    # Narrative material rides in on reserved keys so it does not get overlaid
    # onto a document field of the same name.
    claim_description = fields.pop("_claim_description", None)
    excerpts = fields.pop("_document_excerpts", None)
    anchor_date = fields.get("loss_date") or current_run().anchor_date

    # Claim values pin their concepts up front, so they win over anything a
    # component generates. Everything the claim does not cover is filled in by
    # the first component that produces it (see _seed_shared).
    claim_fields = _normalize_claim_dates(fields)
    shared: dict = {}
    for concept, key in (("claimant", "insured_name"), ("location", "loss_location"),
                         ("incident_date", "loss_date"), ("insurer", "insurer_name")):
        if claim_fields.get(key):
            shared[concept] = claim_fields[key]

    components = sorted(spec["components"], key=lambda c: c["order"])
    plan = []
    for comp in components:
        doc_type = comp["doc_type"]
        data = build_synthetic_data(doc_type, scenario, anchor_date=anchor_date)
        # Sync first so this component adopts what the packet already agreed,
        # then seed so whatever it uniquely contributes is available to the rest.
        _sync_component(data, doc_type, shared, fields, claim_description, excerpts)
        _seed_shared(shared, data, doc_type)
        plan.append({
            "label": comp["label"],
            "doc_type": doc_type,
            "template_name": doc_type.replace("-", "_"),
            "data": data,
        })

    # A concept only discovered on a later component (a physician the first
    # document does not name) has to be pushed back over the earlier ones, or
    # the packet still disagrees with itself.
    for entry in plan:
        _sync_component(entry["data"], entry["doc_type"], shared, fields,
                        claim_description, excerpts=None)

    current_run().packet_plan = plan
    logger.info(
        f"packet {packet_name}/{scenario!r}: {len(plan)} component(s) sharing "
        f"claimant={shared.get('claimant')!r} claim={shared.get('claim_number')!r} "
        f"incident={shared.get('incident_date')!r}"
    )
    return {
        "packet": packet_name,
        "scenario": scenario,
        "component_count": len(plan),
        "components": [{k: c[k] for k in ("label", "doc_type", "template_name")} for c in plan],
        "shared_identity": {
            "name": shared.get("claimant"),
            "location": shared.get("location"),
            "incident_date": shared.get("incident_date"),
            "claim_number": shared.get("claim_number"),
        },
    }


@_logged
def render_packet() -> dict:
    """Render every component build_packet planned, in order. One call does the
    whole packet - there is no per-component step."""
    ctx = current_run()
    if not ctx.packet_plan:
        raise ValueError("No packet planned yet - call build_packet first.")

    ctx.packet = []
    for comp in ctx.packet_plan:
        pdf_bytes = render_html_to_pdf(comp["template_name"], comp["data"])
        ctx.packet.append({"label": comp["label"], "kind": "pdf", "bytes": pdf_bytes})
        logger.info(f"packet: rendered {comp['label']!r} ({len(pdf_bytes)} bytes)")

    return {
        "status": "rendered",
        "components": [{"label": c["label"], "size_bytes": len(c["bytes"])} for c in ctx.packet],
    }


_AGENT_FUNCTIONS = (
    generate_synthetic_data,
    recreate_document_data,
    revise_document_data,
    validate_document_structure,
    render_document_to_pdf,
    analyze_uploaded_reference,
    build_packet,
    render_packet,
)


def agent_tools() -> list:
    """The functions above wrapped as Andromeda tools.

    Wrapping happens here rather than as a decorator on each definition so the
    functions stay plain callables. Andromeda's @tool returns a StructuredTool,
    which is not callable - decorating in place would make them unusable from
    Python and untestable, for no gain, since only the agent needs the wrapper.
    """
    from andromeda.tools import tool

    return [tool(f) for f in _AGENT_FUNCTIONS]
