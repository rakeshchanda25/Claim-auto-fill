"""Decide which text on a page is the form and which is what was filled into it.

A printed document is two things mixed together: the SCHEMA (labels, headings,
instructions, table headers, boilerplate - identical on every copy) and the
VALUES (the data specific to this one document). Only the values are ever
handwritten.

Rules cannot tell these apart reliably - plenty of forms have no colons, put
the label above the box, or run values across table cells - so the page is
handed to the model that already serves this app.
"""

import json
import os
import re
from pathlib import Path

_AGENT_CONFIG = Path(__file__).parent / ".andromeda" / "agents" / "doc-generator.yaml"

# Spans per request. Big enough that the model sees a whole page's context,
# small enough that a long document does not blow the context window.
_CHUNK = 140

_SYSTEM = """You separate a form's pre-printed schema from the data filled into it.

You are given the text spans of ONE page of a document, grouped by line, each
span numbered. Decide for every span whether it is SCHEMA or VALUE.

SCHEMA - pre-printed, identical on every blank copy of this document:
  field labels ("Name of Hospital", "Date of Loss", "Policy No"), section
  headings, table column headers, instructions, units and currency symbols
  printed as part of the form, legal boilerplate, footers, page numbers,
  the organisation's own name and address in the letterhead.

VALUE - specific to THIS document, what somebody entered:
  names of people and places, addresses, phone and account numbers, policy
  claim and reference numbers, dates, amounts, quantities, diagnoses,
  descriptions, ticked options, signatures, free-text answers.

Rules:
- A span may hold a label and its value together ("Name: Ram"). Return only
  the value part as `text` ("Ram"), copied exactly as it appears.
- The letterhead of the organisation that PRINTED the form is schema. A name
  written INTO the form is a value.
- When a span is genuinely ambiguous, call it schema. Turning a label into
  handwriting is worse than leaving one value printed.

Reply with JSON only, no prose, no code fence:
{"values": [{"span": <number>, "text": "<the value text>"}]}"""


def _configured_model() -> str:
    """The model the app already talks to, so this needs no separate setup."""
    if env := os.environ.get("HANDWRITE_MODEL"):
        return env
    try:
        import yaml
        config = yaml.safe_load(_AGENT_CONFIG.read_text(encoding="utf-8"))
        if name := (config.get("model") or {}).get("name"):
            return name
    except Exception:
        pass
    return "openai/qwen3.6:27b"


def _render_lines(lines: list) -> str:
    """The page as the model sees it: line structure kept, spans numbered."""
    out = []
    for line_no, spans in enumerate(lines, 1):
        parts = " ".join(f'[{idx}]"{text}"' for idx, text in spans)
        out.append(f"L{line_no}: {parts}")
    return "\n".join(out)


def _parse_reply(reply: str, valid_ids: set) -> list:
    """Pull the JSON out of whatever the model wrapped it in."""
    text = re.sub(r"^```(?:json)?|```$", "", reply.strip(), flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in model reply: {reply[:200]!r}")

    data = json.loads(match.group(0))
    results = []
    for entry in data.get("values", []):
        if not isinstance(entry, dict):
            continue
        try:
            span_id = int(entry.get("span"))
        except (TypeError, ValueError):
            continue
        value = (entry.get("text") or "").strip()
        if span_id in valid_ids and value:
            results.append((span_id, value))
    return results


def classify_page(lines: list, model: str = "", timeout: int = 120) -> list:
    """Ask the model which spans are values.

    `lines` is a list of lines, each a list of (span_id, text).
    Returns [(span_id, value_text), ...]. Raises if the model is unreachable
    or answers with something unusable: guessing at a document's schema with
    rules produced worse results than not running at all.
    """
    valid_ids = {idx for line in lines for idx, _ in line}
    if not valid_ids:
        return []

    # Imported here on purpose: litellm takes many seconds to import, and the
    # scan features that never classify anything should not pay for it.
    from litellm import completion

    model = model or _configured_model()
    found = []

    flat = [(idx, text) for line in lines for idx, text in line]
    for start in range(0, len(flat), _CHUNK):
        chunk_ids = {idx for idx, _ in flat[start:start + _CHUNK]}
        chunk_lines = [[(i, t) for i, t in line if i in chunk_ids] for line in lines]
        chunk_lines = [line for line in chunk_lines if line]

        response = completion(
            model=model,
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": _render_lines(chunk_lines)}],
            temperature=0,
            timeout=timeout,
        )
        found.extend(_parse_reply(response.choices[0].message.content, chunk_ids))

    return found
