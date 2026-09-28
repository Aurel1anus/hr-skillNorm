"""Run the shared benchmark through the selected provider and alias path."""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.deepseek_matcher import DeepSeekMatcher  # noqa: E402
from app.jev_matcher import JevMatcher  # noqa: E402
from app.matchers import MatcherRegistry  # noqa: E402
from app.normalizer import SkillNormalizer  # noqa: E402
from app.taxonomy import load_skills  # noqa: E402
from benchmark.evaluation import evaluate, print_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("deepseek", "jev"), required=True)
    parser.add_argument("--semantic-only", action="store_true", help="skip cases matched by aliases")
    parser.add_argument("--jsonl-out", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    skills = load_skills(ROOT / "data" / "skills.json")
    matcher = MatcherRegistry([DeepSeekMatcher(skills), JevMatcher(skills)]).get(args.provider)
    normalizer = SkillNormalizer(skills, semantic_matcher=matcher)
    cases = json.loads((ROOT / "benchmark" / "cases.json").read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[:args.limit]
    if args.semantic_only:
        cases = [case for case in cases if SkillNormalizer(skills).normalize(case["input"]).match_type != "exact"]

    results, traces = [], []
    for index, case in enumerate(cases, 1):
        started = time.perf_counter()
        result = normalizer.normalize(case["input"])
        item = result.to_dict()
        results.append(item)
        traces.append({"case_id": case["id"], "latency_ms": round((time.perf_counter() - started) * 1000), "result": item})
        print(f"[{index}/{len(cases)}] {case['id']} -> {result.match_type}", flush=True)

    metrics = evaluate(cases, results)
    print_report(metrics, 20)
    output = args.jsonl_out or ROOT / "benchmark" / "results" / f"{args.provider}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in traces), encoding="utf-8")
    print(f"JSONL report          : {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
