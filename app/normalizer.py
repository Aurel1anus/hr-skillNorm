from collections.abc import Callable, Sequence

from .alias_matcher import AliasMatcher
from .config import MARGIN_THRESHOLD, SEMANTIC_THRESHOLD, TOP_K, UNKNOWN_THRESHOLD
from .schemas import Skill, SkillCandidate, SkillNormalizationResult


SemanticMatcher = Callable[[str, int], Sequence[SkillCandidate]]


class SkillNormalizer:
    def __init__(
        self,
        skills: list[Skill],
        semantic_matcher: SemanticMatcher | None = None,
        top_k: int = TOP_K,
        semantic_threshold: float = SEMANTIC_THRESHOLD,
        unknown_threshold: float = UNKNOWN_THRESHOLD,
        margin_threshold: float = MARGIN_THRESHOLD,
    ):
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        self._alias_matcher = AliasMatcher(skills)
        self._semantic_matcher = semantic_matcher
        self._top_k = top_k
        self._semantic_threshold = semantic_threshold
        self._unknown_threshold = unknown_threshold
        self._margin_threshold = margin_threshold

    def normalize(self, text: str) -> SkillNormalizationResult:
        raw_text = text
        exact = self._alias_matcher.match(text)
        if exact:
            return SkillNormalizationResult(
                raw_text, exact.id, exact.name, 1.0, "exact", False
            )

        if self._semantic_matcher is None:
            return SkillNormalizationResult(raw_text, None, None, None, "unknown", True)

        candidates = list(self._semantic_matcher(text, self._top_k))[: self._top_k]
        if not candidates:
            return SkillNormalizationResult(raw_text, None, None, None, "unknown", True)

        top = candidates[0]
        margin = top.score - candidates[1].score if len(candidates) > 1 else top.score
        if top.score < self._unknown_threshold:
            match_type = "unknown"
            normalized = None
        elif top.score >= self._semantic_threshold and margin >= self._margin_threshold:
            match_type = "semantic"
            normalized = top
        else:
            match_type = "review"
            normalized = None

        return SkillNormalizationResult(
            raw_text,
            normalized.skill_id if normalized else None,
            normalized.name if normalized else None,
            top.score,
            match_type,
            match_type != "semantic",
            candidates,
        )

    def normalize_many(self, texts: list[str]) -> list[SkillNormalizationResult]:
        return [self.normalize(text) for text in texts]
