from collections.abc import Sequence

from .schemas import Skill, SkillCandidate


def build_skill_document(skill: Skill) -> str:
    aliases = "、".join(skill.aliases)
    return f"{skill.name}。{skill.description}。相关表达：{aliases}"


class EmbeddingMatcher:
    def __init__(
        self,
        skills: list[Skill],
        model_name: str,
        device: str | None = None,
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Embedding matching requires sentence-transformers; "
                "install dependencies with: pip install -r requirements.txt"
            ) from exc

        self._skills = skills
        self._model = SentenceTransformer(model_name, **({"device": device} if device else {}))
        documents = [build_skill_document(skill) for skill in skills]
        self._embeddings = self._model.encode(
            documents,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

    def match(self, text: str, top_k: int) -> Sequence[SkillCandidate]:
        if not text.strip() or not self._skills:
            return []

        query_embedding = self._model.encode(
            [text],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]
        scores = self._embeddings @ query_embedding
        ranked_indexes = scores.argsort()[::-1][:top_k]
        return [
            SkillCandidate(
                skill_id=self._skills[index].id,
                name=self._skills[index].name,
                score=float(scores[index]),
            )
            for index in ranked_indexes
        ]
