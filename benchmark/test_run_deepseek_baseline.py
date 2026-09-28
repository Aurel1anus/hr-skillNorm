import unittest
from types import SimpleNamespace

from benchmark.run_deepseek_baseline import adapt_response


class DeepSeekBaselineAdapterTest(unittest.TestCase):
    def setUp(self):
        self.skills = {
            "excel": SimpleNamespace(name="Excel"),
            "pivot_table": SimpleNamespace(name="数据透视表"),
        }

    def test_auto_match_is_first_candidate(self):
        result, error = adapt_response(
            "做 Excel 数据透视",
            '{"skill_id":"excel","decision":"auto_match","confidence":0.9,"top3_skill_ids":["pivot_table"]}',
            self.skills,
        )
        self.assertIsNone(error)
        self.assertEqual(result["skill_id"], "excel")
        self.assertEqual([item["skill_id"] for item in result["candidates"]], ["excel", "pivot_table"])

    def test_invalid_skill_becomes_review(self):
        result, error = adapt_response(
            "未知技能",
            '{"skill_id":"missing","decision":"auto_match","confidence":0.9,"top3_skill_ids":[]}',
            self.skills,
        )
        self.assertEqual(result["match_type"], "review")
        self.assertIn("invalid auto_match skill_id", error)


if __name__ == "__main__":
    unittest.main()
