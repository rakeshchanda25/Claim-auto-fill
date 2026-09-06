"""Covers the logic that has actually broken before.

Every check here renders through the real Jinja templates under StrictUndefined,
which is what catches a field the data layer forgot to supply. PDF generation
itself is not exercised - WeasyPrint needs system libraries that are absent on
many dev machines, and it is the one step with no project logic in it.
"""

import json
from pathlib import Path

import pytest

from ai_doc_generator import tools
from ai_doc_generator.registry import DOC_TYPES, PACKET_REGISTRY, SCENARIO_REGISTRY
from renderers import render_html
from renderers.components import get_components
from renderers.synthetic_data import build_synthetic_data, resolve_doc_type

DOC_TYPE_IDS = [d["id"] for d in DOC_TYPES]

# Every (doc_type, scenario) a user can actually ask for: each type against every
# scenario a packet containing it supports, plus "general" for all of them.
DOC_SCENARIOS = sorted({
    (doc_id, "general") for doc_id in DOC_TYPE_IDS
} | {
    (component["doc_type"], scenario)
    for packet in PACKET_REGISTRY.values()
    for component in packet["components"]
    for scenario in packet["compatible_scenarios"]
})


@pytest.fixture(autouse=True)
def clean_run():
    """Each test starts with no staged state and leaves none behind."""
    tools.begin_run()
    yield
    tools.end_run()


@pytest.fixture(scope="session")
def claim_fixture():
    """A real captured Guidewire response, unwrapped to its `data` payload."""
    path = Path(__file__).parent / "fixtures" / "guidewire_claim.json"
    return json.loads(path.read_text(encoding="utf-8"))["data"]


# ---------------------------------------------------------------------------
# Registry consistency
# ---------------------------------------------------------------------------

def test_every_doc_type_has_a_template_and_a_skill():
    root = Path(__file__).parent.parent
    for doc_id in DOC_TYPE_IDS:
        assert (root / "renderers" / "templates" / f"{doc_id.replace('-', '_')}.html").is_file(), doc_id
        assert (root / "skills" / doc_id / "SKILL.md").is_file(), doc_id


def test_every_packet_component_is_a_known_doc_type():
    for name, packet in PACKET_REGISTRY.items():
        for component in packet["components"]:
            assert component["doc_type"] in DOC_TYPE_IDS, f"{name} -> {component['doc_type']}"
        for scenario in packet["compatible_scenarios"]:
            assert scenario in SCENARIO_REGISTRY, f"{name} -> {scenario}"


def test_every_doc_type_has_required_fields_defined():
    for doc_id in DOC_TYPE_IDS:
        assert resolve_doc_type(doc_id) in tools._REQUIRED_FIELDS, doc_id


# ---------------------------------------------------------------------------
# Generation and rendering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("doc_type,scenario", DOC_SCENARIOS, ids=lambda v: str(v))
def test_document_builds_and_renders(doc_type, scenario):
    """The main sweep: real data through the real template under StrictUndefined,
    so any field the template reads and the data layer never sets fails here."""
    data = build_synthetic_data(doc_type, scenario)
    html = render_html(doc_type, data)
    assert len(html) > 500, f"{doc_type}/{scenario} rendered suspiciously little HTML"


@pytest.mark.parametrize("doc_type,scenario", DOC_SCENARIOS, ids=lambda v: str(v))
def test_generated_document_passes_its_own_validation(doc_type, scenario):
    tools.generate_synthetic_data(doc_type, scenario)
    result = tools.validate_document_structure(doc_type)
    assert result["valid"], f"{doc_type}/{scenario} missing {result['missing_fields']}"


@pytest.mark.parametrize("doc_type,scenario", DOC_SCENARIOS, ids=lambda v: str(v))
def test_components_are_registered_and_used(doc_type, scenario):
    components = get_components(doc_type, scenario)
    assert components, f"no component composition for {doc_type}/{scenario}"
    assert build_synthetic_data(doc_type, scenario)["components"] == components


def test_police_report_drops_vehicle_sections_for_a_property_scenario():
    """The bug this component system was built for: a fire-damage report was
    rendering empty Driver 1 / Driver 2 vehicle tables."""
    fire = render_html("police-report", build_synthetic_data("police-report", "fire_damage"))
    crash = render_html("police-report", build_synthetic_data("police-report", "rear_end_collision"))

    assert "Driver 1" not in fire
    assert "Driver 1" in crash


def test_unknown_scenario_still_produces_a_complete_document():
    """Any scenario string can reach a doc type, including one that has nothing
    to do with it. It must fall back to a full document, never an empty one."""
    assert get_components("police-report", "chronic_medication") == get_components("police-report", "general")


# ---------------------------------------------------------------------------
# Claim data
# ---------------------------------------------------------------------------

CLAIM_FIELDS = {
    "insured_name": "Aditya Krishna",
    "claim_number": "000-00-053109",
    "policy_number": "9185479590",
    "loss_location": "742 Evergreen Terrace, Springfield, IL",
    "loss_date": "2026-06-06T00:00:00.000Z",
}


@pytest.mark.parametrize("doc_type", DOC_TYPE_IDS)
def test_claim_identity_reaches_every_document_type(doc_type):
    """The claimant is called patient_name here, plaintiff_name there, and is
    nested under employee/parties_involved elsewhere. A plain key overlay only
    reaches whichever type happens to match, which is the bug this guards."""
    tools.begin_run(custom_fields=dict(CLAIM_FIELDS))
    tools.generate_synthetic_data(doc_type, "general")
    rendered = render_html(doc_type, tools.current_run().doc_data)

    # acord-25 is a certificate of insurance: it names the insured but has no
    # claim number field at all, so only the identity assertion applies.
    assert CLAIM_FIELDS["insured_name"] in rendered, f"{doc_type} lost the claimant's name"


def test_claim_data_overrides_generated_values():
    tools.begin_run(custom_fields=dict(CLAIM_FIELDS))
    tools.generate_synthetic_data("medical-record", "general")
    data = tools.current_run().doc_data
    assert data["patient_name"] == CLAIM_FIELDS["insured_name"]


def test_explicit_tool_arguments_merge_over_staged_values():
    """The model may pass claim fields too. Anything it adds merges on top;
    anything it omits still applies from the staged copy."""
    tools.begin_run(custom_fields={"insured_name": "Staged Name", "claim_number": "STAGED-1"})
    tools.generate_synthetic_data("medical-record", "general",
                                  custom_fields={"insured_name": "Explicit Name"})
    data = tools.current_run().doc_data
    assert data["patient_name"] == "Explicit Name"   # explicit wins
    assert data["claim_number"] == "STAGED-1"        # staged still applies


def test_loss_date_anchors_every_generated_date():
    """A report cannot predate the loss it reports. Dates are derived from the
    anchor before generation rather than patched afterwards, so every derived
    field moves together."""
    data = build_synthetic_data("police-report", "rear_end_collision",
                                anchor_date="2026-06-06T00:00:00.000Z")
    assert "2026" in data["incident_date"]
    assert "2026" in data["report_date"]
    assert "2026" in str(data["local_report_number"])


# ---------------------------------------------------------------------------
# Packets
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("packet_name", sorted(PACKET_REGISTRY))
def test_packet_components_agree_on_every_shared_concept(packet_name):
    """Every document in a packet describes ONE claim, so wherever two of them
    carry the same concept they must carry the same value - whatever each calls
    it. Documents that lack a concept simply do not constrain it."""
    scenario = PACKET_REGISTRY[packet_name]["compatible_scenarios"][0]
    tools.build_packet(packet_name, scenario)
    plan = tools.current_run().packet_plan

    for concept in tools._ALIASES:
        seen = {}
        for component in plan:
            value = tools._read_concept(component["data"], component["doc_type"], concept)
            if value is not None:
                seen[component["label"]] = value
        assert len(set(seen.values())) <= 1, (
            f"{packet_name}: components disagree on {concept!r} -> {seen}"
        )


def test_auto_packet_agrees_on_the_incident_date_across_field_names():
    """A police report calls it incident_date and an auto loss notice calls it
    accident_date. Before concept syncing these were independently generated,
    so one packet described two different crashes."""
    tools.build_packet("auto-accident-packet", "rear_end_collision")
    by_type = {c["doc_type"]: c["data"] for c in tools.current_run().packet_plan}
    assert by_type["police-report"]["incident_date"] == by_type["auto-accident-report"]["accident_date"]


def test_property_packet_agrees_on_the_loss_date_across_field_names():
    tools.build_packet("property-claim-packet", "fire_damage")
    by_type = {c["doc_type"]: c["data"] for c in tools.current_run().packet_plan}
    assert by_type["property-loss-notice"]["loss_date"] == by_type["police-report"]["incident_date"]


def test_medical_packet_agrees_on_admission_and_physician():
    """discharge-summary says date_of_admission, ub-04 says admission_date; the
    prescribing/attending doctor is named differently again on each form."""
    tools.build_packet("medical-packet", "hospital_admission")
    by_type = {c["doc_type"]: c["data"] for c in tools.current_run().packet_plan}

    assert by_type["discharge-summary"]["date_of_admission"] == by_type["ub-04"]["admission_date"]
    assert by_type["discharge-summary"]["date_of_discharge"] == by_type["ub-04"]["discharge_date"]
    assert by_type["medical-record"]["physician_name"] == by_type["ub-04"]["attending_physician_name"]


def test_provider_name_is_not_synced_across_its_two_meanings():
    """provider_name is the treating clinician on an EOB but the facility on a
    UB-04. Syncing it as one concept would print a doctor in a hospital field."""
    tools.build_packet("medical-packet", "hospital_admission")
    by_type = {c["doc_type"]: c["data"] for c in tools.current_run().packet_plan}
    assert by_type["ub-04"]["provider_name"] == by_type["medical-record"]["hospital"]


@pytest.mark.parametrize("packet_name", sorted(PACKET_REGISTRY))
def test_every_packet_component_renders(packet_name):
    scenario = PACKET_REGISTRY[packet_name]["compatible_scenarios"][0]
    tools.build_packet(packet_name, scenario)
    for component in tools.current_run().packet_plan:
        html = render_html(component["template_name"], component["data"])
        assert len(html) > 500, f"{packet_name}/{component['label']}"


def test_packet_applies_claim_data_to_every_component():
    tools.begin_run(custom_fields=dict(CLAIM_FIELDS))
    tools.build_packet("auto-accident-packet", "rear_end_collision")
    for component in tools.current_run().packet_plan:
        rendered = render_html(component["template_name"], component["data"])
        assert CLAIM_FIELDS["insured_name"] in rendered, component["label"]


def test_claim_narrative_only_reaches_documents_that_have_somewhere_for_it():
    """Notes and excerpts go into scenario_facts, which not every type has.
    Types without it must be left alone rather than grown a new section."""
    tools.begin_run(custom_fields={
        **CLAIM_FIELDS,
        "_claim_description": "Insured was rear-ended at a stop light.",
        "_document_excerpts": [
            {"category": "police report|accident report", "source": "Report.pdf",
             "text": "Unit 1 was struck from behind while stopped at the signal."},
        ],
    })
    tools.build_packet("auto-accident-packet", "rear_end_collision")
    by_type = {c["doc_type"]: c["data"] for c in tools.current_run().packet_plan}

    police = by_type["police-report"]
    assert any(f["label"] == "Claim Description" for f in police["scenario_facts"])
    assert any("Excerpt" in f["label"] for f in police["scenario_facts"])

    # A certificate of insurance has no narrative section - it must stay clean.
    assert "scenario_facts" not in by_type["acord-25"] or not any(
        f["label"] == "Claim Description" for f in by_type["acord-25"].get("scenario_facts", [])
    )


# ---------------------------------------------------------------------------
# Guidewire mapping
# ---------------------------------------------------------------------------

def _context_from(claim_fixture):
    from claim_context import ClaimContext

    return ClaimContext(
        details=claim_fixture["claim_details"],
        policy=claim_fixture["policy_details"],
        contacts=claim_fixture["contacts"]["contacts"],
        notes=[n["body_summary"] for n in claim_fixture["notes"]["notes"] if n.get("body_summary")],
    )


def test_claim_response_maps_onto_document_fields(claim_fixture):
    """Guards the mapping against a real captured API response."""
    from claim_context import claim_to_fields

    fields = claim_to_fields(_context_from(claim_fixture))
    details = claim_fixture["claim_details"]

    assert fields["claim_number"] == details["claim_number"]
    assert fields["insured_name"] == details["insured"]
    assert fields["loss_date"] == details["loss_date"]
    assert fields["policy_type"] == claim_fixture["policy_details"]["policy_type"]
    # Empty values must be dropped so they fall through to generated data
    # rather than blanking the field. This claim's Agent contact has no name.
    assert all(v not in (None, "") for v in fields.values())
    assert "producer_name" not in fields


def test_claim_facts_from_a_real_response_reach_a_document(claim_fixture):
    """End to end on real data: response -> field mapping -> rendered document."""
    from claim_context import claim_to_fields

    fields = claim_to_fields(_context_from(claim_fixture))
    tools.begin_run(custom_fields=fields, anchor_date=fields["loss_date"])
    tools.generate_synthetic_data("police-report", "rear_end_collision")
    data = tools.current_run().doc_data

    assert data["parties_involved"][0]["name"] == claim_fixture["claim_details"]["insured"]
    assert data["claim_number"] == claim_fixture["claim_details"]["claim_number"]
    # loss_date is 2026-08-01; every derived date must sit on that year.
    assert "2026" in data["incident_date"]
    assert "2026" in data["report_date"]
    assert claim_fixture["claim_details"]["insured"] in render_html("police-report", data)


def test_claim_notes_are_available_as_narrative(claim_fixture):
    from claim_context import claim_narrative

    narrative = claim_narrative(_context_from(claim_fixture))
    assert "Adjuster's claim description:" in narrative


# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------

def test_agent_config_has_no_env_placeholders():
    """Config values are literal by design - there is no .env file. A ${VAR} here
    would not be substituted and would reach the model client as raw text."""
    from ai_doc_generator.agent_factory import _AGENT_CONFIG

    config_lines = [
        line for line in _AGENT_CONFIG.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    assert "${" not in chr(10).join(config_lines)


def test_agent_config_loads_and_is_usable():
    andromeda_config = pytest.importorskip(
        "andromeda.config", reason="Andromeda framework not installed"
    )
    from ai_doc_generator.agent_factory import _AGENT_CONFIG

    config = andromeda_config.WorkspaceAgentConfig.load_from_file(
        str(_AGENT_CONFIG), resolve_tools=False
    )
    assert config.name == "doc-generator"
    assert config.model.name and config.prompt.strip()
    # These reach the model client and must not arrive as strings.
    assert isinstance(config.model.other_args["temperature"], float)
    assert isinstance(config.model.other_args["timeout"], int)
    # The PII guardrail is disabled deliberately: its default phone pattern
    # matches any bare 10-digit number, i.e. every policy and claim number.
    assert config.middleware.guardrails.data_patterns.phone == "(?!)"


def test_configured_backend_is_one_the_framework_accepts():
    """WorkspaceSession.create rejects "auto" - it is a config-level default the
    framework expands only when it builds the session itself. We build our own,
    so the YAML has to name a concrete backend. Shipping "auto" raised
    WorkspaceCompatibilityError at runtime."""
    pytest.importorskip("andromeda.workspace", reason="Andromeda framework not installed")
    from andromeda.config import WorkspaceAgentConfig
    from andromeda.workspace.backends import get_backend_capabilities

    from ai_doc_generator.agent_factory import _AGENT_CONFIG

    config = WorkspaceAgentConfig.load_from_file(str(_AGENT_CONFIG), resolve_tools=False)
    assert config.workspace_backend != "auto"
    # Raises WorkspaceCompatibilityError for a name the framework does not know.
    assert get_backend_capabilities(config.workspace_backend).supports_file_tools


def test_claim_id_is_found_in_free_text():
    from claim_context import extract_claim_id

    assert extract_claim_id("please use claim 000-00-053109 for this") == "000-00-053109"
    assert extract_claim_id("cc:12345 needs a police report") == "cc:12345"
    assert extract_claim_id("just a normal request") is None


# ---------------------------------------------------------------------------
# Dynamic packets - the model chooses which documents a claim needs, instead
# of a pre-defined named packet.
# ---------------------------------------------------------------------------

def test_build_packet_accepts_a_model_chosen_component_list():
    result = tools.build_packet(components=["police-report", "medical-record", "acord-25"],
                                scenario="rear_end_collision")
    assert result["packet"] == "custom"
    assert result["component_count"] == 3
    plan = tools.current_run().packet_plan
    assert [c["doc_type"] for c in plan] == ["police-report", "medical-record", "acord-25"]


def test_dynamic_packet_components_sync_identity_like_a_named_packet():
    """The sync engine (_sync_component / _seed_shared) must not care whether
    the component list came from PACKET_REGISTRY or the model - same identity
    agreement either way."""
    tools.build_packet(components=["police-report", "auto-accident-report", "medical-record"],
                       scenario="rear_end_collision", custom_fields={"insured_name": "Aditya Krishna"})
    plan = tools.current_run().packet_plan
    for comp in plan:
        name = tools._read_concept(comp["data"], comp["doc_type"], "claimant")
        assert name == "Aditya Krishna", f"{comp['doc_type']} disagrees"


def test_build_packet_rejects_a_document_type_this_system_cannot_generate():
    with pytest.raises(ValueError, match="Unknown document type"):
        tools.build_packet(components=["police-report", "not-a-real-doc-type"])


def test_build_packet_requires_either_a_packet_name_or_components():
    with pytest.raises(ValueError, match="needs either packet_name"):
        tools.build_packet()


def test_named_packet_path_is_unaffected_by_the_dynamic_addition():
    result = tools.build_packet(packet_name="medical-packet", scenario="surgery")
    assert result["packet"] == "medical-packet"
    assert result["component_count"] == len(PACKET_REGISTRY["medical-packet"]["components"])


# ---------------------------------------------------------------------------
# Packet prompts: named vs. dynamic, fixed vs. auto scenario
# ---------------------------------------------------------------------------

def _packet_request(doc_type, scenario, **kw):
    from ai_doc_generator.config import GenerationRequest

    return GenerationRequest(doc_type=doc_type, mode="packet", scenario=scenario, **kw)


def test_named_packet_with_fixed_scenario_prompt_is_unchanged():
    """The common case must not change at all - this is the exact text the
    original single-branch implementation produced."""
    from ai_doc_generator.prompt_builder import build_generation_prompt

    req = _packet_request("auto-accident-packet", "rear_end_collision")
    prompt = build_generation_prompt(req)
    assert "build_packet(packet_name='auto-accident-packet', scenario='rear_end_collision'" in prompt
    assert "render_packet()" in prompt
    assert "decide the right set of documents" not in prompt


def test_named_packet_with_auto_scenario_lets_model_pick_from_its_own_list():
    from ai_doc_generator.prompt_builder import build_generation_prompt

    req = _packet_request("auto-accident-packet", "auto")
    prompt = build_generation_prompt(req)
    for scenario in PACKET_REGISTRY["auto-accident-packet"]["compatible_scenarios"]:
        assert scenario in prompt
    assert "build_packet(packet_name='auto-accident-packet', scenario=<your pick>" in prompt


def test_no_packet_with_fixed_scenario_lists_every_document_type():
    from ai_doc_generator.prompt_builder import build_generation_prompt

    req = _packet_request(None, "fire_damage")
    prompt = build_generation_prompt(req)
    for doc_id in DOC_TYPE_IDS:
        assert doc_id in prompt
    assert "build_packet(components=[<your chosen document type ids>], scenario='fire_damage'" in prompt
    assert "standard US insurance claims practice" in prompt


def test_no_packet_with_auto_scenario_lists_documents_and_scenarios():
    from ai_doc_generator.prompt_builder import build_generation_prompt

    req = _packet_request(None, "auto")
    prompt = build_generation_prompt(req)
    for doc_id in DOC_TYPE_IDS:
        assert doc_id in prompt
    for scenario_id in SCENARIO_REGISTRY:
        assert scenario_id in prompt
    assert "build_packet(components=[<your chosen document type ids>], scenario=<the scenario you picked>" in prompt


def test_packet_prompt_still_carries_claim_facts_for_the_model_to_reason_on():
    """The model can only decide sensibly if it can see the claim's loss type,
    cause and narrative - both already flow through the shared tail block."""
    from ai_doc_generator.prompt_builder import build_generation_prompt

    req = _packet_request(None, "auto",
                          custom_fields={"loss_type": "Property", "loss_cause": "Fire"},
                          user_input="Adjuster's claim description: kitchen fire, smoke damage")
    prompt = build_generation_prompt(req)
    assert "loss_type" in prompt and "Property" in prompt
    assert "kitchen fire" in prompt


# ---------------------------------------------------------------------------
# The route: doc_type is optional for packets, required for generate/recreate
# ---------------------------------------------------------------------------

def test_generation_request_allows_no_doc_type_for_packet_mode():
    from ai_doc_generator.config import GenerationRequest

    req = GenerationRequest(doc_type=None, mode="packet", scenario="auto")
    assert req.doc_type is None
