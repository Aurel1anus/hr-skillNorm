"""Thin HTTP bridge for the Skill Normalizer.

This file does not modify any existing backend code. It only imports the
existing `SkillNormalizer` and `load_skills` helpers and exposes them over
HTTP so that `frontend/` can be used interactively.

Semantic matching is intentionally left unconfigured (same as the CLI) so
that the project can still decide on the model/runtime strategy later.
Exact matches and the threshold/review decision logic work out of the box.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
_normalizer = SkillNormalizer(_skills)


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
            "category": skill.category,
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
