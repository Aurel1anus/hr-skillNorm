"""Jev semantic matcher and its provider-specific decision policy."""

import json
import os
import time
from collections.abc import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .schemas import Skill, SkillCandidate, SkillNormalizationResult


class JevClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 10):
        self.api_key = api_key or os.getenv("TYPESAFE_API_KEY")
        self.model = model or os.getenv("JEV_MODEL", "jev-latest")
        self.timeout = timeout

    def choice(self, state: dict, criteria: dict) -> dict:
        if not self.api_key:
            raise RuntimeError("TYPESAFE_API_KEY is required when an exact or alias match misses")
        payload = {
            "state": state,
            "model": self.model,
            "questions": {"skill_match": {
                "type": "choice",
                "instructions": "选择与输入技能表达最匹配的标准技能。优先选择直接支持的最具体技能；不得推断未表达的能力；无可靠匹配时选 __unknown__。",
                "criteria": criteria,
            }},
        }
        request = Request(
            "https://api.typesafe.ai/v1/systemone",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"Jev request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Jev request failed: {exc}") from exc


class JevMatcher:
    provider_name = "jev"
    AUTO_CONFIDENCE = 0.80
    AUTO_MARGIN = 0.15
    UNKNOWN_THRESHOLD = 0.65
    UNKNOWN_ID = "__unknown__"

    def __init__(self, skills: Sequence[Skill], client: JevClient | None = None):
        self._skills = {skill.id: skill for skill in skills}
        self._client = client or JevClient()
        self._criteria = {
            skill.id: {"name": skill.name, "definition": skill.description}
            for skill in skills
        }
        self._criteria[self.UNKNOWN_ID] = {
            "name": "未知技能",
            "definition": "输入表达无法可靠映射到任何现有标准技能，不得因语义相关而强行选择近似技能。",
        }

    def match(self, text: str) -> SkillNormalizationResult:
        started = time.perf_counter()
        result = self._client.choice({"skill_expression": text}, self._criteria)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        answers = result.get("answers", {})
        answer = answers.get("skill_match") if isinstance(answers, dict) else None
        if not isinstance(answer, dict):
            raise RuntimeError("Jev response is missing answers.skill_match")
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, dict) or not probabilities:
            raise RuntimeError("Jev response is missing skill_match probabilities")
        probs = {key: float(value) for key, value in probabilities.items() if key in self._criteria and isinstance(value, (int, float))}
        if not probs:
            raise RuntimeError("Jev response has no valid skill probabilities")
        ranked = sorted(probs.items(), key=lambda item: item[1], reverse=True)
        top_id, top_prob = ranked[0]
        confidence = answer.get("confidence")
        confidence = min(1.0, max(0.0, float(confidence))) if isinstance(confidence, (int, float)) else top_prob
        margin = top_prob - (ranked[1][1] if len(ranked) > 1 else 0.0)

        if top_id == self.UNKNOWN_ID:
            match_type = "unknown" if top_prob >= self.UNKNOWN_THRESHOLD else "review"
            skill_id = None
        elif confidence >= self.AUTO_CONFIDENCE and margin >= self.AUTO_MARGIN:
            match_type, skill_id = "semantic", top_id
        else:
            match_type, skill_id = "review", None

        candidates = [
            SkillCandidate(skill_id, self._skills[skill_id].name, probability)
            for skill_id, probability in ranked if skill_id != self.UNKNOWN_ID
        ][:3]
        skill = self._skills.get(skill_id) if skill_id else None
        usage = result.get("usage") or {}
        return SkillNormalizationResult(
            raw_text=text, skill_id=skill.id if skill else None,
            canonical_name=skill.name if skill else None, score=confidence,
            match_type=match_type, needs_review=match_type != "semantic", candidates=candidates,
            provider="jev", latency_ms=elapsed_ms,
            input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens"),
        )
