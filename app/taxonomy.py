import json
from pathlib import Path

from .schemas import Skill


def load_skills(path: str | Path) -> list[Skill]:
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    skills = [Skill(**record) for record in records]
    ids = [skill.id for skill in skills]
    if len(ids) != len(set(ids)):
        raise ValueError("taxonomy contains duplicate skill ids")
    return skills
