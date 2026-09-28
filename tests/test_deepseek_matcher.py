import unittest
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from app.deepseek_matcher import DeepSeekMatcher, load_env
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

    def test_load_env_preserves_existing_environment(self):
        old_value = os.environ.get("DEEPSEEK_TEST_VALUE")
        try:
            os.environ["DEEPSEEK_TEST_VALUE"] = "shell"
            with TemporaryDirectory() as directory:
                path = Path(directory) / ".env"
                path.write_text('DEEPSEEK_TEST_VALUE=file\nDEEPSEEK_NEW_VALUE="new"\n', encoding="utf-8")
                load_env(path)
            self.assertEqual(os.environ["DEEPSEEK_TEST_VALUE"], "shell")
            self.assertEqual(os.environ["DEEPSEEK_NEW_VALUE"], "new")
        finally:
            os.environ.pop("DEEPSEEK_NEW_VALUE", None)
            if old_value is None:
                os.environ.pop("DEEPSEEK_TEST_VALUE", None)
            else:
                os.environ["DEEPSEEK_TEST_VALUE"] = old_value


if __name__ == "__main__":
    unittest.main()
