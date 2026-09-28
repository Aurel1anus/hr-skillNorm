from typing import Any


def _accepted(case: dict[str, Any], skill_id: str | None) -> bool:
    return skill_id in {case["expected_skill"], *case["acceptable_skills"]}


def _top_ids(result: dict[str, Any]) -> list[str]:
    if result["match_type"] == "exact" and result["skill_id"]:
        return [result["skill_id"]]
    return [candidate["skill_id"] for candidate in result["candidates"]]


def evaluate(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    known_cases = [case for case in cases if case["expected_skill"] is not None]
    unknown_cases = [case for case in cases if case["expected_skill"] is None]
    top1_hits = top3_hits = auto_count = auto_hits = review_count = unknown_count = unknown_rejection_hits = 0
    errors: list[dict[str, Any]] = []

    for case, result in zip(cases, results):
        candidates = _top_ids(result)
        top1 = candidates[0] if candidates else None
        is_unknown = case["expected_skill"] is None
        accepted = _accepted(case, top1) if not is_unknown else False
        rejected = result["match_type"] in {"unknown", "review"}
        if is_unknown:
            unknown_rejection_hits += int(rejected)
        else:
            top1_hits += int(accepted)
            top3_hits += int(any(_accepted(case, skill_id) for skill_id in candidates[:3]))
        if not result["needs_review"]:
            auto_count += 1
            auto_hits += int(accepted)
        review_count += int(result["match_type"] == "review")
        unknown_count += int(result["match_type"] == "unknown")
        if not (rejected if is_unknown else accepted):
            errors.append({
                "id": case["id"], "input": case["input"], "expected": case["expected_skill"],
                "actual_top1": top1, "match_type": result["match_type"],
                "score": result["score"], "top3": candidates[:3],
            })

    def ratio(numerator: int, denominator: int) -> float | None:
        return round(numerator / denominator, 4) if denominator else None

    return {
        "total": len(cases), "known_cases": len(known_cases), "unknown_cases": len(unknown_cases),
        "top1_accuracy": ratio(top1_hits, len(known_cases)),
        "top3_recall": ratio(top3_hits, len(known_cases)),
        "auto_match_precision": ratio(auto_hits, auto_count), "auto_match_count": auto_count,
        "review_rate": ratio(review_count, len(cases)), "unknown_rate": ratio(unknown_count, len(cases)),
        "unknown_rejection": ratio(unknown_rejection_hits, len(unknown_cases)), "errors": errors,
    }


def print_report(metrics: dict[str, Any], max_errors: int) -> None:
    print("Skill Normalizer Benchmark\n" + "=" * 28)
    labels = {
        "total": "Cases", "known_cases": "Known cases", "unknown_cases": "Unknown cases",
        "top1_accuracy": "Top1 Accuracy", "top3_recall": "Top3 Recall",
        "auto_match_precision": "Auto Match Precision", "auto_match_count": "Auto Match Count",
        "review_rate": "Review Rate", "unknown_rate": "Unknown Rate", "unknown_rejection": "Unknown Rejection",
    }
    for key, label in labels.items():
        value = metrics[key]
        print(f"{label:<22}: {value:.2%}" if isinstance(value, float) else f"{label:<22}: {value}")
    print(f"Errors                 : {len(metrics['errors'])}")
    for error in metrics["errors"][:max_errors]:
        print(f"{error['id']}: expected={error['expected']} | top1={error['actual_top1']} | top3={error['top3']}")
