import os
import threading
from dataclasses import dataclass
from pathlib import Path

from . import tools
from .tools import (
    analyze_uploaded_reference,
    build_packet,
    fill_docx_form_controls,
    fill_pdf_form_tool,
    fill_pdf_widgets,
    fit_grid_row,
    flow_text_into_widgets,
    generate_synthetic_data,
    get_pdf_form_fields,
    inspect_docx_form_structure,
    inspect_pdf_form_structure,
    inspect_region_image,
    render_document_to_pdf,
    validate_document_structure,
    verify_docx_fill,
    verify_pdf_fill,
)

_PROJECT_ROOT = Path(__file__).parent.parent


@dataclass(frozen=True)
class ScopedDirectorySeed:
    """Seeds only specific subpaths of source_dir into the sandbox, instead
    of DirectorySeed's whole-tree copy (it has no include/exclude option -
    andromeda/workspace/seeds.py). This project's root also holds test/
    output PDFs, __pycache__, and old experimental scripts that nothing in
    the sandbox ever reads - copying all of that on every agent build was
    pure waste. Composes andromeda's own DirectorySeed per subpath so the
    same symlink/size-limit checks still apply. `skills` is load-bearing:
    SkillsMiddleware reads it from the seeded sandbox root, not the host
    path directly (andromeda/core/workspace.py:~624), so it must stay.
    """

    source_dir: str
    subpaths: tuple[str, ...]
    target_path: str = "/"

    def apply(self, root, policy) -> None:
        from andromeda.workspace import DirectorySeed

        base = Path(self.source_dir)
        # andromeda's own seed-path resolver (andromeda/workspace/seeds.py
        # _resolve_seed_path) only special-cases target_path == "/" as
        # "workspace root itself" - anything else with a leading "/" is
        # treated as an OS-absolute path (e.g. the C:\ drive root on
        # Windows) and rejected as escaping the sandbox. So subpaths must be
        # passed WITHOUT a leading slash to land under workspace root.
        base_target = self.target_path.strip("/")
        for sub in self.subpaths:
            src = base / sub
            if not src.is_dir():
                continue
            target = f"{base_target}/{sub}" if base_target else sub
            DirectorySeed(source_dir=str(src), target_path=target).apply(root, policy)


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
        analyze_uploaded_reference,
        build_packet,
        validate_document_structure,
        # dynamic-form-fill: works on any AcroForm template, no per-form config
        inspect_pdf_form_structure,
        inspect_region_image,
        flow_text_into_widgets,
        fit_grid_row,
        fill_pdf_widgets,
        verify_pdf_fill,
        # dynamic-docx-fill: same pattern for Word content-control forms
        inspect_docx_form_structure,
        fill_docx_form_controls,
        verify_docx_fill,
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
        # Only skills/ (required - SkillsMiddleware reads it from the
        # sandbox root) and renderers/templates (used by the packet-builder/
        # renderer specialists) need to exist in the sandbox. Everything
        # else in the project (test fixtures, generated output PDFs,
        # __pycache__, frontend/, docs) is dead weight nothing here reads.
        seed=ScopedDirectorySeed(source_dir=str(_PROJECT_ROOT), subpaths=("skills", "renderers/templates")),
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
            "FILL mode and GENERATE mode are opposite tasks - never conflate them. "
            "For FILLING a supplied fillable PDF form (the user uploaded an existing document and "
            "wants ITS OWN fields populated): load_skill('dynamic-form-fill') and follow it. That "
            "skill works on any AcroForm template, including ones never seen before - discover the "
            "layout at runtime with inspect_pdf_form_structure (and inspect_region_image when a "
            "label is unclear). Never assume a form's fields, never infer a field's meaning from "
            "its raw internal name, and NEVER call generate_synthetic_data or render_document_to_pdf "
            "for this task - those produce a brand new document from a template, not a filled copy "
            "of the uploaded one. "
            "For FILLING a supplied .docx with Word content controls: load_skill('dynamic-docx-fill') "
            "and follow it instead - discover the controls at runtime with "
            "inspect_docx_form_structure. Same rule: never assume a docx's controls, and never "
            "fall back to generate_synthetic_data/render_document_to_pdf. "
            "For GENERATING a single new document from scratch (no uploaded reference): call "
            "generate_synthetic_data, validate_document_structure, then render_document_to_pdf. "
            "For packets: call build_packet to get all components, then render_document_to_pdf for each. "
            "For recreate mode: delegate reference analysis to doc-analyst first. "
            "Return final output as a JSON string with key 'pdf_bytes_b64' (base64-encoded PDF), "
            "'docx_bytes_b64' (base64-encoded docx, fill mode on a .docx only), or 'components' "
            "(list of {label, pdf_bytes_b64}) for packets."
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


# ---------------------------------------------------------------------------
# Process-wide shared agent. Building one from scratch reseeds the sandbox
# and compiles 5 LangGraph agents (supervisor + 3 specialists + 1 auto
# coworker from min_agents padding) - real, measurable overhead that was
# previously paid on every single API request. WorkspaceAgent.close()'s own
# docstring confirms reuse is supported: concurrent .run() calls are
# serialized on an internal lock rather than racing on shared state, so this
# is safe - just not concurrent (requests queue instead of running in
# parallel, which is fine for this tool's usage).
# ---------------------------------------------------------------------------

_shared_agent = None
_shared_agent_lock = threading.Lock()


def get_shared_agent():
    global _shared_agent
    if _shared_agent is None:
        with _shared_agent_lock:
            if _shared_agent is None:
                _shared_agent = create_doc_generator_agent()
    return _shared_agent


def close_shared_agent() -> None:
    """Release the shared agent's sandbox session. Call on app shutdown."""
    global _shared_agent
    with _shared_agent_lock:
        if _shared_agent is not None:
            _shared_agent.close()
            _shared_agent = None


def run_with_reference(agent, prompt: str, reference_bytes: bytes | None):
    """Runs the agent with `reference_bytes` staged as this request's
    uploaded reference document (see tools.py's reference-document-staging
    tools - a tool-calling model cannot transcribe a PDF/docx's raw bytes as
    a JSON argument, so fill/recreate tools read this staged value instead
    of taking bytes as an LLM-supplied parameter).

    Holds tools.reference_lock for the whole call, not just the staging
    step, so two requests on the shared agent can never see each other's
    reference document - this is safe to serialize on because
    WorkspaceAgent.run() already serializes concurrent calls internally too
    (its own instance lock), so this adds no new bottleneck.
    """
    with tools.reference_lock:
        tools.set_reference_document(reference_bytes)
        try:
            return agent.run(prompt)
        finally:
            tools.set_reference_document(None)
