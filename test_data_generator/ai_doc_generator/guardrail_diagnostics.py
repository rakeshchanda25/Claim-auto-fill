"""Adds "which pattern matched, on what text" logging to the shared andromeda
package's three guardrail middlewares (andromeda/core/middleware/guardrails.py,
andromeda/core/middleware/privacy.py) without editing those files - they're
shared framework code outside this project's deploy scope, so this patches
them at runtime from here instead.

Without this, a block ("Request blocked by IDP document generation policy.")
is a black box: none of the three middlewares log which pattern fired or what
text triggered it, so every occurrence has to be re-diagnosed from scratch.
That's exactly how the DataPrivacyMiddleware phone-number false-positive this
session went undiagnosed for two rounds - andromeda/core/middleware/
factory.py silently bundles a THIRD guardrail (DataPrivacyMiddleware,
strategy="block") in alongside prompt-injection/compliance whenever
guardrails.input/output is on, and its default phone pattern matches any bare
10-digit number - exactly the shape of a policy/claim/member number. See
agent_factory.py's data_patterns override, which disables that layer for
this agent; this module's job is purely to make the NEXT such surprise
visible in one line instead of requiring this same investigation again.

Patches only the low-level match-check methods (_contains_injection /
_is_non_compliant / _transform), never the @hook_config-decorated
before_model/after_model hooks themselves - replacing a decorated method
risks losing the `can_jump_to` metadata the LangChain middleware framework
relies on to honor the guardrail's block-and-end behavior. The low-level
checks are undecorated plumbing; wrapping them only adds a logging side
effect before returning the same value the original would have.
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
    from andromeda.core.middleware.privacy import DataPrivacyMiddleware

    _wrap_pattern_list(PromptInjectionMiddleware, "_contains_injection", "prompt_injection")
    _wrap_pattern_list(ComplianceMiddleware, "_is_non_compliant", "compliance")
    _wrap_data_privacy(DataPrivacyMiddleware)
    _installed = True
    logger.info(
        "guardrail_diagnostics: installed match logging on "
        "PromptInjectionMiddleware/ComplianceMiddleware/DataPrivacyMiddleware"
    )


def _log(guard: str, pattern_repr: str, matched: str, snippet: str, extra: str = "") -> None:
    line = (
        f"[GUARDRAIL BLOCK] {guard} guardrail: pattern={pattern_repr!r} "
        f"matched={matched!r} snippet={snippet!r}{extra}"
    )
    logger.error(line)
    print(line, flush=True)


def _wrap_pattern_list(cls, method_name: str, guard_name: str) -> None:
    """For PromptInjectionMiddleware/ComplianceMiddleware: self.patterns is a
    plain list of compiled patterns, checked with a simple any(...)."""
    original = getattr(cls, method_name)

    def wrapped(self, text, _original=original, _guard=guard_name):
        for pattern in self.patterns:
            m = pattern.search(text)
            if m:
                start = max(0, m.start() - 60)
                end = min(len(text), m.end() + 60)
                snippet = text[start:end].replace("\n", " ")
                _log(_guard, pattern.pattern, m.group(0), snippet)
                break
        return _original(self, text)

    setattr(cls, method_name, wrapped)


def _wrap_data_privacy(cls) -> None:
    """DataPrivacyMiddleware.self.patterns is a {pii_type: compiled_pattern}
    dict, and a match only actually BLOCKS the request when strategy=="block"
    (otherwise it's redacted/masked/hashed/tokenized and lets the message
    through) - both are worth showing, since a "detected but not blocking"
    line is exactly what would tell us this layer is filtering silently
    rather than the guardrail everyone assumes is responsible."""
    original = cls._transform

    def wrapped(self, text, _original=original):
        for pii_type, pattern in self.patterns.items():
            m = pattern.search(text)
            if m:
                start = max(0, m.start() - 60)
                end = min(len(text), m.end() + 60)
                snippet = text[start:end].replace("\n", " ")
                extra = f" pii_type={pii_type!r} strategy={self.strategy!r}"
                _log("data_privacy", pattern.pattern, m.group(0), snippet, extra)
                break
        return _original(self, text)

    cls._transform = wrapped
