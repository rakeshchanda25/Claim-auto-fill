from renderers.synthetic_data import resolve_doc_type

from .config import GenerationRequest


def _custom_fields_block(req: GenerationRequest) -> str:
    """ User supplied values passing to LLM so they can be used for filling or recreating the a form
    """
    if not req.custom_fields:
        return ""
    return (
        f"\n\nUSER-SUPPLIED VALUES (authoritative - use each of these verbatim wherever "
        f"it fits a field, and only invent the remaining values):\n{req.custom_fields}"
    )


def _custom_fields_arg(req: GenerationRequest) -> str:
    """A `, custom_fields=<dict>` kwarg fragment - the literal dict embedded
    directly, same trick as packet mode's build_packet(..., custom_fields=...)
    below. Without this, custom_fields (USER-SUPPLIED VALUES, e.g. a live
    Guidewire claim) only ever reached the model as prose it had to notice
    and manually re-apply via revise_document_data/carried_values, correctly
    guessing which of ITS OWN field names each value belonged to - which is
    exactly the failure mode reported as "Guidewire info is not used" in
    Generate/Recreate mode. generate_synthetic_data/recreate_document_data
    now apply this automatically (see tools.py's _apply_claim_facts), so it
    no longer depends on the model doing that translation correctly."""
    return f", custom_fields={req.custom_fields!r}" if req.custom_fields else ""


def _anchor_date_arg(req: GenerationRequest) -> str:
    """A `, anchor_date=<value>` kwarg fragment, present only when
    custom_fields carries a 'loss_date' (from a live Guidewire lookup - see
    app.py's fetch_claim_facts). Embedding the literal value here (not just
    describing it in prose and trusting the model to notice and pass it) is
    what makes every generated date field - report_date, dos, an incident's
    embedded case-number year, etc. - actually anchor to the real loss date
    instead of an independently random one; see build_synthetic_data's
    anchor_date parameter for the mechanism."""
    loss_date = (req.custom_fields or {}).get("loss_date")
    return f", anchor_date={loss_date!r}" if loss_date else ""


def _user_input_block(req: GenerationRequest) -> str:
    """Free-form text typed in the frontend's "User Input" box. Distinct from
    custom_fields (structured field:value overrides, including any facts a
    Guidewire claim lookup added - see app.py's ai_generate_document): this is
    plain guidance/instructions, not necessarily field-shaped."""
    if not req.user_input:
        return ""
    return f"\n\nUSER INPUT (incorporate what's relevant to this document):\n{req.user_input}"


def build_generation_prompt(req: GenerationRequest) -> str:
    is_packet = req.doc_type.endswith("-packet") or req.mode == "packet"

    json_footer = (
        "\n\nCRITICAL OUTPUT REQUIREMENT:\n"
        "Your final response MUST be a single raw JSON object (or ```json ``` block).\n"
        "Do NOT include any conversational text before or after the JSON."
    )

    if is_packet:
        # custom_fields is embedded directly as a literal kwarg, not left for the
        # model to notice in the USER-SUPPLIED VALUES prose and retype - the
        # packet prompt explicitly tells the model there is no per-component step
        # where it could otherwise apply these (see build_packet's own docstring:
        # it previously had no parameter for this at all, so a packet request
        # carrying Guidewire/custom_fields data silently ignored it entirely).
        return (
            f"Generate a '{req.doc_type}' document packet for scenario '{req.scenario}'.\n"
            f"1. Call build_packet(packet_name='{req.doc_type}', scenario='{req.scenario}'"
            + (f", seed={req.seed}" if req.seed is not None else "") + _custom_fields_arg(req) + ").\n"
            "2. Call render_packet(). That renders every component in one go.\n"
            "That is the whole job - there is no per-component step to run, and you never see, "
            "handle or encode any component's data or bytes. build_packet already gave every "
            "document the same claimant, claim number and encounter date so they belong to one "
            "claim; do not try to adjust them. Once render_packet returns, reply with a short "
            "JSON status object: {\"status\": \"ok\", \"components\": <count>}."
            + _custom_fields_block(req)
            + _user_input_block(req)
            + json_footer
        )

    staged_footer = (
        "\nNever pass a `data` argument to validate_document_structure or render_document_to_pdf, "
        "and never restate the document's fields in your own output: the generated data is held "
        "server-side and both tools read it automatically. Repeating it back is the slowest thing "
        "you can do and risks corrupting a field - use revise_document_data for any change.\n"
        "The rendered PDF is staged automatically the moment render_document_to_pdf runs - "
        "you never see or handle its bytes, and must NOT attempt to encode or embed them "
        "yourself (a document is far too large to transcribe as text). Once it's staged, just "
        "return a short JSON status object: {\"status\": \"ok\"}."
    )

    if req.mode == "generate":
        return (
            f"Generate a single '{req.doc_type}' document for scenario '{req.scenario}'.\n"
            f"1. Load the skill: load_skill('{resolve_doc_type(req.doc_type)}').\n"
            f"2. Call generate_synthetic_data(doc_type='{req.doc_type}', scenario='{req.scenario}'"
            + (f", seed={req.seed}" if req.seed is not None else "") + _anchor_date_arg(req)
            + _custom_fields_arg(req) + ").\n"
            f"3. Call validate_document_structure(doc_type='{req.doc_type}').\n"
            "4. Fix anything it reports missing with revise_document_data({...}), passing ONLY the "
            "fields that change.\n"
            f"5. Call render_document_to_pdf(template_name='{req.doc_type.replace('-', '_')}')."
            + staged_footer
            + _custom_fields_block(req)
            + _user_input_block(req)
            + json_footer
        )

    if req.mode == "recreate":
        ext = req.reference_file_type or "pdf"
        skill = resolve_doc_type(req.doc_type)
        return (
            f"Recreate the user's uploaded {ext} as a '{req.doc_type}' document, re-told for the "
            f"scenario '{req.scenario}'.\n"
            "WHAT RECREATE MEANS: the new document keeps the SAME PEOPLE AND IDENTIFIERS as the "
            "uploaded one - same claimant/patient, same date of birth, same policy, claim, member "
            "and record numbers, same provider, same addresses - but everything the scenario drives "
            f"is re-generated to fit '{req.scenario}' instead: diagnoses, procedures, service dates, "
            "line items, amounts, and any narrative. It is NOT a fresh unrelated document, and it is "
            "NOT a copy of the original either.\n"
            f"1. Call analyze_uploaded_reference(file_type='{ext}') - the uploaded file's bytes are "
            "supplied automatically, do not attempt to pass them. Read each page's `text` to find "
            "the document's actual values.\n"
            f"2. Load the skill: load_skill('{skill}') - it lists the exact field names this "
            "document type uses.\n"
            "3. From the reference text, collect the values worth preserving into one dict, keyed by "
            "those field names - the people and identifiers listed above. Leave OUT anything the "
            "scenario should change; if the reference does not show a value, simply omit that key "
            "rather than guessing one. Some fields (an address, for instance) are NESTED dicts, not "
            "a single string - check the skill's field list for the exact sub-keys (e.g. address = "
            "{street, city, state, zip}) and either supply that same nested shape or leave the whole "
            "field out. A flat string carried for a field that is actually a nested dict is rejected "
            "(reported back in 'unmapped_keys'), not silently applied - it would otherwise replace "
            "the structured value and break every part of the document that reads a sub-field.\n"
            f"4. Call recreate_document_data(doc_type='{req.doc_type}', scenario='{req.scenario}', "
            f"carried_values=<that dict>{_anchor_date_arg(req)}{_custom_fields_arg(req)}). "
            "It generates fresh data for the new scenario, overlays "
            "your carried values on top, and stages the result for rendering. If the result's "
            "'unmapped_keys' is non-empty, those names either do not exist for this document type or "
            "were rejected for a shape mismatch (see step 3) - re-check them against the skill's "
            "field list and call it once more with the corrected names/shapes.\n"
            f"5. Call render_document_to_pdf(template_name='{req.doc_type.replace('-', '_')}')."
            + staged_footer
            + _custom_fields_block(req)
            + _user_input_block(req)
            + json_footer
        )

    return (
        f"Generate a '{req.doc_type}' document for scenario '{req.scenario}'."
        + _custom_fields_block(req) + _user_input_block(req) + json_footer
    )
