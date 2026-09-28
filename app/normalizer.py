from collections.abc import Callable
from typing import Protocol

from .alias_matcher import AliasMatcher
from .schemas import Skill, SkillNormalizationResult


FallbackMatcher = Callable[[str], SkillNormalizationResult]


class Matcher(Protocol):
    provider_name: str

    def match(self, text: str) -> SkillNormalizationResult: ...


class SkillNormalizer:
    def __init__(
        self,
        skills: list[Skill],
        fallback_matcher: FallbackMatcher | None = None,
        semantic_matcher: Matcher | None = None,
    ):
        self._alias_matcher = AliasMatcher(skills)
        self._fallback_matcher = semantic_matcher.match if semantic_matcher else fallback_matcher

    def normalize(self, text: str) -> SkillNormalizationResult:
        raw_text = text
        exact = self._alias_matcher.match(text)
        if exact:
            return SkillNormalizationResult(
                raw_text, exact.id, exact.name, 1.0, "exact", False
            )

        if self._fallback_matcher is None:
            return SkillNormalizationResult(raw_text, None, None, None, "unknown", True)
        result = self._fallback_matcher(raw_text)
        if result.raw_text != raw_text:
            from dataclasses import replace
            result = replace(result, raw_text=raw_text)
        return result

    def normalize_many(self, texts: list[str]) -> list[SkillNormalizationResult]:
        return [self.normalize(text) for text in texts]
