import pytest

from ai_doc_generator import tools
from ai_doc_generator.registry import FIXED_FORM_DOC_TYPES, LAYOUT_AXIS, US_STATES, layout_axis
from renderers import render_html
from renderers.components import shape_for
from renderers.layout_validator import validate_layout
from renderers.layouts import all_layouts, available_layouts, get_layout, normalize_key
from renderers.synthetic_data import build_synthetic_data

POLICE_SCENARIOS = ["rear_end_collision", "intersection_accident", "hit_and_run",
                    "fire_damage", "water_damage", "theft", "wind_damage", "general"]
LAYOUT_STATES = available_layouts("police-report")


@pytest.fixture(autouse=True)
def clean_run():
    tools.begin_run()
    yield
    tools.end_run()


@pytest.mark.parametrize("doc_type", FIXED_FORM_DOC_TYPES)
def test_national_forms_never_vary_by_jurisdiction(doc_type):
    assert doc_type not in LAYOUT_AXIS
    assert layout_axis(doc_type) is None
    data = build_synthetic_data(doc_type, "general", jurisdiction="TX")
    assert data["layout_key"] is None
    assert get_layout(doc_type, "TX") is None
    assert not available_layouts(doc_type)


def test_fixed_forms_render_identically_whatever_jurisdiction_is_asked_for():
    for doc_type in FIXED_FORM_DOC_TYPES:
        tools.begin_run(jurisdiction="TX")
        tools.generate_synthetic_data(doc_type, "general", seed=11)
        with_tx = render_html(doc_type, tools.current_run().doc_data)
        tools.begin_run()
        tools.generate_synthetic_data(doc_type, "general", seed=11)
        without = render_html(doc_type, tools.current_run().doc_data)
        assert with_tx == without, f"{doc_type} changed with a jurisdiction set"


def test_author_layout_refuses_a_fixed_national_form():
    with pytest.raises(ValueError, match="fixed national form"):
        tools.author_layout("cms-1500", "TX", "<html>x</html>")


@pytest.mark.parametrize("state", LAYOUT_STATES)
@pytest.mark.parametrize("scenario", POLICE_SCENARIOS)
def test_state_layout_passes_the_validation_gate(state, scenario):
    data = build_synthetic_data("police-report", scenario, jurisdiction=state)
    html = get_layout("police-report", state, data["layout_shape"])
    assert html, f"no layout for {state}"
    assert validate_layout(html, data, tools._REQUIRED_FIELDS["police-report"]) == []


@pytest.mark.parametrize("state", LAYOUT_STATES)
@pytest.mark.parametrize("scenario", POLICE_SCENARIOS)
def test_state_layout_matches_the_scenario_shape(state, scenario):
    data = build_synthetic_data("police-report", scenario, jurisdiction=state)
    out = render_html("police-report", data)
    is_auto = shape_for("police-report", scenario) == "auto"
    assert ("VIN" in out) is is_auto, f"{state}/{scenario} vehicle sections should be {is_auto}"


def test_jurisdiction_changes_the_rendered_form():
    import random

    from faker import Faker

    renders = {}
    for state in LAYOUT_STATES:
        Faker.seed(3)
        random.seed(3)
        data = build_synthetic_data("police-report", "rear_end_collision", jurisdiction=state)
        renders[state] = render_html("police-report", data)
    assert len(set(renders.values())) == len(LAYOUT_STATES)
    assert "TEXAS PEACE OFFICER" in renders["TX"]
    assert "CHP 555" in renders["CA"]


def test_unknown_state_falls_back_to_the_generic_template():
    data = build_synthetic_data("police-report", "rear_end_collision", jurisdiction="WY")
    out = render_html("police-report", data)
    assert "TEXAS PEACE OFFICER" not in out and "CHP 555" not in out
    assert len(out) > 500


def test_every_layout_carries_the_specimen_marking():
    for doc_type, states in all_layouts().items():
        for state in states:
            for scenario in ("rear_end_collision", "fire_damage"):
                data = build_synthetic_data(doc_type, scenario, jurisdiction=state)
                assert "SPECIMEN" in render_html(doc_type, data)


def test_validator_rejects_a_layout_that_drops_a_required_field():
    data = build_synthetic_data("police-report", "rear_end_collision", jurisdiction="TX")
    stripped = "<html><body>SPECIMEN " + ("filler " * 200) + "</body></html>"
    problems = validate_layout(stripped, data, tools._REQUIRED_FIELDS["police-report"])
    assert any("incident_number" in p for p in problems)


def test_validator_rejects_a_layout_missing_the_specimen_marking():
    data = build_synthetic_data("police-report", "rear_end_collision", jurisdiction="TX")
    html = "<html><body>{{ incident_number }} " + ("filler " * 200) + "</body></html>"
    assert any("SPECIMEN" in p for p in validate_layout(html, data, ()))


def test_validator_rejects_a_layout_that_does_not_render():
    data = build_synthetic_data("police-report", "rear_end_collision", jurisdiction="TX")
    problems = validate_layout("{{ no_such_field }}", data, ())
    assert problems and "failed to render" in problems[0]


def test_layout_keys_are_sanitised():
    assert normalize_key("tx") == "TX"
    assert normalize_key("../../etc/passwd") is None
    assert normalize_key("") is None
    assert normalize_key(None) is None


def test_every_state_in_the_registry_is_selectable():
    assert len(US_STATES) == 50
    codes = [s["code"] for s in US_STATES]
    assert len(set(codes)) == 50
    assert set(LAYOUT_STATES) <= set(codes)


def test_jurisdiction_reaches_the_document_body():
    tools.begin_run(jurisdiction="TX")
    tools.generate_synthetic_data("police-report", "rear_end_collision")
    data = tools.current_run().doc_data
    assert data["layout_key"] == "TX"
    assert data["location"].endswith("TX")
