"""Run the Skill Normalizer benchmark.

Usage:
    python benchmark/run_benchmark.py
    python benchmark/run_benchmark.py --json-out benchmark/results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import (  # noqa: E402
    MARGIN_THRESHOLD,
    MODEL_PATH,
    SEMANTIC_THRESHOLD,
    TOP_K,
    UNKNOWN_THRESHOLD,
)
from app.embedding_matcher import EmbeddingMatcher  # noqa: E402
from app.normalizer import SkillNormalizer  # noqa: E402
from app.taxonomy import load_skills  # noqa: E402


SKILLS_PATH = PROJECT_ROOT / "data" / "skills.json"
CASES_PATH = PROJECT_ROOT / "benchmark" / "cases.json"


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def top_ids(result: dict[str, Any]) -> list[str]:
    if result["match_type"] == "exact" and result["skill_id"]:
        return [result["skill_id"]]
    return [candidate["skill_id"] for candidate in result["candidates"]]


def accepted(case: dict[str, Any], skill_id: str | None) -> bool:
    return skill_id in {case["expected_skill"], *case["acceptable_skills"]}


def evaluate(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(cases)
    known_cases = [case for case in cases if case["expected_skill"] is not None]
    unknown_cases = [case for case in cases if case["expected_skill"] is None]

    top1_hits = 0
    top3_hits = 0
    auto_count = 0
    auto_hits = 0
    review_count = 0
    unknown_count = 0
    unknown_rejection_hits = 0
    errors: list[dict[str, Any]] = []

    for case, result in zip(cases, results):
        candidates = top_ids(result)
        top1 = candidates[0] if candidates else None
        is_unknown_case = case["expected_skill"] is None
        is_accepted = accepted(case, top1) if not is_unknown_case else False

        if is_unknown_case:
            unknown_rejection = result["match_type"] in {"unknown", "review"}
            unknown_rejection_hits += int(unknown_rejection)
        else:
            top1_hits += int(is_accepted)
            top3_hits += int(any(accepted(case, skill_id) for skill_id in candidates[:3]))

        if not result["needs_review"]:
            auto_count += 1
            auto_hits += int(is_accepted)
        review_count += int(result["match_type"] == "review")
        unknown_count += int(result["match_type"] == "unknown")

        case_correct = (
            unknown_rejection if is_unknown_case else is_accepted
        )
        if not case_correct:
            errors.append(
                {
                    "id": case["id"],
                    "input": case["input"],
                    "expected": case["expected_skill"],
                    "actual_top1": top1,
                    "match_type": result["match_type"],
                    "score": result["score"],
                    "top3": candidates[:3],
                }
            )

    def ratio(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 4) if denominator else None

    return {
        "total": total,
        "known_cases": len(known_cases),
        "unknown_cases": len(unknown_cases),
        "top1_accuracy": ratio(top1_hits, len(known_cases)),
        "top3_recall": ratio(top3_hits, len(known_cases)),
        "auto_match_precision": ratio(auto_hits, auto_count),
        "auto_match_count": auto_count,
        "review_rate": ratio(review_count, total),
        "unknown_rate": ratio(unknown_count, total),
        "unknown_rejection": ratio(unknown_rejection_hits, len(unknown_cases)),
        "errors": errors,
    }


def print_report(metrics: dict[str, Any], max_errors: int) -> None:
    print("Skill Normalizer Benchmark")
    print("=" * 28)
    print(f"Cases                 : {metrics['total']}")
    print(f"Known cases           : {metrics['known_cases']}")
    print(f"Unknown cases         : {metrics['unknown_cases']}")
    print(f"Top1 Accuracy         : {format_ratio(metrics['top1_accuracy'])}")
    print(f"Top3 Recall           : {format_ratio(metrics['top3_recall'])}")
    print(f"Auto Match Precision  : {format_ratio(metrics['auto_match_precision'])}")
    print(f"Auto Match Count      : {metrics['auto_match_count']}")
    print(f"Review Rate           : {format_ratio(metrics['review_rate'])}")
    print(f"Unknown Rate          : {format_ratio(metrics['unknown_rate'])}")
    print(f"Unknown Rejection     : {format_ratio(metrics['unknown_rejection'])}")
    print(f"Errors                : {len(metrics['errors'])}")

    if metrics["errors"]:
        print("\nError samples")
        print("-------------")
        for error in metrics["errors"][:max_errors]:
            print(
                f"{error['id']}: {error['input']} | "
                f"expected={error['expected']} | "
                f"top1={error['actual_top1']} | "
                f"type={error['match_type']} | "
                f"top3={error['top3']}"
            )
        remaining = len(metrics["errors"]) - max_errors
        if remaining > 0:
            print(f"... and {remaining} more")


def format_ratio(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2%}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Skill Normalizer benchmark")
    parser.add_argument("--model", type=Path, default=MODEL_PATH, help="local SentenceTransformer model path")
    parser.add_argument("--device", default=None, help="SentenceTransformer device, for example cpu or cuda")
    parser.add_argument("--limit", type=int, default=None, help="run only the first N cases")
    parser.add_argument("--max-errors", type=int, default=20, help="number of error samples to print")
    parser.add_argument("--json-out", type=Path, help="write metrics and per-case results to JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    skills = load_skills(SKILLS_PATH)
    cases = load_cases()
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be at least 1")
        cases = cases[: args.limit]

    matcher = EmbeddingMatcher(skills, str(args.model), device=args.device)
    normalizer = SkillNormalizer(
        skills,
        semantic_matcher=matcher.match,
        top_k=TOP_K,
        semantic_threshold=SEMANTIC_THRESHOLD,
        unknown_threshold=UNKNOWN_THRESHOLD,
        margin_threshold=MARGIN_THRESHOLD,
    )
    results = [normalizer.normalize(case["input"]).to_dict() for case in cases]
    metrics = evaluate(cases, results)
    print_report(metrics, args.max_errors)

    if args.json_out:
        payload = {"metrics": metrics, "results": results}
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON report          : {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
