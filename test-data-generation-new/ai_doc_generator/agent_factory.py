import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import tools

logger = logging.getLogger(__name__)
from .tools import (
    analyze_uploaded_reference,
    build_packet,
    generate_synthetic_data,
    recreate_document_data,
    render_document_to_pdf,
    render_packet,
    revise_document_data,
    validate_document_structure,
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
    logger.info("building doc-generator agent: seeding sandbox, compiling LangGraph agents...")
    _t0 = time.monotonic()
    try:
        from andromeda.config import (
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
        analyze_uploaded_reference,
        recreate_document_data,
        build_packet,
        render_packet,
        revise_document_data,
        validate_document_structure,
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
    # Shell is off. It existed solely for the removed `renderer` specialist to
    # run `python3 -m weasyprint` on the command line; every document is now
    # rendered in-process by render_document_to_pdf / render_packet, so no
    # code path here needs a shell at all. Withholding it is also the durable
    # fix for a run wandering off to `ls` around the workspace instead of
    # calling the skill's tools - a capability the agent does not have cannot
    # be misspent, which beats asking it in the prompt not to.
    policy = WorkspacePolicy(
        read_only=False,
        enable_shell=False,
        file=FilePolicy(max_file_size_mb=20, allow_symlinks=False, protect_root=True),
    )

    settings = None
    if backend == "bubblewrap_process":
        settings = BubblewrapProcessSettings(
            network_mode="none",
            inherit_host_env=False,
        )

    session = WorkspaceSession.create(
        backend=backend,
        # Only skills/ needs to exist in the sandbox - SkillsMiddleware reads
        # it from the sandbox root rather than the host path. Everything else
        # in the project (test fixtures, generated PDFs, frontend/, docs) is
        # dead weight nothing in here reads.
        # renderers/templates is deliberately NOT seeded any more: templates are
        # read from the host path by renderers/html_renderer.py (_TEMPLATES_DIR),
        # which runs in this process, never inside the sandbox. Copying them in
        # only mattered for the removed shell-based renderer specialist.
        seed=ScopedDirectorySeed(source_dir=str(_PROJECT_ROOT), subpaths=("skills",)),
        policy=policy,
        settings=settings,
    )

    # No specialist agents. The three that used to live here (doc-analyst,
    # packet-builder, renderer) described a pipeline that no longer exists:
    # packet-builder wrote component HTML to /output/ and renderer shelled out
    # to `python3 -m weasyprint` to convert it, both long since replaced by the
    # in-process render_document_to_pdf / render_packet tools, and doc-analyst
    # by analyze_uploaded_reference. Nothing referenced them by name any more.
    #
    # They were not free. Every specialist is another LangGraph agent compiled
    # at build time, and the supervisor carries a handoff tool for each one in
    # its prompt on EVERY turn. Worse, `renderer` held the full shell toolset -
    # which is how a run could wander off running shell commands to look
    # around the workspace instead of calling the skill's own tools, burning a
    # whole context budget without producing a document.
    #
    # min_agents=1 is the floor andromeda allows (WorkspaceAgent requires a
    # team; supplying none pads with a single generic coworker).
    specialists: list = []

    config = WorkspaceAgentConfig(
        name="doc-generator",
        model=model,
        prompt=(
            "You are the lead insurance document generation agent for IDP testing. "
            "ALWAYS load the matching skill via load_skill before any generation step. "
            "For GENERATING a single new document from scratch (no uploaded reference): call "
            "generate_synthetic_data, validate_document_structure, then render_document_to_pdf. "
            "NEVER pass a `data` argument to validate_document_structure or "
            "render_document_to_pdf - the generated data is held server-side and both tools pick "
            "it up automatically. Restating a document's fields in your own output is the single "
            "slowest thing you can do and risks corrupting them; to change values, call "
            "revise_document_data with ONLY the fields that change. "
            "For PACKETS: exactly two calls - build_packet(packet_name, scenario) then "
            "render_packet(). build_packet plans every component with one shared claimant and "
            "claim number; render_packet renders them all. Do not loop over components yourself. "
            "For RECREATING an uploaded document under a DIFFERENT scenario: call "
            "analyze_uploaded_reference, read the document's real values out of each page's `text`, "
            "then call recreate_document_data(doc_type, scenario, carried_values={...}) and render "
            "the dict it returns. Carry over only the people and identifiers (names, DOB, policy/ "
            "claim/member/record numbers, provider, addresses); never carry diagnoses, procedures, "
            "amounts or narrative - the requested new scenario must drive those, and copying them "
            "would just reproduce the original document. "
            "STAY ON TASK: do not browse the workspace, list directories, read skill files "
            "directly, or run shell commands to 'look around' - load_skill already gives you "
            "everything a skill contains. Every step must be one of the tool calls the loaded "
            "skill names; if you catch yourself exploring the filesystem instead of calling "
            "those tools, stop and call the next tool in the skill's workflow. "
            "Every mode's output is staged server-side (single documents via render_document_to_pdf, "
            "packets via render_packet) - once "
            "staging is done, your final answer is just a short JSON status object, e.g. "
            "{\"status\": \"ok\"} or {\"status\": \"ok\", \"components\": 4}. Never put a document's "
            "bytes in your own output."
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


    agent = WorkspaceAgent(
        config,
        agents=specialists,
        session=session,
        min_agents=1,
    )
    logger.info(f"doc-generator agent ready in {time.monotonic() - _t0:.1f}s "
                f"({len(specialists)} named specialists + auto-coworkers, backend={backend})")
    return agent


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
    else:
        logger.debug("reusing existing shared agent")
    return _shared_agent


def close_shared_agent() -> None:
    """Release the shared agent's sandbox session. Call on app shutdown."""
    global _shared_agent
    with _shared_agent_lock:
        if _shared_agent is not None:
            logger.info("closing shared agent")
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
    prior_memory, prior_plan = len(agent.memory), len(agent.plan)
    agent.memory.clear()
    agent.plan.clear()
    for coworker in agent.agents:
        coworker.memory.clear()
    if prior_memory or prior_plan:
        logger.info(f"cleared prior agent state before this run: {prior_memory} memory "
                    f"message(s), {prior_plan} plan item(s)")


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
    a JSON argument, so recreate's analyze_uploaded_reference tool reads this
    staged value instead of taking bytes as an LLM-supplied parameter). Also
    clears and then returns whatever OUTPUT document got staged during the
    run (see tools.stage_artifact) - the same "can't carry bytes through the
    model's own text" problem applies just as much on the way out, so
    render_document_to_pdf stages its result here instead of returning it,
    and this function is where
    that staged result actually gets retrieved - never by parsing it out of
    the model's final answer.

    Returns (final_text, artifact_bytes, artifact_kind, packet_components).
    `artifact_bytes` is None if no single document was staged this run (e.g.
    packet mode, which stages N documents into packet_components instead -
    see tools.render_packet). `packet_components` is None if
    nothing was added to it this run, otherwise a list of
    {label, kind, bytes} in the order they were staged.

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
    from langchain_core.messages import HumanMessage

    with tools.reference_lock:
        logger.info("acquired reference_lock - starting agent run")
        _reset_agent_memory(agent)

        tools.set_reference_document(reference_bytes)
        if reference_bytes is not None:
            logger.info(f"staged reference document: {len(reference_bytes)} bytes")
        tools.clear_staged_artifact()
        tools.clear_staged_packet()
        tools.clear_staged_packet_plan()
        tools.clear_staged_doc_data()

        try:
            _t0 = time.monotonic()
            try:
                result = agent.supervise({"messages": [HumanMessage(content=prompt)], "plan": []})
            except Exception:
                # Logged here (not just re-raised) because app.py's outer handler only
                # surfaces str(e) to the browser - the full traceback would otherwise
                # never reach this process's console at all.
                logger.exception(f"agent.supervise() raised after {time.monotonic() - _t0:.1f}s")
                raise
            logger.info(f"agent.supervise() completed in {time.monotonic() - _t0:.1f}s")

            messages = result.get("messages", []) if isinstance(result, dict) else []
            final, note = _extract_final_text(messages)
            logger.info(f"answer extraction: {note}")
            # Always dump the tail of the conversation, not just when nothing was found -
            # `final` can be a real AIMessage that isn't actually the finished answer (e.g.
            # early mid-task narration like "Let me check X first"), which _extract_final_text
            # has no way to distinguish from a genuine closing answer since both are non-empty
            # AI text. Seeing the last few messages is what tells them apart.
            tail = messages[-8:]
            skipped = len(messages) - len(tail)
            logger.info(f"conversation tail ({len(messages)} total"
                        f"{f', showing last {len(tail)}' if skipped > 0 else ''}):")
            for m in tail:
                tc = getattr(m, "tool_calls", None)
                content = getattr(m, "content", None)
                if isinstance(content, str) and len(content) > 300:
                    content = content[:300] + f"...<+{len(content) - 300} chars>"
                logger.info(f"  - {type(m).__name__}: content={content!r} tool_calls={tc}")

            artifact_bytes, artifact_kind = tools.get_staged_artifact()
            if artifact_bytes is not None:
                logger.info(f"staged artifact ready: kind={artifact_kind} size={len(artifact_bytes)} bytes")
            else:
                logger.info("no artifact was staged this run")

            packet_components = tools.get_staged_packet()
            if packet_components:
                logger.info(f"staged packet ready: {len(packet_components)} component(s) - "
                            f"{[c['label'] for c in packet_components]}")
            else:
                logger.info("no packet was staged this run")

            return final, artifact_bytes, artifact_kind, packet_components
        finally:
            tools.set_reference_document(None)
            logger.info("released reference_lock")
