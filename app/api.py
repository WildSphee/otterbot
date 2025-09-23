# api.py
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from db.sqlite_db import DB

load_dotenv()
app = FastAPI(title="OtterBot Files API")

# CORS (adjust as desired)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DB()
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
GAMES_DIR = os.path.join(STORAGE_DIR, "games")
os.makedirs(GAMES_DIR, exist_ok=True)

# Serve files under /files/{slug}/<filename>
# We mount /files to STORAGE_DIR/games, so each game folder is /files/<slug>/
app.mount("/files", StaticFiles(directory=GAMES_DIR), name="files")


class GameOut(BaseModel):
    name: str
    slug: str
    status: Optional[str]
    store_dir: str
    last_researched_at: Optional[str]


class GameFileOut(BaseModel):
    title: Optional[str]
    url: Optional[str]
    local_filename: Optional[str]
    link: str  # absolute link to download/view
    source_type: str


@app.get("/games", response_model=List[GameOut])
def list_games():
    games = db.list_games()
    return [
        GameOut(
            name=g["name"],
            slug=g["slug"],
            status=g["status"],
            store_dir=g["store_dir"],
            last_researched_at=g["last_researched_at"],
        )
        for g in games
    ]


@app.get("/games/{slug}", response_model=GameOut)
def get_game(slug: str):
    g = db.get_game_by_slug(slug)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    return GameOut(
        name=g["name"],
        slug=g["slug"],
        status=g["status"],
        store_dir=g["store_dir"],
        last_researched_at=g["last_researched_at"],
    )


@app.get("/games/{slug}/files", response_model=List[GameFileOut])
def list_game_files(slug: str):
    g = db.get_game_by_slug(slug)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")

    rows = db.list_sources_for_game_slug(slug)
    out: List[GameFileOut] = []
    for r in rows:
        local_filename = None
        link = r["url"] or ""
        if r.get("local_path"):
            fname = os.path.basename(r["local_path"])
            local_filename = fname
            link = f"/files/{slug}/{fname}"

        out.append(
            GameFileOut(
                title=r.get("title"),
                url=r.get("url"),
                local_filename=local_filename,
                link=link,
                source_type=r.get("source_type", "other"),
            )
        )
    return out
