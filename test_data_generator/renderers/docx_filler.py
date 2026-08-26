"""
Fill/read-back for .docx content-control SDTs, paired with docx_structure.py.
Writes values the same way Word itself does when a user fills a form field,
so the result round-trips cleanly when reopened in Word:
 - text/richText/date: replace sdtContent's runs with one run holding the
   value (reusing the first run's formatting), and clear w:showingPlcHdr so
   the filled text no longer renders as placeholder/ghost text.
 - checkbox (w14:checkbox): flip w14:checked and swap the displayed glyph to
   the control's own checked/unchecked symbol + font (never assume "X" -
   the glyph is whatever the form author configured).
 - dropdown/comboBox: set sdtContent's text to the chosen listItem's
   displayText (this IS the selection - OOXML has no separate "selected
   index" for these two control types).
"""

from __future__ import annotations

import copy
import io

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from .docx_structure import _choices, _control_type, iter_sdt

W14_CHECKBOX = qn("w14:checkbox")


def _set_sdt_content_text(sdt_content, text: str) -> None:
    runs = sdt_content.findall(".//" + qn("w:r"))
    rPr = copy.deepcopy(runs[0].find(qn("w:rPr"))) if runs and runs[0].find(qn("w:rPr")) is not None else None

    p = sdt_content.find(qn("w:p"))
    container = p if p is not None else sdt_content
    for r in list(container.findall(qn("w:r"))):
        container.remove(r)

    new_r = OxmlElement("w:r")
    if rPr is not None:
        new_r.append(rPr)
    new_t = OxmlElement("w:t")
    new_t.set(qn("xml:space"), "preserve")
    new_t.text = text
    new_r.append(new_t)
    container.append(new_r)


def _set_sdt_content_glyph(sdt_content, glyph: str, font: str) -> None:
    p = sdt_content.find(qn("w:p"))
    container = p if p is not None else sdt_content
    for r in list(container.findall(qn("w:r"))):
        container.remove(r)

    new_r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"), font)
    rFonts.set(qn("w:hAnsi"), font)
    rFonts.set(qn("w:hint"), "eastasia")
    rPr.append(rFonts)
    new_r.append(rPr)
    new_t = OxmlElement("w:t")
    new_t.text = glyph
    new_r.append(new_t)
    container.append(new_r)


def _clear_placeholder_flag(sdt_pr) -> None:
    if sdt_pr is None:
        return
    flag = sdt_pr.find(qn("w:showingPlcHdr"))
    if flag is not None:
        sdt_pr.remove(flag)


def fill_docx_controls(
    docx_bytes: bytes,
    values: dict[str, str] | None = None,
    checks: dict[str, bool] | None = None,
    choices: dict[str, str] | None = None,
) -> bytes:
    values = values or {}
    checks = checks or {}
    choices = choices or {}

    doc = Document(io.BytesIO(docx_bytes))

    for sdt, name, alias, tag, sdt_pr, sdt_content in iter_sdt(doc):
        ctype = _control_type(sdt_pr)

        if ctype == "checkbox" and name in checks:
            cb = sdt_pr.find(W14_CHECKBOX)
            checked = bool(checks[name])
            checked_el = cb.find(qn("w14:checked"))
            checked_el.set(qn("w14:val"), "1" if checked else "0")
            state_tag = qn("w14:checkedState") if checked else qn("w14:uncheckedState")
            state_el = cb.find(state_tag)
            val = state_el.get(qn("w14:val")) if state_el is not None else ("2612" if checked else "2610")
            font = state_el.get(qn("w14:font")) if state_el is not None else "MS Gothic"
            _set_sdt_content_glyph(sdt_content, chr(int(val, 16)), font)
            continue

        if ctype in ("dropdown", "combobox") and name in choices:
            wanted = choices[name]
            valid = {c["display"] for c in _choices(sdt_pr, ctype)}
            if wanted not in valid:
                raise ValueError(f"{name}: {wanted!r} is not one of the control's listItems {sorted(valid)}")
            _set_sdt_content_text(sdt_content, wanted)
            _clear_placeholder_flag(sdt_pr)
            continue

        if ctype in ("text", "richText", "date") and name in values:
            _set_sdt_content_text(sdt_content, str(values[name]))
            _clear_placeholder_flag(sdt_pr)

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def read_back_docx_controls(docx_bytes: bytes) -> dict[str, str | bool]:
    """Reads the just-written values back out, so verify_docx_fill can diff
    against what was requested - never trust a fill worked, confirm it."""
    from .docx_structure import build_draft

    draft = build_draft(docx_bytes)
    out: dict[str, str | bool] = {}
    for c in draft["controls"]:
        out[c["name"]] = c["checked"] if c["type"] == "checkbox" else c["current_text"]
    return out
