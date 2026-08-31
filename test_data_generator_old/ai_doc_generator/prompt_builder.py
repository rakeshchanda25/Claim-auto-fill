from renderers.synthetic_data import resolve_doc_type

from .config import GenerationRequest


def _custom_fields_block(req: GenerationRequest) -> str:
    """User-supplied values must reach the agent in EVERY mode - they were
    previously only wired into 'generate', so a name/amount pinned by the
    user was silently dropped when filling or recreating a form."""
    if not req.custom_fields:
        return ""
    return (
        f"\n\nUSER-SUPPLIED VALUES (authoritative - use each of these verbatim wherever "
        f"it fits a field, and only invent the remaining values):\n{req.custom_fields}"
    )


def build_generation_prompt(req: GenerationRequest) -> str:
    is_packet = req.doc_type.endswith("-packet") or req.mode == "packet"

    json_footer = (
        "\n\nCRITICAL OUTPUT REQUIREMENT:\n"
        "Your final response MUST be a single raw JSON object (or ```json ``` block).\n"
        "Do NOT include any conversational text before or after the JSON."
    )

    if is_packet:
        return (
            f"Generate a '{req.doc_type}' document packet for scenario '{req.scenario}'.\n"
            f"1. Call build_packet(packet_name='{req.doc_type}', scenario='{req.scenario}'"
            + (f", seed={req.seed}" if req.seed is not None else "") + ").\n"
            "2. Call render_packet(). That renders every component in one go.\n"
            "That is the whole job - there is no per-component step to run, and you never see, "
            "handle or encode any component's data or bytes. build_packet already gave every "
            "document the same claimant, claim number and encounter date so they belong to one "
            "claim; do not try to adjust them. Once render_packet returns, reply with a short "
            "JSON status object: {\"status\": \"ok\", \"components\": <count>}."
            + _custom_fields_block(req)
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
            # A variant template (e.g. acord-new) has no skill of its own - it
            # shares the parent form's field contract, so it loads the parent's
            # skill. Without resolving, load_skill would look for a directory
            # that does not exist.
            f"1. Load the skill: load_skill('{resolve_doc_type(req.doc_type)}').\n"
            f"2. Call generate_synthetic_data(doc_type='{req.doc_type}', scenario='{req.scenario}'"
            + (f", seed={req.seed}" if req.seed is not None else "") + ").\n"
            f"3. Call validate_document_structure(doc_type='{req.doc_type}').\n"
            "4. Fix anything it reports missing with revise_document_data({...}), passing ONLY the "
            "fields that change.\n"
            f"5. Call render_document_to_pdf(template_name='{req.doc_type.replace('-', '_')}')."
            + staged_footer
            + _custom_fields_block(req)
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
            "carried_values=<that dict>). It generates fresh data for the new scenario, overlays "
            "your carried values on top, and stages the result for rendering. If the result's "
            "'unmapped_keys' is non-empty, those names either do not exist for this document type or "
            "were rejected for a shape mismatch (see step 3) - re-check them against the skill's "
            "field list and call it once more with the corrected names/shapes.\n"
            f"5. Call render_document_to_pdf(template_name='{req.doc_type.replace('-', '_')}')."
            + staged_footer
            + _custom_fields_block(req)
            + json_footer
        )

    if req.mode == "fill" and (req.reference_file_type or "").lower().lstrip(".") == "docx":
        return (
            f"Fill the user's uploaded .docx (Word content-control form) with coherent synthetic "
            f"data. The user's own instructions for what to fill in are: '{req.scenario}'.\n"
            "0. ABSOLUTE RULE: you are filling the user's UPLOADED document in place. NEVER call "
            "generate_synthetic_data or render_document_to_pdf in this mode - those create a brand "
            "new document from a template, which is not this task, no matter how thin the "
            "instructions above look.\n"
            "1. Load the skill: load_skill('dynamic-docx-fill') and follow it exactly. It works on "
            "ANY docx with content controls, including one never seen before - do not assume this "
            "document's controls or layout.\n"
            "2. Call inspect_docx_form_structure() to discover the document's real controls (the "
            "uploaded file's bytes are supplied automatically, do not attempt to pass them): each "
            "one's type (text/richText/date/checkbox/dropdown/combobox), harvested label, and - for "
            "dropdown/comboBox - its exact choices.\n"
            "3. Decide what each control is asking for FROM ITS LABEL, never from its raw `tag`. "
            "For a dropdown/comboBox you MUST pick one of its own `choices[].display` values.\n"
            "4. Choose values, keeping ONE coherent identity, date order, and arithmetic across "
            "the whole document.\n"
            "5. Call fill_docx_form_controls(values={...}, checks={...}, choices={...}), then "
            "verify_docx_fill(expected_values) (no docx argument needed - it reads the "
            "just-filled docx automatically, but expected_values IS still required) and "
            "resolve any mismatch.\n"
            "6. The filled docx is staged automatically the moment fill_docx_form_controls runs - "
            "you never see or handle its bytes, and must NOT attempt to encode or embed them "
            "yourself. Once verify_docx_fill confirms ok, just return a short JSON status object: "
            "{\"status\": \"ok\"}."
            + _custom_fields_block(req)
            + json_footer
        )

    if req.mode == "fill":
        return (
            f"Fill the user's uploaded fillable PDF form with coherent synthetic data. The user's "
            f"own instructions for what to fill in are: '{req.scenario}'.\n"
            "0. ABSOLUTE RULE: you are filling the user's UPLOADED document in place. NEVER call "
            "generate_synthetic_data or render_document_to_pdf in this mode - those create a brand "
            "new document from a template, which is not this task, no matter how thin the "
            "instructions above look.\n"
            "1. Load the skill: load_skill('dynamic-form-fill') and follow it exactly. "
            "It works on ANY AcroForm template, including one never seen before - do not "
            "assume this form's fields or layout.\n"
            "2. Call inspect_pdf_form_structure() to discover the form's real structure (the "
            "uploaded file's bytes are supplied automatically, do not attempt to pass them): runs "
            "with harvested labels, Yes/No pairs with their question text, repeating grids, and "
            "section headings.\n"
            "3. Decide what each run/pair/grid column is asking for FROM ITS LABEL, never from "
            "its internal widget name. If a label is empty or ambiguous, call "
            "inspect_region on that widget's rect to read more of the surrounding page text.\n"
            "4. Choose values, keeping ONE coherent identity, date order, and arithmetic across "
            "the whole form.\n"
            "5. Fit text with flow_text_into_widgets (runs) and fit_grid_row (table rows) - never "
            "guess a font size.\n"
            "6. Call fill_pdf_widgets(widget_values, widget_fonts, watermark=...), then "
            "verify_pdf_fill(expected_values) (no PDF argument needed - it reads the just-filled "
            "PDF automatically) and resolve any mismatch.\n"
            "7. The filled PDF is staged automatically the moment fill_pdf_widgets runs - you never "
            "see or handle its bytes, and must NOT attempt to encode or embed them yourself (a "
            "document is far too large to transcribe as text). Once verify_pdf_fill confirms ok, "
            "just return a short JSON status object: {\"status\": \"ok\"}."
            + _custom_fields_block(req)
            + json_footer
        )

    return f"Generate a '{req.doc_type}' document for scenario '{req.scenario}'." + _custom_fields_block(req) + json_footer
