import functools
import logging
import random
import threading
import time
from faker import Faker
try:
    from andromeda.tools import tool
except Exception:
    def tool(func):
        return func

logger = logging.getLogger(__name__)


def _summarize(value, maxlen=120):
    """Short, log-safe representation of a tool argument/return value -
    never dumps a full document's bytes or a huge dict into the log."""
    if isinstance(value, bytes):
        return f"<bytes: {len(value)}>"
    if isinstance(value, dict):
        return f"<dict: {len(value)} keys>"
    if isinstance(value, (list, tuple)):
        return f"<{type(value).__name__}: {len(value)} items>"
    r = repr(value)
    return r if len(r) <= maxlen else r[: maxlen] + f"...<+{len(r) - maxlen} chars>"


def _log_exceptions(func):
    """Logs every tool call's entry (args), success (result), and full
    traceback on failure - this is the only place a real traceback survives:
    andromeda's ToolErrorHandlerMiddleware (andromeda/core/middleware/
    tooling.py) catches every tool exception and reduces it to just
    f"Tool error: ... ({exc})" before it reaches the model or the console -
    for something like IndexError that's literally "list index out of
    range" with zero file/line context."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        parts = [_summarize(a) for a in args] + [f"{k}={_summarize(v)}" for k, v in kwargs.items()]
        logger.info(f"tool call -> {func.__name__}({', '.join(parts)})")
        t0 = time.monotonic()
        try:
            result = func(*args, **kwargs)
        except Exception:
            logger.exception(f"tool '{func.__name__}' raised after {time.monotonic() - t0:.2f}s")
            raise
        logger.info(f"tool ok    <- {func.__name__} ({time.monotonic() - t0:.2f}s) = {_summarize(result)}")
        return result
    return wrapper

from renderers.synthetic_data import build_synthetic_data, resolve_doc_type
from renderers.docx_parser import extract_docx_layout
from renderers import render_html_to_pdf
from .packets import PACKET_REGISTRY


_fake = Faker()

reference_lock = threading.Lock()
_reference_bytes: bytes | None = None


def set_reference_document(data: bytes | None) -> None:
    global _reference_bytes
    _reference_bytes = data


def _require_reference_bytes() -> bytes:
    if _reference_bytes is None:
        raise ValueError(
            "No reference document is staged for this request. The user must upload a "
            "reference file for recreate mode - there is nothing to analyze."
        )
    return _reference_bytes


_staged_artifact_bytes: bytes | None = None
_staged_artifact_kind: str | None = None


def stage_artifact(data: bytes, kind: str) -> dict:
    global _staged_artifact_bytes, _staged_artifact_kind
    _staged_artifact_bytes = data
    _staged_artifact_kind = kind
    return {"status": "staged", "kind": kind, "size_bytes": len(data)}


def get_staged_artifact() -> tuple[bytes | None, str | None]:
    return _staged_artifact_bytes, _staged_artifact_kind


def clear_staged_artifact() -> None:
    global _staged_artifact_bytes, _staged_artifact_kind
    _staged_artifact_bytes = None
    _staged_artifact_kind = None


_staged_packet: list[dict] | None = None


def get_staged_packet() -> list[dict] | None:
    return _staged_packet


def clear_staged_packet() -> None:
    global _staged_packet
    _staged_packet = None

_staged_doc_data: dict | None = None


def clear_staged_doc_data() -> None:
    global _staged_doc_data
    _staged_doc_data = None


def _stage_doc_data(data: dict, doc_type: str, scenario: str) -> dict:
    global _staged_doc_data
    _staged_doc_data = data
    return {
        "status": "staged",
        "doc_type": doc_type,
        "scenario": scenario,
        "field_count": len(data),
        "fields": sorted(k for k in data if not k.startswith("_")),
    }


def _require_staged_doc_data() -> dict:
    if _staged_doc_data is None:
        raise ValueError(
            "No document data has been staged yet - call generate_synthetic_data (or "
            "recreate_document_data) before rendering."
        )
    return _staged_doc_data


def _overlay_values(dst: dict, src: dict, path: str = "", unmapped: list | None = None) -> list:
    """Merge `src` into `dst` in place.

    Nested dicts are merged key-by-key. Returns dotted paths that could not
    be applied because the key is missing or a structured `dst` field received
    a non-dict value. Such values are rejected to avoid replacing structured
    fields with scalars and causing later template failures.
    """
    if unmapped is None:
        unmapped = []
    for key, value in (src or {}).items():
        full = f"{path}.{key}" if path else key
        if key not in dst:
            unmapped.append(full)
        elif isinstance(dst[key], dict):
            if isinstance(value, dict):
                _overlay_values(dst[key], value, full, unmapped)
            else:
                unmapped.append(full)
        else:
            dst[key] = value
    return unmapped




@tool
@_log_exceptions
def generate_synthetic_data(doc_type: str, scenario: str = "general", seed: int = None, anchor_date: str = None) -> dict:
    """Generate and stage synthetic insurance claim data.

    anchor_date: pass this whenever the prompt's USER-SUPPLIED VALUES include
    a 'loss_date' (e.g. from a live Guidewire claim) - it anchors every
    generated date field to that real date instead of an independent random
    one, so report_date/dos/etc. can't land in a different year than the
    real incident. Omit it otherwise.

    Returns field names only; data is stored server-side for
    render_document_to_pdf. Use revise_document_data to change specific
    fields instead of restating the full document."""
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)
    data = build_synthetic_data(doc_type, scenario, anchor_date=anchor_date)
    return _stage_doc_data(data, doc_type, scenario)


@tool
@_log_exceptions
def revise_document_data(changes: dict) -> dict:
    """Update specific fields in the staged document; nested dicts merge.
    Returns changed and unmapped field names."""
    data = _require_staged_doc_data()
    unmapped = _overlay_values(data, changes)
    if unmapped:
        logger.warning(f"revise_document_data: {len(unmapped)} unmapped key(s): {unmapped}")
    return {
        "status": "revised",
        "changed": [k for k in (changes or {}) if k not in unmapped],
        "unmapped_keys": unmapped,
    }


@tool
@_log_exceptions
def render_document_to_pdf(template_name: str, data: dict = None) -> dict:
    """Render staged document data to a PDF using the named Jinja2 template.
    Omit `data` to use the currently staged document. Returns a status object;
    the generated PDF is staged automatically."""
    pdf_bytes = render_html_to_pdf(template_name, data if data is not None else _require_staged_doc_data())
    return stage_artifact(pdf_bytes, "pdf")


def analyze_reference_document(file_bytes: bytes, file_type: str) -> dict:
    """Analyze a reference document and return its detected structure/layout.
    Supports PDF, DOCX/DOC, and common image formats.
    """
    file_type = file_type.lower().lstrip(".")

    if file_type in ("docx", "doc"):
        return extract_docx_layout(file_bytes)

    if file_type == "pdf":
        import pymupdf
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        result = {"pages": [], "file_type": "pdf"}
        for page_num in range(min(3, len(doc))):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            text_blocks = []
            for b in blocks:
                if b.get("type") == 0:
                    for line in b.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text:
                                text_blocks.append({
                                    "text": text,
                                    "font_size": round(span.get("size", 10), 1),
                                    "bold": bool(span.get("flags", 0) & 2**4),
                                    "bbox": [round(v, 1) for v in span.get("bbox", [])],
                                })
            result["pages"].append({
                "page": page_num + 1,
                "text": page.get_text().strip(),
                "text_blocks": text_blocks[:60],
            })
        return result

    return {"file_type": file_type, "note": "image analysis requires vision-capable model"}


@tool
@_log_exceptions
def analyze_uploaded_reference(file_type: str) -> dict:
    """Analyze the uploaded reference document and return its structure/layout.
    File bytes are supplied automatically."""
    return analyze_reference_document(_require_reference_bytes(), file_type)


@tool
@_log_exceptions
def recreate_document_data(doc_type: str, scenario: str, carried_values: dict, anchor_date: str = None) -> dict:
    """Generate fresh data for `scenario`, preserve selected reference values,
    and stage the result. Pass only identity/identifier fields in
    `carried_values`; scenario-specific fields stay newly generated.
    Nested dicts merge key-by-key. Returns a field summary plus carried and
    unmapped key counts.

    anchor_date: pass this whenever a 'loss_date' is available (from
    USER-SUPPLIED VALUES or the reference document) - see
    generate_synthetic_data's anchor_date for why."""

    resolved = resolve_doc_type(doc_type)
    data = build_synthetic_data(resolved, scenario, anchor_date=anchor_date)
    unmapped = _overlay_values(data, carried_values or {})

    carried_ok = sum(1 for k in (carried_values or {}) if k not in unmapped)
    logger.info(
        f"recreate_document_data: doc_type={doc_type} scenario={scenario!r} - "
        f"carried {carried_ok}/{len(carried_values or {})} value(s) onto fresh {scenario!r} data"
    )
    if unmapped:
        logger.warning(f"recreate_document_data: {len(unmapped)} unmapped key(s): {unmapped}")

    summary = _stage_doc_data(data, doc_type, scenario)
    summary["carried_keys"] = carried_ok
    summary["unmapped_keys"] = unmapped
    return summary

_PACKET_SHARED_FIELDS = (
    "patient_name", "dob", "gender", "address", "phone", "mrn",
    "insurance_id", "group_number",
    "physician_name", "npi", "specialty", "dea", "hospital",
    "insurer_name", "claim_number", "policy_number",
    "dos", "dos_from", "dos_to", "service_date",
)

# _PACKET_SHARED_FIELDS only reaches components that literally use that exact
# key name - but the same "who/where/when" concept is named differently per
# doc type: a medical form's patient_name is a demand-letter's claimant_name
# is a litigation-document's plaintiff_name is an auto-accident-report's
# insured_name/driver_name is police-report's parties_involved[0]['name'].
# police-report/auto-accident-report's incident_date isn't "dos" either.
# Without these aliases, a packet's own documents can disagree with EACH
# OTHER about who the claimant is or when the incident happened - not just
# against an external Guidewire claim, but with each other, even on a plain
# Faker-only run with no external data at all (confirmed: litigation-
# document's plaintiff_name was never in _PACKET_SHARED_FIELDS, so a
# litigation-packet's own documents never actually agreed on the plaintiff's
# name before this).
_SHARED_NAME_FIELDS = ("patient_name", "insured_name", "claimant_name", "plaintiff_name", "driver_name")
_SHARED_LOCATION_FIELDS = ("location", "accident_location", "loss_location")
_SHARED_DATE_FIELDS = ("incident_date",)


def _sync_packet_component(data: dict, *, name: str = None, location: str = None,
                            incident_date: str = None, custom_fields: dict = None) -> None:
    """Applies the packet's one shared identity/location/date onto whichever
    of THIS component's own field names actually carry that concept, plus any
    remaining custom_fields that match a literal key (claim_number,
    policy_number, etc. - see _overlay_values). Deliberately narrow: only
    real fields the template actually renders get touched - no extra
    "claim summary" section gets appended anywhere. A prior version of this
    also injected loss-cause/claim-status/adjuster-name/claim-description
    scenario_facts and document excerpts into every component regardless of
    whether that component's template even shows a scenario_facts section -
    that was removed per explicit direction: don't dump claim details into
    every document, and never surface a claim/document summary at all -
    Guidewire data should land only on the fields a document actually needs,
    Faker fills the rest exactly as it always did."""
    if custom_fields:
        _overlay_values(data, custom_fields)
    if name:
        for field in _SHARED_NAME_FIELDS:
            if field in data:
                data[field] = name
        parties = data.get("parties_involved")
        if isinstance(parties, list) and parties:
            # parties_involved[0] is always the non-at-fault/reporting party
            # (see synthetic_data.py's police-report branch: party1 = _party(
            # "Driver 1", at_fault=False, ...)) - the claimant/insured, not
            # the other party, which stays independently generated since
            # Guidewire's claim data describes the insured, not whoever they
            # were in an incident with.
            parties[0]["name"] = name
        employee = data.get("employee")
        if isinstance(employee, dict):
            # auto-accident-report's "STATE EMPLOYEE" section - the reporting/
            # insured driver, as distinct from vehicle2 (the other driver,
            # left untouched). Nested under 'employee', not a flat key, so
            # _SHARED_NAME_FIELDS' plain data[field]=name above never reached
            # it - confirmed the actual bug behind "I can't see the claim
            # owner's name, only the other driver's": the template only ever
            # rendered data.vehicle2.driver_name, never anyone from the
            # employee/claimant side, until employee.name was added to both
            # the data model and the template.
            employee["name"] = name
    if location:
        for field in _SHARED_LOCATION_FIELDS:
            if field in data:
                data[field] = location
    if incident_date:
        for field in _SHARED_DATE_FIELDS:
            if field in data:
                data[field] = incident_date

_staged_packet_plan: list[dict] | None = None


def clear_staged_packet_plan() -> None:
    global _staged_packet_plan
    _staged_packet_plan = None


@tool
@_log_exceptions
def build_packet(packet_name: str, scenario: str = "general", seed: int = None, custom_fields: dict = None) -> dict:
    """Generate all components of a named document packet and return list of {label, template, data} dicts.

    custom_fields: claim-level values (e.g. from a live Guidewire lookup) to
    apply to EVERY component - not just the ones already in
    _PACKET_SHARED_FIELDS. Unlike generate/recreate mode, a packet has no
    per-component step where the caller could otherwise apply these (the
    prompt explicitly tells the model there is none), so this is the only
    place they can land; previously build_packet had no such parameter at
    all, silently dropping any custom_fields the prompt mentioned for packet
    requests. A 'loss_date' key, if present, also anchors every component's
    generated dates (see build_synthetic_data's anchor_date) - fully
    automatic, no per-component step needed for that either."""

    global _staged_packet_plan
    spec = PACKET_REGISTRY.get(packet_name)
    if not spec:
        raise ValueError(f"Unknown packet: {packet_name}. Available: {list(PACKET_REGISTRY.keys())}")

    components = sorted(spec["components"], key=lambda c: c["order"])
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)

    custom_fields = dict(custom_fields or {})
    anchor_date = custom_fields.get("loss_date")

    first = build_synthetic_data(components[0]["doc_type"], scenario, anchor_date=anchor_date)
    # The shared name/location/incident_date come from custom_fields (Guidewire)
    # when present, falling back to whatever the FIRST component itself
    # generated - so a pure-Faker packet (no Guidewire data at all) still gets
    # ONE consistent identity/incident across every document, not just each
    # component agreeing with itself.
    shared_name = custom_fields.get("insured_name") or first.get("patient_name")
    shared_location = custom_fields.get("loss_location") or first.get("location") or first.get("accident_location")
    shared_incident_date = custom_fields.get("incident_date") or first.get("incident_date") or first.get("dos")
    _sync_packet_component(
        first, name=shared_name, location=shared_location,
        incident_date=shared_incident_date, custom_fields=custom_fields,
    )
    shared = {k: first[k] for k in _PACKET_SHARED_FIELDS if k in first}

    plan = []
    for comp in components:
        data = first if comp is components[0] else build_synthetic_data(comp["doc_type"], scenario, anchor_date=anchor_date)
        if data is not first:
            _overlay_values(data, shared)
            _sync_packet_component(
                data, name=shared_name, location=shared_location,
                incident_date=shared_incident_date, custom_fields=custom_fields,
            )
        plan.append({
            "label": comp["label"],
            "doc_type": comp["doc_type"],
            "template_name": comp["doc_type"].replace("-", "_"),
            "data": data,
        })

    _staged_packet_plan = plan
    logger.info(
        f"build_packet: {packet_name} / {scenario!r} - {len(plan)} component(s) staged, "
        f"sharing claimant={shared_name!r} location={shared_location!r} "
        f"incident_date={shared_incident_date!r} claim={shared.get('claim_number')!r}"
    )
    return {
        "packet": packet_name,
        "scenario": scenario,
        "component_count": len(plan),
        "components": [{k: c[k] for k in ("label", "doc_type", "template_name")} for c in plan],
        "shared_identity": {
            "name": shared_name, "location": shared_location, "incident_date": shared_incident_date,
            "claim_number": shared.get("claim_number"), "policy_number": shared.get("policy_number"),
        },
    }


@tool
@_log_exceptions
def render_packet() -> dict:
    """Render every component build_packet staged, in order, and collect them
    into the packet returned to the user. One call does the whole packet -
    there is no per-component step, and no component's data or bytes ever
    passes through your output."""
    global _staged_packet
    plan = _staged_packet_plan
    if not plan:
        raise ValueError("No packet has been planned yet - call build_packet first.")

    _staged_packet = []
    for comp in plan:
        pdf_bytes = render_html_to_pdf(comp["template_name"], comp["data"])
        _staged_packet.append({"label": comp["label"], "kind": "pdf", "bytes": pdf_bytes})
        logger.info(f"render_packet: rendered {comp['label']!r} ({len(pdf_bytes)} bytes)")

    return {
        "status": "rendered",
        "components": [{"label": c["label"], "size_bytes": len(c["bytes"])} for c in _staged_packet],
    }


@tool
@_log_exceptions
def validate_document_structure(doc_type: str, data: dict = None) -> dict:
    """Validate that all required fields for the given document type are present in data."""
    if data is None:
        data = _require_staged_doc_data()
    required_fields = {
        "medical-record": ["patient_name", "dob", "mrn", "dos", "diagnosis_codes", "physician_name"],
        "medical-bill": ["patient_name", "account_number", "service_date", "line_items", "total_amount"],
        "discharge-summary": ["patient_name", "date_of_admission", "date_of_discharge", "diagnosis", "reason", "clinician_signature"],
        "acord-25": ["insured_name", "policy_number", "effective_date", "expiration_date", "insurer_name"],
        "cms-1500": ["patient_name", "insured_id", "dos_from", "diagnosis_codes", "procedure_codes", "provider_npi"],
        "ub-04": ["patient_name", "admission_date", "discharge_date", "revenue_codes", "total_charges"],
        "eob-explanation": ["subscriber_name", "claim_number", "provider_name", "claims", "totals"],
        "litigation-document": ["plaintiff_name", "defendant_name", "case_number", "court_name", "incident_date"],
        "demand-letter": ["claimant_name", "insurer_name", "claim_number", "incident_date", "demand_amount"],
        "police-report": ["incident_number", "incident_date", "location", "officer_name", "badge_number"],
        "pharmacy-invoice": ["invoice_number", "invoice_date", "company_gstin", "customer_name", "items", "grand_total"],
        "property-loss-notice": ["insured_name", "policy_number", "loss_date", "loss_location", "cause_of_loss"],
        "auto-accident-report": ["accident_date", "employee", "vehicle1", "vehicle2"],
    }

    resolved = resolve_doc_type(doc_type)
    if resolved not in required_fields:
        return {
            "valid": False,
            "missing_fields": [],
            "doc_type": doc_type,
            "error": (
                f"Unknown doc_type {doc_type!r} - no required-field list is defined for it, so "
                f"this document cannot be validated. Known types: {sorted(required_fields)}. If "
                f"this is a new variant template, add it to _DOC_TYPE_ALIASES in "
                f"renderers/synthetic_data.py."
            ),
        }

    missing = [f for f in required_fields[resolved] if f not in data or data[f] is None]
    return {"valid": len(missing) == 0, "missing_fields": missing, "doc_type": doc_type}
