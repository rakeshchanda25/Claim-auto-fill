"""
Deterministic, template-agnostic structural analysis of a .docx's real
fillable structures: Word content-control SDTs (w:sdt). Mirrors
form_structure.py's PDF AcroForm analysis - same discover-first, meaning-
later split. Every `concept`/`dtype` field is left None deliberately: what a
control MEANS is the agent's job, not this module's.

Docx has no widget geometry (it's a flow document, not fixed boxes), so
there is no PDF-style overflow/font-fitting problem here - Word grows the
paragraph to fit whatever text a content control holds. That is also why
there is no docx equivalent of flow_text_into_widgets/fit_grid_row.
"""

from __future__ import annotations

import hashlib
import io

from docx import Document
from docx.oxml.ns import qn

W14_CHECKBOX = qn("w14:checkbox")


def _text_of(el) -> str:
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


def _control_type(sdt_pr) -> str:
    if sdt_pr is None:
        return "richText"
    if sdt_pr.find(W14_CHECKBOX) is not None:
        return "checkbox"
    if sdt_pr.find(qn("w:dropDownList")) is not None:
        return "dropdown"
    if sdt_pr.find(qn("w:comboBox")) is not None:
        return "combobox"
    if sdt_pr.find(qn("w:date")) is not None:
        return "date"
    if sdt_pr.find(qn("w:text")) is not None:
        return "text"
    return "richText"


def _choices(sdt_pr, ctype: str) -> list[dict]:
    if ctype not in ("dropdown", "combobox"):
        return []
    tag = "w:dropDownList" if ctype == "dropdown" else "w:comboBox"
    el = sdt_pr.find(qn(tag))
    if el is None:
        return []
    return [
        {"display": item.get(qn("w:displayText")), "value": item.get(qn("w:value"))}
        for item in el.findall(qn("w:listItem"))
    ]


def _context_label(sdt) -> str:
    """Best-effort context: text preceding the control in the same
    paragraph (the common 'Label: ____' pattern), else the previous
    paragraph's text, else - inside a table - the row's first cell."""
    p = sdt.getparent()
    while p is not None and p.tag != qn("w:p"):
        p = p.getparent()

    if p is not None:
        before = []
        for child in p:
            if child is sdt:
                break
            before.append(_text_of(child))
        inline = " ".join(t for t in before if t.strip()).strip().rstrip(":").strip()
        if inline:
            return inline

        prev = p.getprevious()
        while prev is not None and prev.tag == qn("w:p"):
            txt = _text_of(prev).strip()
            if txt:
                return txt.rstrip(":").strip()
            prev = prev.getprevious()

    tc = sdt.getparent()
    while tc is not None and tc.tag != qn("w:tc"):
        tc = tc.getparent()
    if tc is not None:
        tr = tc.getparent()
        first_tc = tr.find(qn("w:tc")) if tr is not None else None
        if first_tc is not None and first_tc is not tc:
            txt = _text_of(first_tc).strip()
            if txt:
                return txt.rstrip(":").strip()
    return ""


def iter_sdt(doc):
    """Walk every content-control SDT in document order, assigning each the
    SAME stable name docx_filler.py must reuse to address it: shared here so
    the two modules can never drift apart on naming. Yields
    (sdt, name, alias, tag, sdt_pr, sdt_content) - sdt_content is None (and
    the entry should be skipped by callers) for a malformed/emptied control."""
    seen_names: dict[str, int] = {}
    count = 0
    for sdt in doc.element.body.iter(qn("w:sdt")):
        sdt_pr = sdt.find(qn("w:sdtPr"))
        sdt_content = sdt.find(qn("w:sdtContent"))
        if sdt_content is None:
            continue
        count += 1

        alias_el = sdt_pr.find(qn("w:alias")) if sdt_pr is not None else None
        tag_el = sdt_pr.find(qn("w:tag")) if sdt_pr is not None else None
        alias = alias_el.get(qn("w:val")) if alias_el is not None else None
        tag = tag_el.get(qn("w:val")) if tag_el is not None else None

        base_name = tag or alias or f"content_control_{count}"
        n = seen_names.get(base_name, 0) + 1
        seen_names[base_name] = n
        name = base_name if n == 1 else f"{base_name}_{n}"

        yield sdt, name, alias, tag, sdt_pr, sdt_content


def _iter_controls(doc) -> list[dict]:
    controls = []

    for sdt, name, alias, tag, sdt_pr, sdt_content in iter_sdt(doc):
        ctype = _control_type(sdt_pr)
        placeholder = sdt_pr.find(qn("w:showingPlcHdr")) is not None if sdt_pr is not None else False

        controls.append(
            {
                "name": name,
                "alias": alias,
                "tag": tag,
                "type": ctype,
                "label": alias or _context_label(sdt),
                "choices": _choices(sdt_pr, ctype),
                "current_text": "" if placeholder else _text_of(sdt_content).strip(),
                "is_placeholder": placeholder,
                "checked": (
                    (sdt_pr.find(W14_CHECKBOX).find(qn("w14:checked")).get(qn("w14:val")) == "1")
                    if ctype == "checkbox"
                    else None
                ),
                "concept": None,  # <- agent fills
                "dtype": None,  # <- agent fills
            }
        )
    return controls


def fingerprint(controls: list[dict]) -> str:
    key = "|".join(sorted(f"{c['name']}:{c['type']}:{c['alias'] or ''}" for c in controls))
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def build_draft(docx_bytes: bytes) -> dict:
    doc = Document(io.BytesIO(docx_bytes))
    controls = _iter_controls(doc)

    by_type: dict[str, int] = {}
    for c in controls:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1

    return {
        "blueprint_version": 1,
        "status": "DRAFT_STRUCTURAL",
        "file_type": "docx",
        "fingerprint": fingerprint(controls),
        "stats": {
            "controls": len(controls),
            **by_type,
        },
        "controls": controls,
    }
