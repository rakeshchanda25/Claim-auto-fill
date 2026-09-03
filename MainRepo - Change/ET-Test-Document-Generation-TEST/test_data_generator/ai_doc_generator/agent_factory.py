import threading
from dataclasses import dataclass
from pathlib import Path

from . import tools
from .tools import agent_tools

_PROJECT_ROOT = Path(__file__).parent.parent
_AGENT_CONFIG = _PROJECT_ROOT / ".andromeda" / "agents" / "doc-generator.yaml"


@dataclass(frozen=True)
class ScopedDirectorySeed:

    source_dir: str
    subpaths: tuple[str, ...]

    def apply(self, root, policy) -> None:
        from andromeda.workspace import DirectorySeed

        for sub in self.subpaths:
            src = Path(self.source_dir) / sub
            if src.is_dir():
                DirectorySeed(source_dir=str(src), target_path=sub).apply(root, policy)


def create_agent():
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

    config = WorkspaceAgentConfig.load_from_file(str(_AGENT_CONFIG), resolve_tools=False)
    config.tools = tool_objects

    backend = config.workspace_backend

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

    return WorkspaceAgent(config, agents=[], session=session, min_agents=1)


_agent = None
_agent_lock = threading.Lock()


def get_shared_agent():
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent = create_agent()
    return _agent


def close_shared_agent() -> None:
    global _agent
    with _agent_lock:
        if _agent is not None:
            _agent.close()
            _agent = None


def _final_text(messages: list):
    from langchain_core.messages import AIMessage

    for m in reversed(messages):
        if not isinstance(m, AIMessage):
            continue
        content = getattr(m, "content", None)
        if (isinstance(content, str) and content.strip()) or (isinstance(content, list) and content):
            return content
    return None


@dataclass
class RunResult:
    text: str | list | None
    artifact: tuple[bytes, str] | None
    packet: list[dict] | None


def run_generation(agent, prompt: str, reference_bytes: bytes | None = None,
                   custom_fields: dict | None = None, anchor_date: str | None = None,
                   jurisdiction: str | None = None) -> RunResult:
    from langchain_core.messages import HumanMessage

    with tools.run_lock:
        tools.begin_run(reference_bytes, custom_fields, anchor_date, jurisdiction)

        agent.memory.clear()
        agent.plan.clear()
        for coworker in agent.agents:
            coworker.memory.clear()

        try:
            result = agent.supervise({"messages": [HumanMessage(content=prompt)], "plan": []})
            messages = result.get("messages", []) if isinstance(result, dict) else []
            ctx = tools.current_run()
            return RunResult(_final_text(messages), ctx.artifact, ctx.packet)
        finally:
            tools.end_run()
