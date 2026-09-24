import unittest

from app.normalizer import SkillNormalizer
from app.schemas import Skill, SkillCandidate


SKILLS = [
    Skill("data_analysis", "数据分析", aliases=["运营数据分析"]),
    Skill("inventory_management", "库存管理", aliases=["库存预测"]),
]


class SkillNormalizerTests(unittest.TestCase):
    def test_exact_match_uses_name_and_alias(self):
        result = SkillNormalizer(SKILLS).normalize(" 库存 预测 ")
        self.assertEqual(result.match_type, "exact")
        self.assertEqual(result.skill_id, "inventory_management")
        self.assertEqual(result.score, 1.0)

    def test_without_model_returns_safe_unknown(self):
        result = SkillNormalizer(SKILLS).normalize("神秘能力")
        self.assertEqual(result.match_type, "unknown")
        self.assertTrue(result.needs_review)

    def test_threshold_and_margin(self):
        def matcher(_text, _top_k):
            return [
                SkillCandidate("data_analysis", "数据分析", 0.84),
                SkillCandidate("inventory_management", "库存管理", 0.83),
            ]

        result = SkillNormalizer(SKILLS, matcher).normalize("分析业务")
        self.assertEqual(result.match_type, "review")
        self.assertIsNone(result.skill_id)


if __name__ == "__main__":
    unittest.main()
