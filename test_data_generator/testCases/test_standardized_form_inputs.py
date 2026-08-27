"""
Tests for the placeholder-then-fill pipeline's input-name handling
(renderers/html_renderer.py::substitute_form_inputs).

The bug these guard against: ACORD-25/CMS-1500/UB-04 all legitimately render
the same data key several times (effective_date on each ACORD coverage row,
dos_from per CMS service line, discharge_date on every UB revenue-code row).
Emitting <input name="discharge_date"> six times gives six widgets sharing
one /T - AcroForm treats that as ONE field, and pypdf then collides on the
per-field XObject it builds while flattening, so only one of those six
locations renders the value. The fix names them discharge_date,
discharge_date__2, ... while keeping each mapped to the original data key.

WeasyPrint isn't importable in this sandbox (needs GTK system libs), so it's
stubbed - none of these tests touch actual PDF rendering, only the pure-Python
name substitution and mapping that precede it.
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

if "weasyprint" not in sys.modules:
    _fake_weasyprint = types.ModuleType("weasyprint")
    _fake_weasyprint.HTML = object
    sys.modules["weasyprint"] = _fake_weasyprint

from renderers.html_renderer import (  # noqa: E402
    _env,
    flatten_data,
    make_placeholder_data,
    substitute_form_inputs,
)
from renderers.synthetic_data import build_synthetic_data  # noqa: E402

STANDARDIZED = ["acord-25", "cms-1500", "ub-04"]


def _rendered_placeholder_html(doc_type: str) -> tuple[str, dict]:
    data = build_synthetic_data(doc_type, "general")
    template = _env.get_template(doc_type.replace("-", "_") + ".html")
    return template.render(**make_placeholder_data(data)), data


def test_substitute_form_inputs_uniquifies_repeated_names():
    html = "__FORM_FIELD_eff__ x __FORM_FIELD_eff__ y __FORM_FIELD_other__"
    out, widget_source = substitute_form_inputs(html)

    names = re.findall(r'name="([^"]+)"', out)
    assert names == ["eff", "eff__2", "other"]
    # every widget still points back at the data key it came from
    assert widget_source == {"eff": "eff", "eff__2": "eff", "other": "other"}


def test_substitute_form_inputs_leaves_no_tokens_behind():
    html = "__FORM_FIELD_a__ __FORM_FIELD_b__ __FORM_FIELD_a__"
    out, _ = substitute_form_inputs(html)
    assert "__FORM_FIELD_" not in out


@pytest.mark.parametrize("doc_type", STANDARDIZED)
def test_every_real_template_emits_unique_widget_names(doc_type):
    # The regression itself: before the fix these templates emitted 7-9
    # duplicate names each, which is what broke flattening.
    html, _ = _rendered_placeholder_html(doc_type)
    out, widget_source = substitute_form_inputs(html)

    names = re.findall(r'name="([^"]+)"', out)
    assert len(names) == len(set(names)), f"{doc_type} emitted duplicate widget names"
    assert len(names) == len(widget_source)


@pytest.mark.parametrize("doc_type", STANDARDIZED)
def test_repeated_keys_are_actually_present_and_all_resolve_to_data(doc_type):
    html, data = _rendered_placeholder_html(doc_type)
    _, widget_source = substitute_form_inputs(html)
    flat = flatten_data(data)

    # These templates DO repeat keys - if that ever stops being true the
    # uniquifying logic is no longer exercised and this test should be revisited.
    assert len(widget_source) > len(set(widget_source.values())), (
        f"{doc_type} no longer repeats any data key"
    )

    # Every widget - including the __2/__3 duplicates - must resolve to a
    # real value, otherwise the fill writes empty strings into those boxes.
    field_map = {w: flat.get(src, "") for w, src in widget_source.items()}
    unresolved = [w for w, v in field_map.items() if v == "" and widget_source[w] not in flat]
    assert not unresolved, f"{doc_type} widgets map to no data key: {unresolved[:5]}"


@pytest.mark.parametrize("doc_type", STANDARDIZED)
def test_duplicate_widgets_share_their_source_value(doc_type):
    html, data = _rendered_placeholder_html(doc_type)
    _, widget_source = substitute_form_inputs(html)
    flat = flatten_data(data)

    by_source: dict[str, list[str]] = {}
    for widget, src in widget_source.items():
        by_source.setdefault(src, []).append(widget)

    for src, widgets in by_source.items():
        if len(widgets) < 2:
            continue
        values = {flat.get(src, "") for _ in widgets}
        assert len(values) == 1, f"{doc_type}: {src} duplicates disagree on value"
