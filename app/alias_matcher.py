from .schemas import Skill
from .text_normalizer import normalize_text


class AliasMatcher:
    def __init__(self, skills: list[Skill]):
        self._skills = {skill.id: skill for skill in skills}
        self._aliases: dict[str, str] = {}
        for skill in skills:
            for alias in [skill.name, *skill.aliases]:
                key = normalize_text(alias)
                previous = self._aliases.get(key)
                if previous and previous != skill.id:
                    raise ValueError(f"alias maps to multiple skills: {alias}")
                self._aliases[key] = skill.id

    def match(self, text: str) -> Skill | None:
        skill_id = self._aliases.get(normalize_text(text))
        return self._skills.get(skill_id)
