import os
from typing import List, Optional

from db.sqlite_db import DB
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()
app = FastAPI(title="OtterBot Files API")

# CORS - Allow your domain
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://otterbot.space,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = DB()
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
GAMES_DIR = os.path.join(STORAGE_DIR, "games")
os.makedirs(GAMES_DIR, exist_ok=True)

# Serve files under /files/{game_id}/<filename>
# We mount /files to STORAGE_DIR/games, so each game folder is /files/<game_id>/
app.mount("/files", StaticFiles(directory=GAMES_DIR), name="files")


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


@app.get("/games/{game_id}/files", response_model=List[GameFileOut])
def list_game_files(game_id: int):
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
    return out
