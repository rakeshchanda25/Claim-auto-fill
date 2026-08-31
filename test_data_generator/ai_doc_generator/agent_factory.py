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
    """Seed selected subdirectories into the sandbox instead of the entire
    source tree. Uses DirectorySeed for each path to retain its safety checks.
    """

    source_dir: str
    subpaths: tuple[str, ...]
    target_path: str = "/"

    def apply(self, root, policy) -> None:
        from andromeda.workspace import DirectorySeed

        base = Path(self.source_dir)
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
                    r"\b(?:help\s+me|please|can\s+you|could\s+you|i\s+(?:want|need)\s+you\s+to|"
                    r"go\s+ahead\s+and|i\s+will|i'll|let'?s|we\s+(?:should|will))\s+"
                    r"(?:(?!not\b|never\b)\w+\s+){0,2}falsif(?:y|ication)\b",
                    r"\b(?:help\s+me|please|can\s+you|could\s+you|i\s+(?:want|need)\s+you\s+to|"
                    r"go\s+ahead\s+and|i\s+will|i'll|let'?s|we\s+(?:should|will))\s+"
                    r"(?:(?!not\b|never\b)\w+\s+){0,2}misrepresent",
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
        seed=ScopedDirectorySeed(source_dir=str(_PROJECT_ROOT), subpaths=("skills",)),
        policy=policy,
        settings=settings,
    )

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
    prior_memory, prior_plan = len(agent.memory), len(agent.plan)
    agent.memory.clear()
    agent.plan.clear()
    for coworker in agent.agents:
        coworker.memory.clear()
    if prior_memory or prior_plan:
        logger.info(f"cleared prior agent state before this run: {prior_memory} memory "
                    f"message(s), {prior_plan} plan item(s)")


def _extract_final_text(messages: list) -> tuple[str | list | None, str]:
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

                logger.exception(f"agent.supervise() raised after {time.monotonic() - _t0:.1f}s")
                raise
            logger.info(f"agent.supervise() completed in {time.monotonic() - _t0:.1f}s")

            messages = result.get("messages", []) if isinstance(result, dict) else []
            final, note = _extract_final_text(messages)
            logger.info(f"answer extraction: {note}")
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
