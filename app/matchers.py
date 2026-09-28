"""Shared matcher contract and provider registry."""

from collections.abc import Sequence
from typing import Protocol

from .schemas import Skill, SkillNormalizationResult


class SemanticMatcher(Protocol):
    provider_name: str

    def match(self, text: str) -> SkillNormalizationResult: ...


class MatcherRegistry:
    def __init__(self, matchers: Sequence[SemanticMatcher]):
        self._matchers = {matcher.provider_name: matcher for matcher in matchers}

    def get(self, provider: str) -> SemanticMatcher:
        try:
            return self._matchers[provider]
        except KeyError as exc:
            raise ValueError(f"Unsupported semantic matcher: {provider}") from exc

    def providers(self) -> list[str]:
        return list(self._matchers)
