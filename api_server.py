"""HTTP bridge for the Skill Normalizer and its local BGE matcher."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import (
    MARGIN_THRESHOLD,
    MODEL_PATH,
    SEMANTIC_THRESHOLD,
    TOP_K,
    UNKNOWN_THRESHOLD,
)
from app.embedding_matcher import EmbeddingMatcher
from app.normalizer import SkillNormalizer
from app.taxonomy import load_skills


BASE_DIR = Path(__file__).parent
SKILLS_PATH = BASE_DIR / "data" / "skills.json"
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Skill Normalizer", version="0.1.0")

# Allow browsers served from the static mount to talk to the API without
# worrying about CORS during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_skills = load_skills(SKILLS_PATH)
_matcher = None


def semantic_match(text: str, top_k: int):
    """Load the local model once, only when an exact match misses."""
    global _matcher
    if _matcher is None:
        _matcher = EmbeddingMatcher(_skills, str(MODEL_PATH))
    return _matcher.match(text, top_k)


_normalizer = SkillNormalizer(
    _skills,
    semantic_matcher=semantic_match,
    top_k=TOP_K,
    semantic_threshold=SEMANTIC_THRESHOLD,
    unknown_threshold=UNKNOWN_THRESHOLD,
    margin_threshold=MARGIN_THRESHOLD,
)


class NormalizeRequest(BaseModel):
    text: str


class NormalizeManyRequest(BaseModel):
    texts: list[str]


@app.get("/api/skills")
def list_skills():
    """Return the full taxonomy."""
    return [
        {
            "id": skill.id,
            "name": skill.name,
            "category": skill.category or skill.domain,
            "domain": skill.domain,
            "description": skill.description,
            "aliases": skill.aliases,
        }
        for skill in _skills
    ]


@app.post("/api/normalize")
def normalize_one(req: NormalizeRequest):
    """Normalize a single skill expression."""
    return _normalizer.normalize(req.text).to_dict()


@app.post("/api/normalize-many")
def normalize_many(req: NormalizeManyRequest):
    """Normalize a batch of skill expressions."""
    return [result.to_dict() for result in _normalizer.normalize_many(req.texts)]


# Serve the frontend from the `frontend/` folder.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    """Serve the SPA index page for all non-API routes."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"detail": "Frontend not built."}
