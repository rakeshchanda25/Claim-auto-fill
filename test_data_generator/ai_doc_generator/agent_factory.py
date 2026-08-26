import os
from pathlib import Path

from .tools import (
    analyze_reference_document,
    build_packet,
    fill_pdf_form_tool,
    fill_pdf_widgets,
    fit_grid_row,
    flow_text_into_widgets,
    generate_synthetic_data,
    get_pdf_form_fields,
    inspect_pdf_form_structure,
    inspect_region_image,
    render_document_to_pdf,
    validate_document_structure,
    verify_pdf_fill,
)

_PROJECT_ROOT = Path(__file__).parent.parent


def create_doc_generator_agent():
    try:
        from andromeda.config import (
            AgentConfig,
            MiddlewareConfig,
            ModelConfig,
            WorkspaceAgentConfig,
        )
        from andromeda.config.config import CompliancePatternsConfig, PromptInjectionPatternsConfig
        from andromeda.core import WorkspaceAgent
        from andromeda.tools.toolkit import register_tool
        from andromeda.workspace import (
            BubblewrapProcessSettings,
            DirectorySeed,
            FilePolicy,
            ShellPolicy,
            WorkspacePolicy,
            WorkspaceSession,
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to import Andromeda framework: {e}. "
            "If using editable install, re-install or check permissions."
        ) from e

    _TOOLS = [
        generate_synthetic_data,
        render_document_to_pdf,
        fill_pdf_form_tool,
        get_pdf_form_fields,
        analyze_reference_document,
        build_packet,
        validate_document_structure,
        # dynamic-form-fill: works on any AcroForm template, no per-form config
        inspect_pdf_form_structure,
        inspect_region_image,
        flow_text_into_widgets,
        fit_grid_row,
        fill_pdf_widgets,
        verify_pdf_fill,
    ]

    for _t in _TOOLS:
        try:
            register_tool(_t)
        except Exception:
            pass

    model = ModelConfig(
        name="openai/qwen3.6:27b",
        provider="litellm",
        other_args={
            "temperature": 0.3,
            "timeout": 120,
        },
    )


    middleware = MiddlewareConfig(
        enabled=True,
        tool_error_handler=True,
        guardrails=MiddlewareConfig.GuardrailOptions(
            input=True,
            output=True,
            tool=False,
            prompt_injection_patterns=PromptInjectionPatternsConfig(
                patterns=[
                    r"ignore.*(previous|above|earlier).*instructions",
                    r"disregard.*(system|prompt)",
                    r"reveal.*system.*prompt",
                    r"bypass.*(guardrail|safety|policy)",
                ]
            ),
            compliance_patterns=CompliancePatternsConfig(
                patterns=[
                    r"\bfalsif(?:y|ied|ication)\b",
                    r"\bmisrepresent(?:ation)?\b",
                    r"guaranteed\s+(approval|coverage|payout)",
                    r"cannot\s+be\s+denied",
                ]
            ),
            blocked_message="Request blocked by IDP document generation policy.",
        ),
    )

    backend = os.environ.get("WORKSPACE_BACKEND", "ephemeral_fs")
    policy = WorkspacePolicy(
        read_only=False,
        enable_shell=True,
        file=FilePolicy(max_file_size_mb=20, allow_symlinks=False, protect_root=True),
        shell=ShellPolicy(
            allowed_commands=("python3", "weasyprint"),
            network_enabled=False,
            timeout_seconds=120,
            max_output_chars=20_000,
            enable_background_shell=False,
        ),
    )

    settings = None
    if backend == "bubblewrap_process":
        settings = BubblewrapProcessSettings(
            network_mode="none",
            inherit_host_env=False,
        )

    session = WorkspaceSession.create(
        backend=backend,
        seed=DirectorySeed(source_dir=str(_PROJECT_ROOT)),
        policy=policy,
        settings=settings,
    )

    read_only_tools = list(session.tools(tool_profile="read_only").values())
    write_tools = list(session.tools(tool_profile="minimal").values())
    shell_tools = list(session.tools().values())


    doc_analyst = AgentConfig(
        name="doc-analyst",
        model=model,
        prompt=(
            "You analyze reference insurance documents. Identify document type, section structure, "
            "field labels, table layouts, and typography conventions. Report findings as structured JSON. "
            "Do not write files."
        ),
        tools=read_only_tools,
        middleware=middleware,
    )

    packet_builder = AgentConfig(
        name="packet-builder",
        model=model,
        prompt=(
            "You build document packet components. For each component, generate synthetic data, "
            "populate the matching Jinja2 template, and write the HTML to /output/<name>.html."
        ),
        tools=write_tools,
        middleware=middleware,
    )

    renderer = AgentConfig(
        name="renderer",
        model=model,
        prompt=(
            "You convert HTML files in /output/ to PDF using WeasyPrint. "
            "Run: python3 -m weasyprint /output/<name>.html /output/<name>.pdf. "
            "Return the list of generated PDF paths."
        ),
        tools=shell_tools,
        middleware=middleware,
    )

    specialists = [doc_analyst, packet_builder, renderer]

    config = WorkspaceAgentConfig(
        name="doc-generator",
        model=model,
        prompt=(
            "You are the lead insurance document generation agent for IDP testing. "
            "ALWAYS load the matching skill via load_skill before any generation step. "
            "For single documents: call generate_synthetic_data, validate_document_structure, "
            "then render_document_to_pdf. "
            "For packets: call build_packet to get all components, then render_document_to_pdf for each. "
            "For recreate mode: delegate reference analysis to doc-analyst first. "
            "For FILLING a supplied fillable PDF form: load_skill('dynamic-form-fill') and follow "
            "it. That skill works on any AcroForm template, including ones never seen before - "
            "discover the layout at runtime with inspect_pdf_form_structure (and "
            "inspect_region_image when a label is unclear). Never assume a form's fields, and "
            "never infer a field's meaning from its raw internal name. "
            "Return final output as a JSON string with key 'pdf_bytes_b64' (base64-encoded PDF) "
            "or 'components' (list of {label, pdf_bytes_b64}) for packets."
        ),
        tools=_TOOLS,
        workspace_backend=backend,
        skill_sources=["/skills"],
        skills_backend="filesystem",
        middleware=middleware,
        allow_parallel_agents=False,
        allow_async_tasks=False,
        recursion_limit=300,
        read_only=False,
    )


    return WorkspaceAgent(
        config,
        agents=specialists,
        session=session,
        min_agents=3,
    )
