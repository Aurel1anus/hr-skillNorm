"""HTTP bridge for exact/alias matching with DeepSeek fallback."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.deepseek_matcher import DeepSeekMatcher
from app.jev_matcher import JevMatcher
from app.matchers import MatcherRegistry
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
_registry = MatcherRegistry([DeepSeekMatcher(_skills), JevMatcher(_skills)])
_default_provider = os.getenv("SKILL_MATCHER_PROVIDER", "deepseek")
_normalizer = SkillNormalizer(_skills, semantic_matcher=_registry.get(_default_provider))


class NormalizeRequest(BaseModel):
    text: str


class NormalizeManyRequest(BaseModel):
    texts: list[str]


class NormalizeDebugRequest(BaseModel):
    text: str
    provider: str


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
    return normalize_text(req.text).to_dict()


@app.post("/api/normalize-many")
def normalize_many(req: NormalizeManyRequest):
    """Normalize a batch of skill expressions."""
    return [normalize_text(text).to_dict() for text in req.texts]


@app.post("/api/normalize/debug")
def normalize_debug(req: NormalizeDebugRequest):
    try:
        return SkillNormalizer(_skills, semantic_matcher=_registry.get(req.provider)).normalize(req.text).to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/normalize/compare")
def normalize_compare(req: NormalizeRequest):
    exact = SkillNormalizer(_skills).normalize(req.text)
    if exact.match_type == "exact":
        return {"alias_match": exact.to_dict(), "deepseek": None, "jev": None}
    results = {}
    for provider in ("deepseek", "jev"):
        try:
            results[provider] = _registry.get(provider).match(req.text).to_dict()
        except RuntimeError as exc:
            results[provider] = {"error": str(exc), "provider": provider}
    return {"alias_match": None, **results}


def normalize_text(text: str):
    try:
        return _normalizer.normalize(text)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# Serve the frontend from the `frontend/` folder.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    """Serve the SPA index page for all non-API routes."""
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"detail": "Frontend not built."}
