"""
Guards the data contract between renderers/synthetic_data.py and the Jinja
templates, plus recreate mode's carry-the-identity behaviour.

The template audit here is the regression guard for a whole bug CLASS rather
than one bug: a template field that synthetic_data never supplies used to
render as an empty string, so it surfaced only as an unexplained blank patch
in the finished PDF - the single hardest failure in this project to trace
back to its cause. Two real instances motivated these tests:

  * ub_04.html printed the provider's telephone (FL1) but only cms-1500's
    data branch ever defined billing_provider_phone;
  * acord_new.html, a newly added variant template, had a doc_type that
    matched no branch in build_synthetic_data at all, so EVERY one of its
    52 fields was blank.

renderers/html_renderer.py now uses Jinja's StrictUndefined so this fails
loudly at render time too, but that only fires for the doc types someone
actually generates. This sweeps every template against every scenario, so a
newly added template or a renamed field is caught here first.
"""

from __future__ import annotations

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

from ai_doc_generator import tools  # noqa: E402
from ai_doc_generator.packets import SCENARIO_REGISTRY  # noqa: E402
from renderers.html_renderer import _env  # noqa: E402
from renderers.synthetic_data import build_synthetic_data  # noqa: E402

TEMPLATE_NAMES = sorted(p.stem for p in (_ROOT / "renderers" / "templates").glob("*.html"))


def _doc_type_for(template_name: str) -> str:
    return template_name.replace("_", "-")


def test_every_template_has_a_template_to_test():
    # Cheap canary: if the glob silently finds nothing, every other test in
    # this file would vacuously pass.
    assert len(TEMPLATE_NAMES) >= 13, TEMPLATE_NAMES


@pytest.mark.parametrize("template_name", TEMPLATE_NAMES)
def test_synthetic_data_supplies_every_field_the_template_uses(template_name):
    """Renders with StrictUndefined (html_renderer's own env), so any field
    the template references but the data never defines raises here instead of
    silently leaving a blank in the PDF."""
    doc_type = _doc_type_for(template_name)
    data = build_synthetic_data(doc_type, "general")
    _env.get_template(f"{template_name}.html").render(data=data, **data)


@pytest.mark.parametrize("template_name", TEMPLATE_NAMES)
def test_templates_render_for_every_scenario(template_name):
    """A field can be present for one scenario and absent for another (e.g.
    only populated on auto-accident scenarios), which the single-scenario
    test above would miss."""
    doc_type = _doc_type_for(template_name)
    template = _env.get_template(f"{template_name}.html")
    for scenario in SCENARIO_REGISTRY:
        data = build_synthetic_data(doc_type, scenario)
        template.render(data=data, **data)


@pytest.fixture
def fake_variant_alias():
    """A throwaway doc_type alias pointed at a real, stable doc_type
    (medical-record), so the alias MECHANISM is tested without hardcoding a
    specific variant template - those have already been renamed/merged/
    deleted twice in this project's history, which is exactly the kind of
    churn a mechanism test should be immune to."""
    from renderers import synthetic_data

    synthetic_data._DOC_TYPE_ALIASES["test-only-variant"] = "medical-record"
    try:
        yield "test-only-variant"
    finally:
        del synthetic_data._DOC_TYPE_ALIASES["test-only-variant"]


def test_variant_alias_resolves_to_its_parents_data(fake_variant_alias):
    """A variant doc_type must resolve to its parent's data contract, not
    fall through every branch in build_synthetic_data and return the bare
    `base` dict - the exact bug acord-new hit when this alias was missing:
    every one of its fields rendered blank."""
    data = build_synthetic_data(fake_variant_alias, "general")
    assert data["chief_complaint"] and data["encounter_type"]


def test_validate_document_structure_rejects_an_unknown_doc_type():
    # Used to return `[]` required fields for anything unrecognised and
    # therefore report valid=True, so a typo'd or brand-new doc_type always
    # passed validation and only failed later, as an empty document.
    result = tools.validate_document_structure("not-a-real-doc-type", data={})
    assert result["valid"] is False
    assert "Unknown doc_type" in result["error"]


def test_validate_document_structure_accepts_a_variant_doc_type(fake_variant_alias):
    data = build_synthetic_data(fake_variant_alias, "general")
    assert tools.validate_document_structure(fake_variant_alias, data=data)["valid"] is True


# --- recreate mode -------------------------------------------------------
# Recreate re-tells the UPLOADED document under a different scenario: same
# people and identifiers, freshly generated scenario content. It previously
# called generate_synthetic_data and produced an entirely unrelated document,
# carrying nothing at all from the reference.


def test_recreate_carries_identity_but_regenerates_scenario_content():
    carried = {
        "patient_name": "Aarav Sharma",
        "dob": "04/11/1978",
        "mrn": "4471902",
        "policy_number": "POLXY7742119",
        "physician_name": "Dr. Meera Iyer",
    }
    summary = tools.recreate_document_data(
        doc_type="medical-record", scenario="medical_malpractice", carried_values=carried
    )
    assert summary["status"] == "staged" and summary["carried_keys"] == len(carried)
    data = tools.get_staged_doc_data()

    for key, value in carried.items():
        assert data[key] == value, f"{key} must be carried from the reference"

    # The scenario, not the reference, drives the clinical content.
    assert data["scenario"] == "medical_malpractice"
    malpractice_codes = {c[0] for c in build_synthetic_data("medical-record", "medical_malpractice")["diagnosis_codes"]}
    assert {c[0] for c in data["diagnosis_codes"]} <= malpractice_codes


def test_recreate_merges_nested_dicts_key_by_key():
    """A partial address must override only the keys supplied, not replace
    the whole dict and blank out street/state/zip."""
    tools.recreate_document_data(
        doc_type="medical-record", scenario="general", carried_values={"address": {"city": "Pune"}}
    )
    data = tools.get_staged_doc_data()
    assert data["address"]["city"] == "Pune"
    assert data["address"]["street"] and data["address"]["state"] and data["address"]["zip"]


def test_recreate_reports_unmapped_keys_instead_of_dropping_them():
    # A mistyped key would otherwise leave the recreated document quietly
    # carrying random data where the reference's real value belonged.
    summary = tools.recreate_document_data(
        doc_type="medical-record",
        scenario="general",
        carried_values={"patient_name": "Aarav Sharma", "claimant": "wrong key name"},
    )
    assert summary["unmapped_keys"] == ["claimant"]
    assert tools.get_staged_doc_data()["patient_name"] == "Aarav Sharma"


def test_recreate_with_no_carried_values_is_still_valid_data():
    summary = tools.recreate_document_data(
        doc_type="medical-record", scenario="general", carried_values={}
    )
    assert summary["unmapped_keys"] == []
    # No data argument - validate reads the staged document.
    assert tools.validate_document_structure("medical-record")["valid"] is True


# --- staged document data ------------------------------------------------
# The generators used to RETURN the full data dict, which the model then had
# to re-emit verbatim as render_document_to_pdf(data=...) - ~670 output tokens
# per document, the slowest kind of token to produce, spent re-transmitting
# something a deterministic generator had just produced. The data now stays
# server-side; only field NAMES cross into the model's context.


def test_generate_synthetic_data_stages_and_returns_only_field_names():
    import json

    summary = tools.generate_synthetic_data(doc_type="cms-1500", scenario="general")
    assert summary["status"] == "staged"

    staged = tools.get_staged_doc_data()
    assert staged["patient_name"] and summary["field_count"] == len(staged)

    # No VALUES may appear in what the model receives.
    payload = json.dumps(summary, default=str)
    assert staged["patient_name"] not in payload
    assert staged["claim_number"] not in payload
    assert len(payload) < len(json.dumps(staged, default=str)) / 2


def test_revise_document_data_changes_only_what_it_is_given():
    tools.generate_synthetic_data(doc_type="medical-record", scenario="general")
    before = dict(tools.get_staged_doc_data())

    result = tools.revise_document_data(
        changes={"patient_name": "Aarav Sharma", "address": {"city": "Pune"}}
    )

    after = tools.get_staged_doc_data()
    assert result["unmapped_keys"] == []
    assert after["patient_name"] == "Aarav Sharma"
    assert after["address"]["city"] == "Pune"
    assert after["address"]["street"] == before["address"]["street"]
    assert after["mrn"] == before["mrn"]


def test_revise_document_data_reports_a_field_that_does_not_exist():
    tools.generate_synthetic_data(doc_type="medical-record", scenario="general")
    result = tools.revise_document_data(changes={"no_such_field": "x"})
    assert result["unmapped_keys"] == ["no_such_field"]


def test_rendering_before_generating_fails_loudly():
    tools.clear_staged_doc_data()
    with pytest.raises(ValueError, match="No document data has been staged"):
        tools.render_document_to_pdf(template_name="medical_record")


def test_recreate_rejects_a_flat_value_for_a_nested_dict_field():
    # The exact bug this guards: a caller extracting text off a reference
    # document naturally carries an address as one flat string
    # ("1500 Jefferson Street SE, Olympia, WA 98504"), but producer_address
    # is a {street, city, state, zip} dict. Applying the string used to
    # silently replace the whole dict, so every template line reading
    # producer_address.street crashed with "'str object' has no attribute
    # 'street'" - far from where the bad data was actually introduced.
    summary = tools.recreate_document_data(
        doc_type="acord-25", scenario="general",
        carried_values={"producer_address": "1500 Jefferson Street SE, Olympia, WA 98504"},
    )
    data = tools.get_staged_doc_data()

    assert summary["unmapped_keys"] == ["producer_address"]
    assert isinstance(data["producer_address"], dict)
    assert data["producer_address"]["street"]


def test_recreate_still_merges_a_properly_shaped_nested_dict():
    tools.recreate_document_data(
        doc_type="acord-25", scenario="general",
        carried_values={"producer_address": {"street": "1500 Jefferson Street SE"}},
    )
    data = tools.get_staged_doc_data()

    assert data["producer_address"]["street"] == "1500 Jefferson Street SE"
    assert data["producer_address"]["city"]  # untouched sub-keys survive
