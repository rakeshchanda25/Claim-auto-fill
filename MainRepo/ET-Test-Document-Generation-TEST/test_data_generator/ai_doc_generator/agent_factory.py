"""Builds and runs the document-generation agent.

All agent settings live in .andromeda/agents/doc-generator.yaml. This module only
supplies what YAML cannot express - the tool function objects and the sandbox
seed - and owns the run lifecycle.
"""

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import tools
from .tools import agent_tools

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent
_AGENT_CONFIG = _PROJECT_ROOT / ".andromeda" / "agents" / "doc-generator.yaml"


def _resolve_backend(backend: str) -> str:
    """Turns the config's "auto" into a concrete backend name.

    WorkspaceSession.create only accepts real backend names - "auto" is a
    WorkspaceAgentConfig-level default that the framework expands only when it
    creates the session itself. We pass our own session (to seed skills/ into
    the sandbox), so we have to expand it here, using the same rule the
    framework uses: the bubblewrap sandbox when the host can run it, otherwise
    the unisolated local workspace.
    """
    if backend != "auto":
        return backend

    from andromeda.workspace import check_provider_availability

    if check_provider_availability("bubblewrap_process").available:
        return "bubblewrap_process"
    logger.info("bubblewrap unavailable on this host - using ephemeral_fs (no isolation)")
    return "ephemeral_fs"


@dataclass(frozen=True)
class ScopedDirectorySeed:
    """Seeds only selected subdirectories into the sandbox rather than the whole
    source tree, while keeping DirectorySeed's own safety checks."""

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


def create_agent():
    logger.info("building doc-generator agent (seeding sandbox, compiling graph)...")
    t0 = time.monotonic()

    try:
        from andromeda.config import WorkspaceAgentConfig
        from andromeda.core import WorkspaceAgent
        from andromeda.tools.toolkit import register_tool
        from andromeda.workspace import (
            BubblewrapProcessSettings,
            FilePolicy,
            WorkspacePolicy,
            WorkspaceSession,
        )
    except ImportError as e:
        raise RuntimeError(
            f"The Andromeda framework is not importable ({e}). Install it from the "
            f"Andromeda repository: pip install -e path/to/andromeda"
        ) from e

    tool_objects = agent_tools()
    for t in tool_objects:
        register_tool(t)

    # resolve_tools=False: the YAML declares no tools, because tool functions are
    # Python objects. Everything else - model, prompt, guardrails, backend - is
    # read from the file.
    config = WorkspaceAgentConfig.load_from_file(str(_AGENT_CONFIG), resolve_tools=False)
    config.tools = tool_objects

    backend = _resolve_backend(config.workspace_backend)

    policy = WorkspacePolicy(
        read_only=False,
        enable_shell=False,
        file=FilePolicy(max_file_size_mb=20, allow_symlinks=False, protect_root=True),
    )
    settings = None
    if backend == "bubblewrap_process":
        settings = BubblewrapProcessSettings(network_mode="none", inherit_host_env=False)

    session = WorkspaceSession.create(
        backend=backend,
        seed=ScopedDirectorySeed(source_dir=str(_PROJECT_ROOT), subpaths=("skills",)),
        policy=policy,
        settings=settings,
    )

    agent = WorkspaceAgent(config, agents=[], session=session, min_agents=1)
    logger.info(f"agent ready in {time.monotonic() - t0:.1f}s (backend={backend})")
    return agent


_agent = None
_agent_lock = threading.Lock()


def get_shared_agent():
    """The agent is expensive to build (sandbox + graph compilation), so one
    instance is reused for the life of the process."""
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent = create_agent()
    return _agent


def close_shared_agent() -> None:
    """Releases the sandbox session. Called on app shutdown."""
    global _agent
    with _agent_lock:
        if _agent is not None:
            logger.info("closing shared agent")
            _agent.close()
            _agent = None


def _final_text(messages: list):
    """The last AI message that actually carries text.

    A run often ends on a tool call with no trailing prose, so the final message
    is not reliably the answer - walk back to the last one with content.
    """
    from langchain_core.messages import AIMessage

    for i, m in enumerate(reversed(messages)):
        if not isinstance(m, AIMessage):
            continue
        content = getattr(m, "content", None)
        if (isinstance(content, str) and content.strip()) or (isinstance(content, list) and content):
            if i:
                logger.info(f"answer taken from {i} message(s) before the end")
            return content
    logger.warning(f"no AI message had text among {len(messages)} messages")
    return None


@dataclass
class RunResult:
    text: str | list | None
    artifact: tuple[bytes, str] | None      # (bytes, kind) for a single document
    packet: list[dict] | None               # rendered packet components


def run_generation(agent, prompt: str, reference_bytes: bytes | None = None,
                   custom_fields: dict | None = None, anchor_date: str | None = None) -> RunResult:
    """Runs one generation end to end.

    The claim facts and the uploaded reference are staged before the agent starts
    rather than passed through the prompt, so the tools get them regardless of
    what the model puts in its tool calls.
    """
    from langchain_core.messages import HumanMessage

    with tools.run_lock:
        tools.begin_run(reference_bytes, custom_fields, anchor_date)
        if reference_bytes:
            logger.info(f"staged reference document: {len(reference_bytes)} bytes")
        if custom_fields:
            logger.info(f"staged {len(custom_fields)} claim fact(s), anchor_date={anchor_date!r}")

        # The agent instance is reused across requests, so last run's messages
        # and plan have to go or they leak into this one's context.
        agent.memory.clear()
        agent.plan.clear()
        for coworker in agent.agents:
            coworker.memory.clear()

        try:
            t0 = time.monotonic()
            result = agent.supervise({"messages": [HumanMessage(content=prompt)], "plan": []})
            logger.info(f"agent finished in {time.monotonic() - t0:.1f}s")

            messages = result.get("messages", []) if isinstance(result, dict) else []
            ctx = tools.current_run()
            if ctx.artifact:
                logger.info(f"artifact staged: {ctx.artifact[1]} ({len(ctx.artifact[0])} bytes)")
            if ctx.packet:
                logger.info(f"packet staged: {[c['label'] for c in ctx.packet]}")
            if not ctx.artifact and not ctx.packet:
                logger.warning("run produced no artifact and no packet")
                for m in messages[-6:]:
                    logger.warning(f"  {type(m).__name__}: {_summary(m)}")

            return RunResult(_final_text(messages), ctx.artifact, ctx.packet)
        finally:
            tools.end_run()


def _summary(message) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str) and len(content) > 300:
        content = content[:300] + f"...<+{len(content) - 300} chars>"
    return f"content={content!r} tool_calls={getattr(message, 'tool_calls', None)}"
