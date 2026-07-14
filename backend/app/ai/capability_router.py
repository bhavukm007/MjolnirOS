"""Deterministic, extensible capability selection after intent classification."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Protocol

from backend.app.ai.intent_router import Intent, RoutedIntent
from backend.app.browser.natural_language import parse_browser_command
from backend.app.windows.natural_language import parse_windows_command


class Capability(StrEnum):
    BROWSER = "browser"
    WINDOWS = "windows"
    LIVE_INFORMATION = "live_information"
    MEMORY = "memory"
    PLANNER = "planner"
    BUILD = "build"
    AI_CODING = "ai_coding"
    CODING = "coding"
    GITHUB = "github"
    GREETING = "greeting"
    LLM = "llm"


class CapabilityStatus(StrEnum):
    READY = "ready"
    NOT_IMPLEMENTED = "not_implemented"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class RoutingContext:
    """Preferences that handlers may consume without changing route selection."""

    preferred_browser_profile: str | None = None


@dataclass(frozen=True)
class CapabilityDecision:
    capability: Capability
    handler: str
    status: CapabilityStatus
    reason: str
    confidence: float
    payload: Any = None
    context: RoutingContext = field(default_factory=RoutingContext)

    def event_data(self) -> dict[str, str | float | None]:
        return {
            "capability": self.capability.value,
            "handler": self.handler,
            "status": self.status.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "preferred_browser_profile": self.context.preferred_browser_profile,
        }


class CapabilityRule(Protocol):
    name: str

    def match(self, routed: RoutedIntent, context: RoutingContext) -> CapabilityDecision | None: ...


@dataclass(frozen=True)
class MatcherRule:
    name: str
    matcher: Callable[[RoutedIntent], Any | None]
    capability: Capability
    reason: str
    status: CapabilityStatus = CapabilityStatus.READY

    def match(self, routed: RoutedIntent, context: RoutingContext) -> CapabilityDecision | None:
        payload = self.matcher(routed)
        if payload is None or payload is False:
            return None
        return CapabilityDecision(
            self.capability, self.name, self.status, self.reason, routed.confidence, payload, context
        )


_LIVE_PATTERNS = (
    r"\bweather\b",
    r"\b(?:latest|current|today'?s?)\s+(?:.+\s+)?news\b",
    r"\b(?:who won|score|result)\b.*\b(?:yesterday|today|last night|ipl|match|game)\b",
    r"\bwhat time is it\b|\btime (?:is it )?in\b|\bcurrent time\b",
    r"\bconvert\s+\d+(?:\.\d+)?\s+[a-z]{3}\s+(?:to|into)\s+[a-z]{3}\b",
    r"\b(?:exchange|conversion) rate\b",
)


def _live_information(routed: RoutedIntent) -> bool | None:
    normalized = routed.message.lower()
    return True if any(re.search(pattern, normalized) for pattern in _LIVE_PATTERNS) else None


class CapabilityRouter:
    """Select the first matching capability from an ordered rule registry."""

    def __init__(self, rules: tuple[CapabilityRule, ...] | None = None) -> None:
        self.rules = rules or self._default_rules()

    def route(self, routed: RoutedIntent, context: RoutingContext | None = None) -> CapabilityDecision:
        active_context = context or RoutingContext()
        for rule in self.rules:
            decision = rule.match(routed, active_context)
            if decision is not None:
                return decision
        return CapabilityDecision(
            Capability.LLM,
            "ollama_fallback",
            CapabilityStatus.FALLBACK,
            "No deterministic capability matched; use general conversation.",
            routed.confidence,
            context=active_context,
        )

    @staticmethod
    def _default_rules() -> tuple[CapabilityRule, ...]:
        # Imports are local so optional agents do not create router import cycles.
        from backend.app.coding.ai_natural_language import parse_ai_coding_command
        from backend.app.coding.build_natural_language import parse_build_command
        from backend.app.coding.natural_language import parse_coding_command
        from backend.app.github.natural_language import parse_github_command

        def intent(*values: Intent) -> Callable[[RoutedIntent], str | None]:
            return lambda routed: routed.message if routed.intent in values else None
        return (
            MatcherRule("browser_controller", lambda routed: parse_browser_command(routed.message), Capability.BROWSER, "Recognized browser navigation or browser action."),
            MatcherRule("windows_controller", lambda routed: parse_windows_command(routed.message), Capability.WINDOWS, "Recognized Windows application or system action."),
            MatcherRule("live_information", _live_information, Capability.LIVE_INFORMATION, "Request requires current external information.", CapabilityStatus.NOT_IMPLEMENTED),
            MatcherRule("memory_service", IntentMatcher({Intent.MEMORY_QUERY, Intent.MEMORY_WRITE, Intent.MEMORY_FORGET, Intent.REMINDER}), Capability.MEMORY, "Recognized memory operation."),
            MatcherRule("build_controller", lambda routed: parse_build_command(routed.message), Capability.BUILD, "Recognized build action."),
            MatcherRule("ai_coding_controller", lambda routed: parse_ai_coding_command(routed.message), Capability.AI_CODING, "Recognized AI coding action."),
            MatcherRule("coding_controller", lambda routed: parse_coding_command(routed.message), Capability.CODING, "Recognized coding action."),
            MatcherRule("github_controller", lambda routed: parse_github_command(routed.message), Capability.GITHUB, "Recognized GitHub action."),
            MatcherRule("planner_service", intent(Intent.AUTOMATION), Capability.PLANNER, "Recognized planner or automation request."),
            MatcherRule("local_greeting", intent(Intent.GREETING), Capability.GREETING, "Recognized deterministic greeting."),
        )


class IntentMatcher:
    def __init__(self, intents: set[Intent]) -> None:
        self.intents = intents

    def __call__(self, routed: RoutedIntent) -> str | None:
        return routed.message if routed.intent in self.intents else None
