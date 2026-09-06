from renderers.synthetic_data import resolve_doc_type

from .config import GenerationRequest
from .registry import DOC_TYPES, PACKET_REGISTRY, SCENARIO_REGISTRY

_JSON_FOOTER = (
    "\n\nOUTPUT: reply with a single raw JSON object and nothing else - no text "
    "before or after it."
)

_STAGED_FOOTER = (
    "\nThe generated data and the rendered document are both held server-side. Never "
    "restate the document's fields in your own output and never try to encode the PDF "
    "yourself - use revise_document_data for any change. When render_document_to_pdf "
    'returns, reply with {"status": "ok"}.'
)


def _claim_facts_block(req: GenerationRequest) -> str:
    if not req.custom_fields:
        return ""
    return (
        "\n\nREAL CLAIM VALUES (already applied automatically to every field that exists - "
        "do not re-apply them with revise_document_data). Use them when writing any narrative "
        "so it agrees with the document's own fields:\n"
        f"{req.custom_fields}"
    )


def _user_input_block(req: GenerationRequest) -> str:
    if not req.user_input:
        return ""
    return f"\n\nUSER INPUT (incorporate what is relevant to this document):\n{req.user_input}"


def _optional_args(req: GenerationRequest, *, with_anchor: bool) -> str:
    args = ""
    if with_anchor and req.custom_fields.get("loss_date"):
        args += f", anchor_date={req.custom_fields['loss_date']!r}"
    if req.custom_fields:
        args += f", custom_fields={req.custom_fields!r}"
    return args


def _seed_arg(req: GenerationRequest) -> str:
    return f", seed={req.seed}" if req.seed is not None else ""


def _doc_type_menu() -> str:
    return "\n".join(f"- {d['id']}: {d['label']} ({d['category']})" for d in DOC_TYPES)


def _scenario_menu() -> str:
    return "\n".join(f"- {sid}: {label}" for sid, label in SCENARIO_REGISTRY.items())


def _packet_prompt(req: GenerationRequest, tail: str) -> str:
    packet_name = req.doc_type
    auto_scenario = req.scenario == "auto"

    if packet_name and not auto_scenario:
        # The common case, unchanged: a named packet and a fixed scenario.
        return (
            f"Generate the '{packet_name}' document packet for scenario '{req.scenario}'.\n"
            f"1. build_packet(packet_name='{packet_name}', scenario='{req.scenario}'"
            f"{_seed_arg(req)}{_optional_args(req, with_anchor=False)})\n"
            "2. render_packet()\n"
            "That is the whole job. build_packet already gives every document the same "
            "claimant, claim number and incident date - do not adjust them, and do not loop "
            "over components. When render_packet returns, reply with "
            '{"status": "ok", "components": <count>}.'
            + tail
        )

    if packet_name and auto_scenario:
        # A named packet, but let the model pick which of its scenarios fits.
        choices = PACKET_REGISTRY.get(packet_name, {}).get("compatible_scenarios") or ["general"]
        return (
            f"Generate the '{packet_name}' document packet.\n"
            f"1. This packet fits several scenarios. Based on the claim facts and narrative "
            f"below, pick the single best-fitting one from: {', '.join(choices)}.\n"
            f"2. build_packet(packet_name='{packet_name}', scenario=<your pick>"
            f"{_seed_arg(req)}{_optional_args(req, with_anchor=False)})\n"
            "3. render_packet()\n"
            "build_packet already gives every document the same claimant, claim number and "
            "incident date - do not adjust them, and do not loop over components. When "
            "render_packet returns, reply with {\"status\": \"ok\", \"components\": <count>}."
            + tail
        )

    # No named packet fits (or none was chosen) - the model decides which
    # documents this claim actually needs, from what this system can generate.
    scenario_step = (
        f"3. Pick the scenario that best matches from:\n{_scenario_menu()}\n"
        if auto_scenario else
        f"3. Use scenario='{req.scenario}'.\n"
    )
    scenario_arg = "<the scenario you picked>" if auto_scenario else f"'{req.scenario}'"
    return (
        "No pre-defined packet was chosen for this claim - decide the right set of documents "
        "yourself.\n"
        "1. Read the claim facts and narrative below: loss type, loss cause, the adjuster's "
        "description, and any document excerpts.\n"
        "2. Based on standard US insurance claims practice for this kind of loss, choose every "
        "document type from this list that this claim would realistically need on file - not "
        "just one document, and not the whole list regardless of relevance:\n"
        f"{_doc_type_menu()}\n"
        + scenario_step +
        f"4. build_packet(components=[<your chosen document type ids>], scenario={scenario_arg}"
        f"{_seed_arg(req)}{_optional_args(req, with_anchor=False)})\n"
        "5. render_packet()\n"
        "build_packet gives every document the same claimant, claim number and incident date "
        "automatically - do not adjust them, and do not loop over components yourself. When "
        "render_packet returns, reply with {\"status\": \"ok\", \"components\": <count>}."
        + tail
    )


def build_generation_prompt(req: GenerationRequest) -> str:
    tail = _claim_facts_block(req) + _user_input_block(req) + _JSON_FOOTER

    if req.mode == "packet":
        return _packet_prompt(req, tail)

    if req.mode == "recreate":
        ext = req.reference_file_type or "pdf"
        return (
            f"Recreate the uploaded {ext} as a '{req.doc_type}' document, retold for the "
            f"scenario '{req.scenario}'.\n"
            "WHAT RECREATE MEANS: keep the SAME PEOPLE AND IDENTIFIERS as the upload - same "
            "claimant, date of birth, policy/claim/member/record numbers, provider, addresses - "
            f"but regenerate everything the scenario drives to fit '{req.scenario}': diagnoses, "
            "procedures, dates of service, line items, amounts, narrative. It is neither a fresh "
            "unrelated document nor a copy of the original.\n"
            f"1. analyze_uploaded_reference(file_type='{ext}') - the bytes are supplied "
            "automatically. Read each page's `text` to find the document's real values.\n"
            f"2. load_skill('{resolve_doc_type(req.doc_type)}') for this type's exact field names.\n"
            "3. Collect the values worth preserving into one dict keyed by those names. Omit "
            "anything the scenario should change, and omit any value the reference does not "
            "actually show rather than guessing. Some fields are nested dicts, not strings - "
            "check the skill's field list for the sub-keys (e.g. address = {street, city, state, "
            "zip}) and either match that shape or leave the field out entirely. A flat string "
            "sent to a nested field is rejected and reported in 'unmapped_keys'.\n"
            f"4. recreate_document_data(doc_type='{req.doc_type}', scenario='{req.scenario}', "
            f"carried_values=<that dict>{_optional_args(req, with_anchor=True)}). If the result's "
            "'unmapped_keys' is non-empty, those names are wrong for this document type or have "
            "the wrong shape - fix them against the skill's field list and call it once more.\n"
            f"5. render_document_to_pdf(template_name='{req.doc_type.replace('-', '_')}')"
            + _STAGED_FOOTER
            + tail
        )

    return (
        f"Generate a single '{req.doc_type}' document for scenario '{req.scenario}'.\n"
        f"1. load_skill('{resolve_doc_type(req.doc_type)}')\n"
        f"2. generate_synthetic_data(doc_type='{req.doc_type}', scenario='{req.scenario}'"
        f"{_seed_arg(req)}{_optional_args(req, with_anchor=True)})\n"
        f"3. validate_document_structure(doc_type='{req.doc_type}')\n"
        "4. Fix anything it reports missing with revise_document_data({...}), passing ONLY the "
        "fields that change.\n"
        f"5. render_document_to_pdf(template_name='{req.doc_type.replace('-', '_')}')"
        + _STAGED_FOOTER
        + tail
    )
