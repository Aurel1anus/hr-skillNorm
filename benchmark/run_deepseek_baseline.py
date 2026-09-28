"""Run the DeepSeek-only Skill Normalizer baseline.

This runner deliberately has no embedding, retrieval, or alias-match fallback:
DeepSeek receives the complete taxonomy and makes one classification decision per
input.  It reuses the existing benchmark evaluator so its metrics are directly
comparable with ``run_benchmark.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.taxonomy import load_skills  # noqa: E402
from benchmark.evaluation import evaluate, print_report  # noqa: E402


SKILLS_PATH = PROJECT_ROOT / "data" / "skills.json"
CASES_PATH = PROJECT_ROOT / "benchmark" / "cases.json"
DECISIONS = {"auto_match", "review", "unknown"}


def build_system_prompt(skills: list[Any], include_aliases: bool) -> str:
    taxonomy = []
    for skill in skills:
        item = {
            "id": skill.id,
            "name": skill.name,
            "domain": skill.domain,
            "description": skill.description,
            "parent_id": skill.parent_id,
        }
        if include_aliases:
            item["aliases"] = skill.aliases
        taxonomy.append(item)

    return """你是招聘技能标准化分类器。将输入文本映射到给定 Taxonomy 的一个标准技能，或拒识。

规则：
1. 只能选择 Taxonomy 中存在的 skill_id。
2. 输入可能是标准名、别名、简短技能表达或岗位职责句。
3. 文本明确对应一个技能时，decision 为 auto_match。
4. 多个候选同样合理、文本含并列技能且无法确定主技能时，decision 为 review。
5. Taxonomy 没有合适技能时，decision 为 unknown。不要因词面相似而强行映射。
6. 输出必须是 JSON 对象，不要 Markdown；reason 不超过 40 个汉字。

JSON schema（示例中的值仅为类型说明）：
{"skill_id":"string 或 null","decision":"auto_match | review | unknown","confidence":0.0,"top3_skill_ids":["最多 3 个 Taxonomy skill_id"],"reason":"简短理由"}

Taxonomy：
""" + json.dumps(taxonomy, ensure_ascii=False, separators=(",", ":"))


def post_chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    input_text: str,
    timeout: float,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 256,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"输入文本：{input_text}\n请输出 JSON。"},
        ],
    }
    request = Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(str(exc)) from exc


def adapt_response(
    raw_text: str,
    content: str,
    skills_by_id: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    try:
        model_result = json.loads(content)
    except json.JSONDecodeError as exc:
        return review_result(raw_text), f"invalid_json: {exc.msg}"
    if not isinstance(model_result, dict):
        return review_result(raw_text), "invalid_json: expected object"

    decision = model_result.get("decision")
    skill_id = model_result.get("skill_id")
    candidate_ids = model_result.get("top3_skill_ids", [])
    if not isinstance(candidate_ids, list):
        candidate_ids = []
    candidate_ids = list(dict.fromkeys(
        item for item in candidate_ids if isinstance(item, str) and item in skills_by_id
    ))[:3]
    confidence = model_result.get("confidence", 0.0)
    confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.0
    confidence = min(1.0, max(0.0, confidence))

    if decision not in DECISIONS:
        return review_result(raw_text, confidence), "invalid_json: invalid decision"
    if decision == "auto_match":
        if not isinstance(skill_id, str) or skill_id not in skills_by_id:
            return review_result(raw_text, confidence), "invalid_json: invalid auto_match skill_id"
        candidate_ids = [skill_id, *[item for item in candidate_ids if item != skill_id]][:3]

    match_type = {"auto_match": "semantic", "review": "review", "unknown": "unknown"}[decision]
    return {
        "raw_text": raw_text,
        "skill_id": skill_id if decision == "auto_match" else None,
        "canonical_name": skills_by_id[skill_id].name if decision == "auto_match" else None,
        "score": confidence,
        "match_type": match_type,
        "needs_review": decision != "auto_match",
        "candidates": candidates(candidate_ids, skills_by_id, confidence),
        "normalized": (
            {"skill_id": skill_id, "canonical_name": skills_by_id[skill_id].name}
            if decision == "auto_match" else None
        ),
    }, None


def candidates(ids: list[str], skills_by_id: dict[str, Any], confidence: float) -> list[dict[str, Any]]:
    return [
        {"skill_id": skill_id, "name": skills_by_id[skill_id].name, "score": max(0.0, confidence - index * 0.01)}
        for index, skill_id in enumerate(ids)
    ]


def review_result(raw_text: str, confidence: float = 0.0) -> dict[str, Any]:
    # This result represents an API/format failure, not a semantic fallback.
    return {
        "raw_text": raw_text,
        "skill_id": None,
        "canonical_name": None,
        "score": confidence,
        "match_type": "review",
        "needs_review": True,
        "candidates": [],
        "normalized": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the DeepSeek-only benchmark baseline")
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    parser.add_argument("--base-url", default=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    parser.add_argument("--json-out", type=Path, default=PROJECT_ROOT / "benchmark" / "deepseek_results.json")
    parser.add_argument("--limit", type=int, help="run only the first N cases")
    parser.add_argument("--max-errors", type=int, default=20)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--sleep-ms", type=int, default=0)
    parser.add_argument("--without-aliases", action="store_true", help="omit aliases from the model taxonomy")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is required")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")

    skills = load_skills(SKILLS_PATH)
    skills_by_id = {skill.id: skill for skill in skills}
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[:args.limit]
    system_prompt = build_system_prompt(skills, include_aliases=not args.without_aliases)
    results: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []

    for index, case in enumerate(cases, start=1):
        started = time.perf_counter()
        response: dict[str, Any] | None = None
        error: str | None = None
        for attempt in range(args.max_retries + 1):
            try:
                response = post_chat_completion(args.base_url, api_key, args.model, system_prompt, case["input"], args.timeout)
                break
            except RuntimeError as exc:
                error = str(exc)
                if attempt < args.max_retries:
                    time.sleep(2 ** attempt)

        if response is None:
            result = review_result(case["input"])
            raw_content = None
        else:
            choices = response.get("choices")
            first_choice = choices[0] if isinstance(choices, list) and choices else {}
            raw_content = first_choice.get("message", {}).get("content", "") if isinstance(first_choice, dict) else ""
            if not isinstance(raw_content, str):
                raw_content = ""
            result, parse_error = adapt_response(case["input"], raw_content, skills_by_id)
            error = error or parse_error
        results.append(result)
        traces.append({
            "case_id": case["id"],
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "usage": response.get("usage") if response else None,
            "raw_response": response,
            "api_error": error,
        })
        print(f"[{index}/{len(cases)}] {case['id']} -> {result['match_type']}", flush=True)
        if args.sleep_ms and index < len(cases):
            time.sleep(args.sleep_ms / 1000)

    metrics = evaluate(cases, results)
    print_report(metrics, args.max_errors)
    payload = {
        "experiment": {
            "name": "deepseek_only_full_taxonomy_v1" if not args.without_aliases else "deepseek_only_no_aliases_v1",
            "model": args.model,
            "base_url": args.base_url,
            "temperature": 0,
            "max_tokens": 256,
            "taxonomy_sha256": hashlib.sha256(SKILLS_PATH.read_bytes()).hexdigest(),
            "prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
            "run_at": datetime.now(timezone.utc).isoformat(),
        },
        "metrics": metrics,
        "results": results,
        "traces": traces,
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON report          : {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
