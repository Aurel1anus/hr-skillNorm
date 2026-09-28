import json
import os
import sys
from pathlib import Path

from app.deepseek_matcher import DeepSeekMatcher
from app.jev_matcher import JevMatcher
from app.matchers import MatcherRegistry
from app.normalizer import SkillNormalizer
from app.taxonomy import load_skills


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("用法: python main.py \"技能表达\"")
    skills = load_skills(Path(__file__).parent / "data" / "skills.json")
    provider = os.getenv("SKILL_MATCHER_PROVIDER", "deepseek")
    matcher = MatcherRegistry([DeepSeekMatcher(skills), JevMatcher(skills)]).get(provider)
    normalizer = SkillNormalizer(skills, semantic_matcher=matcher)
    result = normalizer.normalize(sys.argv[1])
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
