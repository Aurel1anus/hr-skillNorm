import json
import os
from collections.abc import Sequence
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .schemas import Skill, SkillCandidate, SkillNormalizationResult


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)


load_env(Path(__file__).resolve().parents[1] / ".env")


class DeepSeekMatcher:
    def __init__(self, skills: Sequence[Skill]):
        self._skills = {skill.id: skill for skill in skills}
        self._api_key = os.getenv("DEEPSEEK_API_KEY")
        self._base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self._model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self._system_prompt = self._build_prompt(skills)

    def match(self, text: str) -> SkillNormalizationResult:
        if not self._api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required when an exact or alias match misses")
        payload = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": f"输入文本：{text}\n请输出 JSON。"},
            ],
        }
        request = Request(
            self._base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"DeepSeek request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"DeepSeek request failed: {exc}") from exc

        choices = body.get("choices")
        content = choices[0].get("message", {}).get("content") if isinstance(choices, list) and choices else None
        return self._parse(text, content)

    def _parse(self, raw_text: str, content: object) -> SkillNormalizationResult:
        try:
            value = json.loads(content) if isinstance(content, str) else {}
        except json.JSONDecodeError:
            value = {}
        decision = value.get("decision") if isinstance(value, dict) else None
        skill_id = value.get("skill_id") if isinstance(value, dict) else None
        confidence = value.get("confidence", 0.0) if isinstance(value, dict) else 0.0
        confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.0
        confidence = min(1.0, max(0.0, confidence))
        candidate_ids = value.get("top3_skill_ids", []) if isinstance(value, dict) else []
        if not isinstance(candidate_ids, list):
            candidate_ids = []
        candidate_ids = list(dict.fromkeys(
            candidate_id for candidate_id in candidate_ids
            if isinstance(candidate_id, str) and candidate_id in self._skills
        ))[:3]

        if decision == "auto_match" and isinstance(skill_id, str) and skill_id in self._skills:
            candidate_ids = [skill_id, *[item for item in candidate_ids if item != skill_id]][:3]
            skill = self._skills[skill_id]
            return SkillNormalizationResult(
                raw_text, skill.id, skill.name, confidence, "semantic", False,
                self._candidates(candidate_ids, confidence),
            )
        if decision == "unknown":
            return SkillNormalizationResult(
                raw_text, None, None, confidence, "unknown", True,
                self._candidates(candidate_ids, confidence),
            )
        return SkillNormalizationResult(
            raw_text, None, None, confidence, "review", True,
            self._candidates(candidate_ids, confidence),
        )

    def _candidates(self, ids: list[str], confidence: float) -> list[SkillCandidate]:
        return [
            SkillCandidate(skill_id, self._skills[skill_id].name, max(0.0, confidence - index * 0.01))
            for index, skill_id in enumerate(ids)
        ]

    @staticmethod
    def _build_prompt(skills: Sequence[Skill]) -> str:
        taxonomy = [
            {
                "id": skill.id,
                "name": skill.name,
                "domain": skill.domain,
                "description": skill.description,
                "aliases": skill.aliases,
                "parent_id": skill.parent_id,
            }
            for skill in skills
        ]
        return """你是招聘技能标准化分类器。将输入文本映射到给定 Taxonomy 的一个标准技能，或拒识。

规则：只能选择 Taxonomy 中存在的 skill_id。文本明确对应一个技能时 decision 为 auto_match；多个候选同样合理时为 review；Taxonomy 没有合适技能时为 unknown。不要因词面相似而强行映射。输出必须是 JSON 对象，不要 Markdown。

JSON 格式：{"skill_id":"string 或 null","decision":"auto_match | review | unknown","confidence":0.0,"top3_skill_ids":["最多 3 个 Taxonomy skill_id"]}

Taxonomy：
""" + json.dumps(taxonomy, ensure_ascii=False, separators=(",", ":"))
