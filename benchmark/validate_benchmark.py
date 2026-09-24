"""Skill Normalizer benchmark 自检脚本。

用法:
    python benchmark/validate_benchmark.py

校验 10 项数据自检规则（见任务说明第十五节），并额外检查
benchmark 泄漏（semantic/context/ambiguous/unknown 输入不得等于任何 alias）。
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_PATH = PROJECT_ROOT / "data" / "skills.json"
CASES_PATH = PROJECT_ROOT / "benchmark" / "cases.json"

DOMAINS = ["跨境电商/运营", "HR/招聘", "数据", "办公软件", "软件开发", "产品"]
CASE_TYPES = ["canonical", "alias", "semantic", "context", "ambiguous", "unknown"]
DIFFICULTIES = ["easy", "medium", "hard"]

TARGET_TYPE_RATIO = {
    "canonical": 0.10,
    "alias": 0.20,
    "semantic": 0.20,
    "context": 0.25,
    "ambiguous": 0.15,
    "unknown": 0.10,
}


def normalize(text: str) -> str:
    return text.strip().lower().replace(" ", "")


def load() -> tuple[list[dict], list[dict]]:
    skills = json.loads(SKILLS_PATH.read_text(encoding="utf-8"))
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return skills, cases


def check(skills: list[dict], cases: list[dict]) -> list[str]:
    errors: list[str] = []
    skill_ids = [skill["id"] for skill in skills]
    skill_id_set = set(skill_ids)

    # 1. id 唯一（skills 与 cases）
    for label, ids in (("skill", skill_ids), ("case", [case["id"] for case in cases])):
        duplicated = [key for key, count in Counter(ids).items() if count > 1]
        if duplicated:
            errors.append(f"[1] {label} id 重复: {duplicated}")

    # 2/3. expected_skill 与 acceptable_skills 必须存在于 skills.json
    for case in cases:
        expected = case["expected_skill"]
        if expected is not None and expected not in skill_id_set:
            errors.append(f"[2] {case['id']} expected_skill 不存在: {expected}")
        for acceptable in case["acceptable_skills"]:
            if acceptable not in skill_id_set:
                errors.append(f"[3] {case['id']} acceptable_skill 不存在: {acceptable}")
            if acceptable == expected:
                errors.append(f"[3] {case['id']} acceptable 与 expected 重复: {acceptable}")

    # 4/5. parent_id 必须存在，且不能是自身
    for skill in skills:
        parent_id = skill["parent_id"]
        if parent_id is None:
            continue
        if parent_id not in skill_id_set:
            errors.append(f"[4] {skill['id']} parent_id 不存在: {parent_id}")
        if parent_id == skill["id"]:
            errors.append(f"[5] {skill['id']} 的 parent_id 指向自己")

    # 5b. parent 链不能成环
    parent_of = {skill["id"]: skill["parent_id"] for skill in skills}
    for skill_id in skill_ids:
        seen = {skill_id}
        cursor = parent_of.get(skill_id)
        while cursor:
            if cursor in seen:
                errors.append(f"[5] {skill_id} 的 parent 链存在环: {cursor}")
                break
            seen.add(cursor)
            cursor = parent_of.get(cursor)

    # 6/7. aliases 自身不重复；同一 alias 不得归属多个 skill（含 name 冲突）
    owner: dict[str, set[str]] = defaultdict(set)
    for skill in skills:
        keys = [normalize(alias) for alias in skill["aliases"]]
        duplicated = [key for key, count in Counter(keys).items() if count > 1]
        if duplicated:
            errors.append(f"[6] {skill['id']} alias 内部重复: {duplicated}")
        for text in [skill["name"], *skill["aliases"]]:
            owner[normalize(text)].add(skill["id"])
    for key, ids in owner.items():
        if len(ids) > 1:
            errors.append(f"[7] 同一名称/alias 归属多个 skill: {key} -> {sorted(ids)}")

    # 8. case 不得重复（id 唯一之外，输入也不能完全重复）
    duplicated_inputs = [text for text, count in Counter(case["input"] for case in cases).items() if count > 1]
    if duplicated_inputs:
        errors.append(f"[8] case input 完全重复: {duplicated_inputs}")

    # 9/10. type 与 difficulty 枚举
    for case in cases:
        if case["type"] not in CASE_TYPES:
            errors.append(f"[9] {case['id']} type 非法: {case['type']}")
        if case["difficulty"] not in DIFFICULTIES:
            errors.append(f"[10] {case['id']} difficulty 非法: {case['difficulty']}")
        if case["domain"] not in DOMAINS:
            errors.append(f"[9] {case['id']} domain 非法: {case['domain']}")
        if case["type"] == "unknown" and (case["expected_skill"] is not None or case["acceptable_skills"]):
            errors.append(f"[9] {case['id']} unknown case 不应有 expected/acceptable")

    # 附加：benchmark 泄漏检查（输入不得等于任何 name/alias）
    for case in cases:
        if case["type"] in {"semantic", "context", "ambiguous", "unknown"}:
            if normalize(case["input"]) in owner:
                errors.append(f"[泄漏] {case['id']} 输入与 taxonomy 的 name/alias 完全相同: {case['input']}")

    return errors


def report(skills: list[dict], cases: list[dict]) -> None:
    total = len(cases)
    print(f"canonical skills: {len(skills)}")
    print(f"benchmark cases : {total}")
    print("\n[domain 分布]")
    for domain, count in Counter(case["domain"] for case in cases).most_common():
        print(f"  {domain:<12} {count}")
    print("\n[type 分布]")
    for case_type in CASE_TYPES:
        count = sum(1 for case in cases if case["type"] == case_type)
        print(f"  {case_type:<10} {count:>3}  ({count / total:.1%}, 目标 {TARGET_TYPE_RATIO[case_type]:.0%})")
    print("\n[difficulty 分布]")
    for level, count in Counter(case["difficulty"] for case in cases).most_common():
        print(f"  {level:<7} {count}")
    print("\n[skill 分布]")
    for domain, count in Counter(skill["domain"] for skill in skills).most_common():
        print(f"  {domain:<12} {count}")
    print(f"\n有 parent 的子技能: {sum(1 for skill in skills if skill['parent_id'])}")
    print(f"ambiguous case    : {sum(1 for case in cases if case['type'] == 'ambiguous')}")
    print(f"unknown case      : {sum(1 for case in cases if case['type'] == 'unknown')}")

    # 每个领域 × 每种类型的覆盖矩阵
    print("\n[domain x type 覆盖]")
    header = "  " + "domain".ljust(12) + "".join(t[:9].ljust(11) for t in CASE_TYPES)
    print(header)
    for domain in DOMAINS:
        row = [sum(1 for case in cases if case["domain"] == domain and case["type"] == case_type) for case_type in CASE_TYPES]
        print("  " + domain.ljust(12) + "".join(str(value).ljust(11) for value in row))


def main() -> int:
    skills, cases = load()
    report(skills, cases)
    errors = check(skills, cases)
    print()
    if errors:
        print(f"[FAIL] 发现 {len(errors)} 个问题:")
        for error in errors:
            print("  -", error)
        return 1
    print("[OK] 10 项自检全部通过，未发现 benchmark 泄漏")
    return 0


if __name__ == "__main__":
    sys.exit(main())
