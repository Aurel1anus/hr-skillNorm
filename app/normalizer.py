from collections.abc import Callable

from .alias_matcher import AliasMatcher
from .schemas import Skill, SkillNormalizationResult


FallbackMatcher = Callable[[str], SkillNormalizationResult]


class SkillNormalizer:
    def __init__(
        self,
        skills: list[Skill],
        fallback_matcher: FallbackMatcher | None = None,
    ):
        self._alias_matcher = AliasMatcher(skills)
        self._fallback_matcher = fallback_matcher

    def normalize(self, text: str) -> SkillNormalizationResult:
        raw_text = text
        exact = self._alias_matcher.match(text)
        if exact:
            return SkillNormalizationResult(
                raw_text, exact.id, exact.name, 1.0, "exact", False
            )

        if self._fallback_matcher is None:
            return SkillNormalizationResult(raw_text, None, None, None, "unknown", True)
        return self._fallback_matcher(raw_text)

    def normalize_many(self, texts: list[str]) -> list[SkillNormalizationResult]:
        return [self.normalize(text) for text in texts]
