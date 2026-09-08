import random
import threading
from dataclasses import dataclass, field

from faker import Faker

try:
    from andromeda.tools import tool
except Exception:  # framework absent (local dev, tooling) - tools stay plain callables
    def tool(func):
        return func

from renderers import render_html_to_pdf
from renderers.docx_parser import extract_docx_layout
from renderers.synthetic_data import _parse_anchor_date, build_synthetic_data, resolve_doc_type

from .registry import DOC_TYPES, PACKET_REGISTRY

# doc_type id -> human label, used to name ad hoc packet components.
DOC_TYPE_LABELS = {d["id"]: d["label"] for d in DOC_TYPES}


@dataclass
class RunContext:

    reference_bytes: bytes | None = None
    custom_fields: dict = field(default_factory=dict)
    anchor_date: str | None = None

    # What the model concluded about this claim before choosing documents.
    # Survives the whole run, so a later step can re-read it instead of
    # relying on the model still remembering it.
    analysis: dict | None = None

    doc_data: dict | None = None
    packet_plan: list[dict] | None = None
    artifact: tuple[bytes, str] | None = None
    packet: list[dict] | None = None


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


def _overlay(dst: dict, src: dict, path: str = "", unmapped: list | None = None) -> list:
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

_PER_DOC_ALIASES = {
    "eob-explanation": {"provider_name": "physician"},
    "ub-04": {"provider_name": "facility"},
}

_PACKET_SHARED_FIELDS = (
    "gender", "address", "phone", "mrn", "npi", "specialty", "dea",
    "claim_number", "policy_number",
    "dos", "dos_from", "dos_to", "service_date",
)

_CLAIM_DATE_FIELDS = ("loss_date", "reported_date", "policy_effective_date",
                      "policy_expiration_date")


def _alias_fields(doc_type: str | None, concept: str) -> list[str]:
    fields = list(_ALIASES.get(concept, ()))
    for field_name, mapped in _PER_DOC_ALIASES.get(doc_type or "", {}).items():
        if mapped == concept:
            fields.append(field_name)
    return fields or [concept]


def _apply_concept(data: dict, doc_type: str | None, concept: str, value) -> None:
    if value is None:
        return
    for f in _alias_fields(doc_type, concept):
        if f in data:
            data[f] = value
    if concept != "claimant":
        return
    parties = data.get("parties_involved")
    if isinstance(parties, list) and parties:
        parties[0]["name"] = value
    employee = data.get("employee")
    if isinstance(employee, dict):
        employee["name"] = value


def _read_concept(data: dict, doc_type: str | None, concept: str):
    for f in _alias_fields(doc_type, concept):
        if data.get(f):
            return data[f]
    return None


def _normalize_claim_dates(fields: dict) -> dict:
    out = dict(fields)
    for key in _CLAIM_DATE_FIELDS:
        parsed = _parse_anchor_date(out.get(key))
        if parsed:
            out[key] = parsed.strftime("%m/%d/%Y")
    return out


def _apply_claim_facts(data: dict, doc_type: str, custom_fields: dict) -> None:
    if not custom_fields:
        return
    fields = _normalize_claim_dates(custom_fields)
    _overlay(data, fields)
    _apply_concept(data, doc_type, "claimant", fields.get("insured_name"))
    _apply_concept(data, doc_type, "location", fields.get("loss_location"))
    _apply_concept(data, doc_type, "incident_date", fields.get("loss_date"))


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
    _apply_claim_facts(data, doc_type, custom_fields)
    for concept, value in shared.items():
        _apply_concept(data, doc_type, concept, value)

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
    for concept in _ALIASES:
        if not shared.get(concept):
            value = _read_concept(data, doc_type, concept)
            if value:
                shared[concept] = value
    for field_name in _PACKET_SHARED_FIELDS:
        if not shared.get(field_name) and data.get(field_name):
            shared[field_name] = data[field_name]


def _merged_fields(custom_fields: dict | None) -> dict:
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


@tool
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


@tool
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

    carried_ok = sum(1 for k in (carried_values or {}) if k not in unmapped)

    summary = _stage_doc_data(data, doc_type, scenario)
    summary["carried_keys"] = carried_ok
    summary["unmapped_keys"] = unmapped
    return summary


@tool
def revise_document_data(changes: dict) -> dict:
    """Update specific fields on the staged document; nested dicts merge.
    Returns the changed and unmapped field names."""
    unmapped = _overlay(_require_doc_data(), changes)
    return {
        "status": "revised",
        "changed": [k for k in (changes or {}) if k not in unmapped],
        "unmapped_keys": unmapped,
    }


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


@tool
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


@tool
def render_document_to_pdf(template_name: str) -> dict:
    """Render the staged document to a PDF. The result is staged automatically -
    it never passes through your output."""
    pdf_bytes = render_html_to_pdf(template_name, _require_doc_data())
    current_run().artifact = (pdf_bytes, "pdf")
    return {"status": "staged", "kind": "pdf", "size_bytes": len(pdf_bytes)}


def analyze_reference_document(file_bytes: bytes, file_type: str) -> dict:
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
            if b.get("type") != 0:
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


@tool
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


@tool
def note_claim_analysis(claim_type: str, coverage_side: str, injuries_involved: bool,
                        vehicle_involved: bool, documents: list, reasoning: str) -> dict:
    """Record what you concluded about this claim BEFORE building anything.

    Call this once, after reading the claim narrative and the domain reference,
    and before build_packet.

    - claim_type: the claim type from the domain reference that this claim is
      (e.g. "Occupational illness / toxic exposure", "Auto - third-party bodily
      injury"). Say what the claim actually is, not what documents you want.
    - coverage_side: "first-party" or "third-party".
    - injuries_involved: did a person suffer bodily injury or illness?
    - vehicle_involved: was a motor vehicle involved in causing the loss? Answer
      False for workplace exposure, illness, property loss with no vehicle, or
      any loss where no vehicle was part of the event.
    - documents: the document type ids you intend to generate.
    - reasoning: one or two sentences tying the document list to the narrative.

    Returns your analysis back so you can re-read it later with
    read_claim_analysis instead of relying on memory.
    """
    unknown = [d for d in documents if d not in DOC_TYPE_LABELS]
    if unknown:
        raise ValueError(
            f"Unknown document type(s): {unknown}. Known types: {sorted(DOC_TYPE_LABELS)}")

    analysis = {
        "claim_type": claim_type,
        "coverage_side": coverage_side,
        "injuries_involved": bool(injuries_involved),
        "vehicle_involved": bool(vehicle_involved),
        "documents": list(documents),
        "reasoning": reasoning,
    }

    current_run().analysis = analysis
    return analysis


@tool
def read_claim_analysis() -> dict:
    """Re-read the analysis you recorded with note_claim_analysis. Use this if
    you are unsure what you already decided about this claim."""
    analysis = current_run().analysis
    if not analysis:
        raise ValueError("No analysis recorded yet - call note_claim_analysis first.")
    return analysis


@tool
def build_packet(packet_name: str = None, scenario: str = "general", seed: int = None,
                 custom_fields: dict = None, components: list = None) -> dict:
    """Plan a document packet, giving every document one shared claimant, claim
    number and incident date.

    Pass EXACTLY ONE of:

    - packet_name: the id of a pre-defined packet, when one fits the claim as-is.
    - components: a list of document type ids you selected yourself, when the
      claim needs a different set than any fixed packet offers. Use this when
      you have read the claim narrative and decided which documents this
      specific loss would generate in a real US claim file.

    Every id in `components` must be one this system can render. Anything else
    is rejected and the valid list is returned to you, so re-call with corrected
    ids rather than guessing again.

    Claim facts are applied to every component here - a packet has no
    per-component step where they could otherwise land. The loss date, if there
    is one, anchors every component's generated dates.
    """
    if packet_name:
        spec = PACKET_REGISTRY.get(packet_name)
        if not spec:
            raise ValueError(f"Unknown packet: {packet_name}. Available: {list(PACKET_REGISTRY)}")
        component_specs = spec["components"]
    elif components:
        if not current_run().analysis:
            raise ValueError(
                "Record your reasoning first: call note_claim_analysis(...) with the "
                "claim type, coverage side, whether injuries and a vehicle were "
                "involved, your document list and why - then call build_packet again.")
        unknown = [c for c in components if c not in DOC_TYPE_LABELS]
        if unknown:
            raise ValueError(
                f"Unknown document type(s): {unknown}. Known types: {sorted(DOC_TYPE_LABELS)}"
            )
        # De-duplicated, order preserved: the model may legitimately repeat a
        # type (e.g. listing medical-bill twice), but one of each is what a
        # claim file holds.
        ordered = list(dict.fromkeys(components))
        component_specs = [
            {"doc_type": doc_type, "label": DOC_TYPE_LABELS[doc_type], "order": i}
            for i, doc_type in enumerate(ordered)
        ]
    else:
        raise ValueError(
            "build_packet needs either packet_name (a pre-defined packet) or "
            "components (the document type ids you chose for this claim)."
        )

    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)

    fields = _merged_fields(custom_fields)
    claim_description = fields.pop("_claim_description", None)
    excerpts = fields.pop("_document_excerpts", None)
    anchor_date = fields.get("loss_date") or current_run().anchor_date

    claim_fields = _normalize_claim_dates(fields)
    shared: dict = {}
    for concept, key in (("claimant", "insured_name"), ("location", "loss_location"),
                         ("incident_date", "loss_date"), ("insurer", "insurer_name")):
        if claim_fields.get(key):
            shared[concept] = claim_fields[key]

    component_specs = sorted(component_specs, key=lambda c: c["order"])
    plan = []
    for comp in component_specs:
        doc_type = comp["doc_type"]
        data = build_synthetic_data(doc_type, scenario, anchor_date=anchor_date)
        _sync_component(data, doc_type, shared, fields, claim_description, excerpts)
        _seed_shared(shared, data, doc_type)
        plan.append({
            "label": comp["label"],
            "doc_type": doc_type,
            "template_name": doc_type.replace("-", "_"),
            "data": data,
        })

    for entry in plan:
        _sync_component(entry["data"], entry["doc_type"], shared, fields,
                        claim_description, excerpts=None)

    current_run().packet_plan = plan
    return {
        "packet": packet_name or "custom",
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


@tool
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

    return {
        "status": "rendered",
        "components": [{"label": c["label"], "size_bytes": len(c["bytes"])} for c in ctx.packet],
    }


# Already wrapped by @tool at definition, so this is just the roster the agent
# is given - nothing is re-wrapped here.
AGENT_TOOLS = (
    generate_synthetic_data,
    recreate_document_data,
    revise_document_data,
    validate_document_structure,
    render_document_to_pdf,
    analyze_uploaded_reference,
    build_packet,
    render_packet,
    note_claim_analysis,
    read_claim_analysis,
)


def agent_tools() -> list:
    return list(AGENT_TOOLS)
