import unittest

from app.deepseek_matcher import DeepSeekMatcher
from app.schemas import Skill


SKILLS = [
    Skill("data_analysis", "数据分析"),
    Skill("metric_analysis", "指标分析"),
]


class DeepSeekMatcherTests(unittest.TestCase):
    def setUp(self):
        self.matcher = DeepSeekMatcher(SKILLS)

    def test_auto_match_uses_taxonomy_skill(self):
        result = self.matcher._parse(
            "分析指标",
            '{"skill_id":"metric_analysis","decision":"auto_match","confidence":0.9,"top3_skill_ids":["data_analysis"]}',
        )
        self.assertEqual(result.skill_id, "metric_analysis")
        self.assertFalse(result.needs_review)
        self.assertEqual([item.skill_id for item in result.candidates], ["metric_analysis", "data_analysis"])

    def test_invalid_auto_match_becomes_review(self):
        result = self.matcher._parse(
            "未知技能",
            '{"skill_id":"missing","decision":"auto_match","confidence":0.9,"top3_skill_ids":[]}',
        )
        self.assertEqual(result.match_type, "review")
        self.assertTrue(result.needs_review)


if __name__ == "__main__":
    unittest.main()
