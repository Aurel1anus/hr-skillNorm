import json
import sys
from pathlib import Path

from app.config import (
    MARGIN_THRESHOLD,
    MODEL_PATH,
    SEMANTIC_THRESHOLD,
    TOP_K,
    UNKNOWN_THRESHOLD,
)
from app.embedding_matcher import EmbeddingMatcher
from app.normalizer import SkillNormalizer
from app.taxonomy import load_skills


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("用法: python main.py \"技能表达\"")
    skills = load_skills(Path(__file__).parent / "data" / "skills.json")
    matcher = None

    def semantic_match(text: str, top_k: int):
        nonlocal matcher
        if matcher is None:
            matcher = EmbeddingMatcher(skills, str(MODEL_PATH))
        return matcher.match(text, top_k)

    normalizer = SkillNormalizer(
        skills,
        semantic_matcher=semantic_match,
        top_k=TOP_K,
        semantic_threshold=SEMANTIC_THRESHOLD,
        unknown_threshold=UNKNOWN_THRESHOLD,
        margin_threshold=MARGIN_THRESHOLD,
    )
    result = normalizer.normalize(sys.argv[1])
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
