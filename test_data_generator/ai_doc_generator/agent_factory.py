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


def _reset_agent_memory(agent) -> None:
    """Clears the shared agent's conversation memory and plan before each
    run. `WorkspaceAgent.memory`/`.plan` are plain instance state
    (andromeda/core/agent.py:69, andromeda/core/supervisor.py:103) that the
    framework accumulates forever across `.run()` calls with no built-in
    reset or per-thread isolation (its own docstring: "two runs on the same
    agent share and grow the same history no matter what thread_id is
    passed" - `thread_id` only scopes model-side tracing, not this memory).
    Reusing one agent across requests (get_shared_agent) means every request
    after the first would otherwise see every prior request's full prompt +
    output still in context - eventually large enough to blow past the
    model's context window, at which point it produces empty or truncated
    output instead of the requested JSON. Each specialist coworker keeps its
    own separate `.memory` too, so those are cleared alongside the
    supervisor's.
    """
    agent.memory.clear()
    agent.plan.clear()
    for coworker in agent.agents:
        coworker.memory.clear()


def _extract_final_text(messages: list) -> tuple[str | list | None, str]:
    """Picks the final answer out of a finished conversation, and returns a
    one-line diagnostic describing how it got there.

    WorkspaceAgent.run() just returns `messages[-1].content`, which is wrong
    whenever the model's true last turn was a tool call with no accompanying
    text (a normal thing for a tool-calling model to do - `content` is ""
    and the actual call lives in `.tool_calls`) - that turn is functionally
    silent, not the answer, and the real final answer may sit one or two
    turns earlier. So this walks backward for the last AIMessage that
    actually has non-empty text content.

    Deliberately restricted to AIMessage: a ToolMessage's `content` is a
    tool's raw return value stringified by the framework's tool-execution
    layer, never the model's own answer - naively accepting the last
    non-empty message regardless of type previously meant this could return
    the literal `str()` of a tool's raw bytes (e.g. "b'%PDF-1.3\\n...'") as
    if it were the agent's response, which is exactly what a user once saw.
    """
    from langchain_core.messages import AIMessage

    if not messages:
        return None, "no messages at all - the run produced nothing"

    tool_call_tail = 0
    for m in reversed(messages):
        if not isinstance(m, AIMessage):
            tool_call_tail += 1
            continue
        content = getattr(m, "content", None)
        has_text = (isinstance(content, str) and content.strip()) or (isinstance(content, list) and content)
        if has_text:
            note = (
                f"used AIMessage {len(messages) - 1 - tool_call_tail}/{len(messages) - 1} "
                f"(skipped {tool_call_tail} trailing message(s) with no AI text)"
                if tool_call_tail
                else f"used the last message ({len(messages)} total)"
            )
            return content, note
        tool_call_tail += 1

    roles = [type(m).__name__ for m in messages]
    return None, f"NO AIMessage had text content among {len(messages)} messages - roles were: {roles}"


def run_with_reference(agent, prompt: str, reference_bytes: bytes | None):
    """Runs the agent with `reference_bytes` staged as this request's
    uploaded reference document (see tools.py's reference-document-staging
    tools - a tool-calling model cannot transcribe a PDF/docx's raw bytes as
    a JSON argument, so fill/recreate tools read this staged value instead
    of taking bytes as an LLM-supplied parameter). Also clears and then
    returns whatever OUTPUT document got staged during the run (see
    tools.stage_artifact) - the same "can't carry bytes through the model's
    own text" problem applies just as much on the way out, so
    render_document_to_pdf/fill_pdf_widgets/fill_docx_form_controls stage
    their result here instead of returning it, and this function is where
    that staged result actually gets retrieved - never by parsing it out of
    the model's final answer.

    Returns (final_text, artifact_bytes, artifact_kind). `artifact_bytes` is
    None if nothing was staged this run (e.g. packet mode, which still
    relies on the model's own text - see app.py's TODO there).

    Holds tools.reference_lock for the whole call, not just the staging
    step, so two requests on the shared agent can never see each other's
    reference document or output artifact - this is safe to serialize on
    because WorkspaceAgent.run() already serializes concurrent calls
    internally too (its own instance lock), so this adds no new bottleneck.
    Also resets the agent's conversation memory before each run - see
    _reset_agent_memory. The artifact is read out INSIDE this lock (not by
    the caller afterward) so a concurrent request queued behind this one
    cannot clear/overwrite it before it's retrieved.

    Calls agent.supervise(...) directly instead of agent.run() - same call
    WorkspaceAgent.run() makes internally (andromeda/core/workspace.py:656),
    kept in sync with it here - so the full message list is available for
    _extract_final_text and for the diagnostic print on an empty result,
    instead of only the collapsed last-message string agent.run() returns.
    This does skip agent.run()'s own lock/closed-check, which is fine here
    since tools.reference_lock already serializes every call to this
    function and it is the only caller of the agent in this codebase.
    """
    import traceback
    from langchain_core.messages import HumanMessage

    with tools.reference_lock:
        _reset_agent_memory(agent)
        tools.set_reference_document(reference_bytes)
        tools.clear_staged_artifact()
        try:
            try:
                result = agent.supervise({"messages": [HumanMessage(content=prompt)], "plan": []})
            except Exception:
                # Printed here (not just re-raised) because app.py's outer handler only
                # surfaces str(e) to the browser - the full traceback would otherwise
                # never reach this process's console at all.
                print("\n" + "=" * 30 + " AGENT RUN RAISED " + "=" * 30)
                traceback.print_exc()
                print("=" * 79 + "\n")
                raise

            messages = result.get("messages", []) if isinstance(result, dict) else []
            final, note = _extract_final_text(messages)
            print(f"[run_with_reference] {note}")
            # Always dump the tail of the conversation, not just when nothing was found -
            # `final` can be a real AIMessage that isn't actually the finished answer (e.g.
            # early mid-task narration like "Let me check X first"), which _extract_final_text
            # has no way to distinguish from a genuine closing answer since both are non-empty
            # AI text. Seeing the last few messages is what tells them apart.
            tail = messages[-8:]
            skipped = len(messages) - len(tail)
            print(f"[run_with_reference] conversation tail ({len(messages)} total"
                  f"{f', showing last {len(tail)}' if skipped > 0 else ''}):")
            for m in tail:
                tc = getattr(m, "tool_calls", None)
                content = getattr(m, "content", None)
                if isinstance(content, str) and len(content) > 300:
                    content = content[:300] + f"...<+{len(content) - 300} chars>"
                print(f"  - {type(m).__name__}: content={content!r} tool_calls={tc}")

            artifact_bytes, artifact_kind = tools.get_staged_artifact()
            if artifact_bytes is not None:
                print(f"[run_with_reference] staged artifact: kind={artifact_kind} size={len(artifact_bytes)} bytes")
            return final, artifact_bytes, artifact_kind
        finally:
            tools.set_reference_document(None)
