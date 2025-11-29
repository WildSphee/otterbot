"""
FastAPI server for serving game files with a beautiful web interface.
"""

import os
import sys
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot.db import db  # noqa: E402

load_dotenv()
app = FastAPI(title="OtterBot Files API")

# CORS - Allow your domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
GAMES_DIR = os.path.join(STORAGE_DIR, "games")
os.makedirs(GAMES_DIR, exist_ok=True)

# Mount static directories
app.mount("/files", StaticFiles(directory=GAMES_DIR), name="files")
app.mount("/assets", StaticFiles(directory="assets"), name="assets")
app.mount("/static", StaticFiles(directory="api/static"), name="static")


class GameOut(BaseModel):
    id: int
    name: str
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
            id=g["id"],
            name=g["name"],
            status=g["status"],
            store_dir=g["store_dir"],
            last_researched_at=g["last_researched_at"],
        )
        for g in games
    ]


@app.get("/games/{game_id}", response_model=GameOut)
def get_game(game_id: int):
    g = db.get_game_by_id(game_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")
    return GameOut(
        id=g["id"],
        name=g["name"],
        status=g["status"],
        store_dir=g["store_dir"],
        last_researched_at=g["last_researched_at"],
    )


@app.get("/games/{game_id}/files")
def list_game_files(game_id: int, format: Optional[str] = None):
    g = db.get_game_by_id(game_id)
    if not g:
        raise HTTPException(status_code=404, detail="Game not found")

    rows = db.list_sources_for_game(game_id)
    out: List[GameFileOut] = []
    for r in rows:
        local_filename = None
        link = r["url"] or ""
        if r.get("local_path"):
            fname = os.path.basename(r["local_path"])
            local_filename = fname
            link = f"/files/{game_id}/{fname}"

        out.append(
            GameFileOut(
                title=r.get("title"),
                url=r.get("url"),
                local_filename=local_filename,
                link=link,
                source_type=r.get("source_type", "other"),
            )
        )

    # Return JSON if explicitly requested
    if format == "json":
        return out

    # Otherwise return HTML
    from api.render import render_game_files_html

    return HTMLResponse(content=render_game_files_html(g, out), status_code=200)
