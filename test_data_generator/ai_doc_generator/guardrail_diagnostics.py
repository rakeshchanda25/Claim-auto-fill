"""Adds "which pattern matched, on what text" logging to the shared andromeda
package's PromptInjectionMiddleware/ComplianceMiddleware (andromeda/core/
middleware/guardrails.py) without editing that file - it's shared framework
code outside this project's deploy scope, so this patches it at runtime from
here instead.

Without this, a block ("Request blocked by IDP document generation policy.")
is a black box: neither middleware logs which regex fired or what text
triggered it, so every occurrence has to be re-diagnosed from scratch (see
the WA S.F.97 recreate-mode false-positive and the instant-block
auto-accident-report case this session, both indistinguishable from the
final message alone).

Patches only the low-level boolean check (_contains_injection /
_is_non_compliant), never the @hook_config-decorated before_model/after_model
hooks themselves - replacing a decorated method risks losing the
`can_jump_to` metadata the LangChain middleware framework relies on to honor
the guardrail's block-and-end behavior. The low-level check is undecorated
plumbing; wrapping it only adds a logging side effect before returning the
same bool the original would have.
"""
import logging

logger = logging.getLogger(__name__)

_installed = False


def install() -> None:
    """Idempotent - safe to call more than once (e.g. if agent_factory.py's
    module gets reloaded)."""
    global _installed
    if _installed:
        return

    from andromeda.core.middleware.guardrails import ComplianceMiddleware, PromptInjectionMiddleware

    _wrap(PromptInjectionMiddleware, "_contains_injection", "prompt_injection")
    _wrap(ComplianceMiddleware, "_is_non_compliant", "compliance")
    _installed = True
    logger.info("guardrail_diagnostics: installed match logging on PromptInjectionMiddleware/ComplianceMiddleware")


def _wrap(cls, method_name: str, guard_name: str) -> None:
    original = getattr(cls, method_name)

    def wrapped(self, text, _original=original, _guard=guard_name):
        for pattern in self.patterns:
            m = pattern.search(text)
            if m:
                start = max(0, m.start() - 60)
                end = min(len(text), m.end() + 60)
                snippet = text[start:end].replace("\n", " ")
                line = (
                    f"[GUARDRAIL BLOCK] {_guard} guardrail: pattern={pattern.pattern!r} "
                    f"matched={m.group(0)!r} snippet={snippet!r}"
                )
                logger.error(line)
                print(line, flush=True)
                break
        return _original(self, text)

    setattr(cls, method_name, wrapped)
