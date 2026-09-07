"""Step-by-step tracing for a generation run.

Every tool call, its arguments and its outcome are written to stdout and to
one JSONL file per run under `logs/`, so a run that produced the wrong
documents can be read back afterwards and the exact step that went wrong
identified.
"""

import functools
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

_run_id = "no-run"
_run_file = None
_step_no = 0


def _short(value, limit: int = 400) -> str:
    """Readable one-line form of a tool argument or result."""
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    try:
        text = value if isinstance(value, str) else json.dumps(value, default=str)
    except Exception:
        text = repr(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + f"... (+{len(text) - limit} chars)"


def start_run(label: str = "") -> str:
    global _run_id, _run_file, _step_no
    _run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    _step_no = 0
    LOG_DIR.mkdir(exist_ok=True)
    _run_file = LOG_DIR / f"run-{_run_id}.jsonl"
    step("run.start", label=label)
    return _run_id


def step(event: str, **fields) -> None:
    global _step_no
    _step_no += 1
    record = {"run": _run_id, "step": _step_no, "at": datetime.now().isoformat(timespec="seconds"),
              "event": event, **fields}

    detail = "  ".join(f"{k}={_short(v)}" for k, v in fields.items())
    print(f"[trace {_run_id} #{_step_no:02d}] {event}  {detail}".rstrip(), flush=True)

    if _run_file:
        with _run_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")


def write_blob(name: str, text: str) -> None:
    """Park something too long for a log line (the prompt, the final answer)
    next to the run's JSONL file."""
    if not _run_file:
        return
    path = _run_file.with_name(f"run-{_run_id}.{name}.txt")
    path.write_text(text, encoding="utf-8")
    step("blob.written", name=name, chars=len(text), path=str(path))


def traced(func):
    """Log a tool call's arguments, outcome and duration."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        call = {k: _short(v) for k, v in kwargs.items()}
        if args:
            call["_positional"] = [_short(a) for a in args]
        step("tool.call", tool=func.__name__, args=call)

        started = time.perf_counter()
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            step("tool.error", tool=func.__name__, error=f"{type(exc).__name__}: {exc}",
                 ms=round((time.perf_counter() - started) * 1000))
            raise
        step("tool.ok", tool=func.__name__, result=_short(result),
             ms=round((time.perf_counter() - started) * 1000))
        return result

    return wrapper
