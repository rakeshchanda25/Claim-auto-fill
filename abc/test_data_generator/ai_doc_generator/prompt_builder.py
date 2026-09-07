from renderers.synthetic_data import resolve_doc_type
from .claim_playbook import playbook_text
from .registry import DOC_TYPES, PACKET_REGISTRY, SCENARIO_REGISTRY
from .config import GenerationRequest

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

def _packet_summary() -> str:
    lines = []

    for packet_name, packet in PACKET_REGISTRY.items():
        scenarios = ", ".join(packet["compatible_scenarios"])
        lines.append(
            f"- {packet_name}: {packet['display_name']} "
            f"(compatible scenarios: {scenarios})"
        )

    return "\n".join(lines)

def _packet_document_summary(packet_name: str) -> str:
    packet = PACKET_REGISTRY.get(packet_name)

    if not packet:
        return f"Unknown packet: {packet_name}"

    return "\n".join(
        f"{component['order']}. {component['doc_type']} - {component['label']}"
        for component in sorted(
            packet["components"],
            key=lambda x: x["order"]
        )
    )

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
            f"1. Call build_packet("
            f"packet_name='{packet_name}', "
            f"scenario='{req.scenario}'"
            f"{_seed_arg(req)}"
            f"{_optional_args(req, with_anchor=False)})\n"
            "2. Call render_packet()\n"
            "That is the whole job. build_packet already gives every document the same "
            "claimant, claim number and incident date - do not adjust them, and do not "
            "loop over components yourself. When render_packet returns, reply with "
            '{"status": "ok", "components": <count>}.'
            + tail
        )

    if packet_name and auto_scenario:
        # A named packet, but let the model pick which of its scenarios fits.
        choices = PACKET_REGISTRY.get(packet_name, {}).get("compatible_scenarios") or ["general"]
        return (
             f"Generate the '{packet_name}' document packet.\n"
            "1. Read the claim facts and narrative below: loss type, loss description, "
            "loss cause, the adjuster's description and notes, and treat it as "
            "'Claim Narrative'.\n"
            f"2. Based on the Claim Narrative, select the single best-fitting scenario "
            f"from the scenarios supported by this packet:\n"
            f"{', '.join(choices)}\n"
            f"3. Call build_packet("
            f"packet_name='{packet_name}', "
            f"scenario=<the scenario you picked>"
            f"{_seed_arg(req)}"
            f"{_optional_args(req, with_anchor=False)})\n"
            "4. Call render_packet()\n"
            "build_packet already gives every document the same claimant, claim number "
            "and incident date - do not adjust them, and do not loop over components "
            "yourself. When render_packet returns, reply with "
            '{"status": "ok", "components": <count>}.'
            + tail
        )

    scenario_step = (
        f"4. Choose the scenario that matches what actually happened, from:\n{_scenario_menu()}\n"
        if auto_scenario else
        f"4. Use scenario='{req.scenario}'.\n"
    )
    scenario_arg = "<the scenario you chose>" if auto_scenario else f"'{req.scenario}'"

    return (
        "You are assembling a realistic US insurance claim file. No pre-defined packet "
        "was chosen, so you decide which documents this specific claim would contain.\n\n"

        "STEP 1 - READ THE CLAIM.\n"
        "Below you are given the claim's real values and narrative: loss type, loss "
        "cause, loss location, the adjuster's description, and excerpts from documents "
        "already attached to the claim. Read them before deciding anything. The "
        "narrative tells you what actually happened; the document set must follow from "
        "it, not from a template.\n\n"

        "STEP 2 - CLASSIFY THE CLAIM using the domain reference below.\n"
        f"{playbook_text()}\n"

        "STEP 3 - SELECT THE DOCUMENTS.\n"
        "Start from the closest pre-defined packet as a sanity check on completeness:\n"
        f"{_packet_summary()}\n"
        "Then produce your own final list. You may drop a document the packet contains "
        "if the claim gives no basis for it, and you may add any document the claim "
        "clearly generated. You may ONLY use ids from this list:\n"
        f"{_doc_type_menu()}\n"

        + scenario_step +

        f"5. Call build_packet(components=[<your final document type ids>], "
        f"scenario={scenario_arg}"
        f"{_seed_arg(req)}{_optional_args(req, with_anchor=False)})\n"
        "6. Call render_packet().\n\n"

        "Before you call build_packet, check your list against the claim: is every "
        "document justified by something in the narrative, and is anything the claim "
        "obviously produced missing? A realistic file for a disputed injury claim is "
        "several documents; a simple first-party property claim may be two.\n"
        "build_packet gives every document the same claimant, claim number and incident "
        "date automatically - do not adjust them, and do not loop over components "
        "yourself. When render_packet returns, reply with "
        "{\"status\": \"ok\", \"components\": <count>}."
        + tail
    )


def build_generation_prompt(req: GenerationRequest) -> str:
    tail = _claim_facts_block(req) + _user_input_block(req) + _JSON_FOOTER

    if req.mode == "packet":
        return (_packet_prompt(req, tail))

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
