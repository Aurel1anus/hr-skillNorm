from dataclasses import asdict, dataclass, field
from typing import Literal

MatchType = Literal["exact", "semantic", "review", "unknown"]


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    domain: str | None = None
    category: str | None = None
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    parent_id: str | None = None


@dataclass(frozen=True)
class SkillCandidate:
    skill_id: str
    name: str
    score: float


@dataclass(frozen=True)
class SkillNormalizationResult:
    raw_text: str
    skill_id: str | None
    canonical_name: str | None
    score: float | None
    match_type: MatchType
    needs_review: bool
    candidates: list[SkillCandidate] = field(default_factory=list)

    @property
    def normalized(self) -> dict[str, str] | None:
        if self.skill_id is None or self.canonical_name is None:
            return None
        return {"skill_id": self.skill_id, "canonical_name": self.canonical_name}

    def to_dict(self) -> dict:
        value = asdict(self)
        value["normalized"] = self.normalized
        return value
