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
            "2. For each component returned, call render_document_to_pdf(template_name, data) "
            "to produce the PDF bytes.\n"
            "3. Encode each component's PDF bytes as base64 string.\n"
            "4. Return final result as JSON object: {\"components\": [{\"label\": \"...\", \"pdf_bytes_b64\": \"...\"}]}.\n"
            "Always load the skill for each component doc_type before rendering it."
            + _custom_fields_block(req)
            + json_footer
        )

    if req.mode == "generate":
        return (
            f"Generate a single '{req.doc_type}' document for scenario '{req.scenario}'.\n"
            f"1. Load the skill: load_skill('{req.doc_type}').\n"
            f"2. Call generate_synthetic_data(doc_type='{req.doc_type}', scenario='{req.scenario}'"
            + (f", seed={req.seed}" if req.seed is not None else "") + ").\n"
            "3. Call validate_document_structure(data, doc_type) and fix any missing fields.\n"
            f"4. Call render_document_to_pdf(template_name='{req.doc_type.replace('-', '_')}', data=data).\n"
            "5. Encode the returned PDF bytes as a base64 string.\n"
            "6. Return JSON object: {\"pdf_bytes_b64\": \"<base64_string>\"}."
            + _custom_fields_block(req)
            + json_footer
        )

    if req.mode == "recreate":
        ext = req.reference_file_type or "pdf"
        return (
            f"Recreate a '{req.doc_type}' document based on a reference {ext} file.\n"
            f"1. Call analyze_reference_document(file_bytes=<reference_bytes>, file_type='{ext}') "
            "to understand the layout.\n"
            f"2. Load the skill: load_skill('{req.doc_type}').\n"
            f"3. Call generate_synthetic_data(doc_type='{req.doc_type}', scenario='{req.scenario}').\n"
            "4. Adapt the data to match the layout detected in step 1.\n"
            f"5. Call render_document_to_pdf(template_name='{req.doc_type.replace('-', '_')}', data=data).\n"
            "6. Encode the returned PDF bytes as base64.\n"
            "7. Return JSON object: {\"pdf_bytes_b64\": \"<base64_string>\"}."
            + _custom_fields_block(req)
            + json_footer
        )

    if req.mode == "fill" and (req.reference_file_type or "").lower().lstrip(".") == "docx":
        return (
            f"Fill the supplied blank .docx (Word content-control form) with coherent synthetic "
            f"data for scenario '{req.scenario}'.\n"
            "1. Load the skill: load_skill('dynamic-docx-fill') and follow it exactly. It works on "
            "ANY docx with content controls, including one never seen before - do not assume this "
            "document's controls or layout.\n"
            "2. Call inspect_docx_form_structure(docx_bytes=<reference_bytes>) to discover the "
            "document's real controls: each one's type (text/richText/date/checkbox/dropdown/"
            "combobox), harvested label, and - for dropdown/comboBox - its exact choices.\n"
            "3. Decide what each control is asking for FROM ITS LABEL, never from its raw `tag`. "
            "For a dropdown/comboBox you MUST pick one of its own `choices[].display` values.\n"
            "4. Choose values, keeping ONE coherent identity, date order, and arithmetic across "
            "the whole document.\n"
            "5. Call fill_docx_form_controls(docx_bytes, values={...}, checks={...}, choices={...}), "
            "then verify_docx_fill(...) and resolve any mismatch.\n"
            "6. Encode the verified docx bytes as base64.\n"
            "7. Return JSON object: {\"docx_bytes_b64\": \"<base64_string>\"}.\n"
            f"\nIf a '{req.doc_type}' skill exists with domain rules for this document type, you "
            "may also load it for guidance on realistic values - but dynamic-docx-fill governs "
            "the filling procedure itself."
            + _custom_fields_block(req)
            + json_footer
        )

    if req.mode == "fill":
        return (
            f"Fill the supplied blank fillable PDF form with coherent synthetic data "
            f"for scenario '{req.scenario}'.\n"
            "1. Load the skill: load_skill('dynamic-form-fill') and follow it exactly. "
            "It works on ANY AcroForm template, including one never seen before - do not "
            "assume this form's fields or layout.\n"
            "2. Call inspect_pdf_form_structure(pdf_bytes=<reference_bytes>) to discover the "
            "form's real structure: runs with harvested labels, Yes/No pairs with their "
            "question text, repeating grids, and section headings.\n"
            "3. Decide what each run/pair/grid column is asking for FROM ITS LABEL, never from "
            "its internal widget name. If a label is empty or ambiguous, call "
            "inspect_region_image on that widget's rect and look at the page.\n"
            "4. Choose values, keeping ONE coherent identity, date order, and arithmetic across "
            "the whole form.\n"
            "5. Fit text with flow_text_into_widgets (runs) and fit_grid_row (table rows) - never "
            "guess a font size.\n"
            "6. Call fill_pdf_widgets(...), then verify_pdf_fill(...) and resolve any mismatch.\n"
            "7. Encode the verified PDF bytes as base64.\n"
            "8. Return JSON object: {\"pdf_bytes_b64\": \"<base64_string>\"}.\n"
            f"\nIf a '{req.doc_type}' skill exists with domain rules for this document type, you "
            "may also load it for guidance on realistic values - but dynamic-form-fill governs "
            "the filling procedure itself."
            + _custom_fields_block(req)
            + json_footer
        )

    return f"Generate a '{req.doc_type}' document for scenario '{req.scenario}'." + _custom_fields_block(req) + json_footer
