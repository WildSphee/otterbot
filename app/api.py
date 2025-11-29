import os
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.db import db

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
    return HTMLResponse(content=_render_files_html(g, out), status_code=200)


def _render_files_html(game: dict, files: List[GameFileOut]) -> str:
    """Render a beautiful HTML page for game files."""

    # Group files by type
    pdfs = [f for f in files if f.source_type == "pdf"]
    htmls = [f for f in files if f.source_type == "html"]
    links = [f for f in files if f.source_type == "link"]
    others = [f for f in files if f.source_type not in ["pdf", "html", "link"]]

    def render_file_card(file: GameFileOut) -> str:
        icon = {
            "pdf": "📄",
            "html": "🌐",
            "link": "🔗",
            "txt": "📝",
            "video": "🎥",
            "other": "📎",
        }.get(file.source_type, "📎")

        title = file.title or "Untitled"
        is_local = file.local_filename is not None
        badge = (
            '<span class="badge badge-local">Downloaded</span>'
            if is_local
            else '<span class="badge badge-external">External Link</span>'
        )

        # Show preview for PDFs
        preview = ""
        if file.source_type == "pdf" and is_local:
            preview = f'<div class="preview"><embed src="{file.link}" type="application/pdf" width="100%" height="200px" /></div>'

        return f"""
        <div class="file-card">
            <div class="file-icon">{icon}</div>
            <div class="file-content">
                <h3 class="file-title">{title}</h3>
                {badge}
                {preview}
                <div class="file-actions">
                    <a href="{file.link}" target="_blank" class="btn btn-primary">
                        {"View" if is_local else "Open Link"}
                    </a>
                    {f'<a href="{file.url}" target="_blank" class="btn btn-secondary">Original Source</a>' if file.url else ""}
                </div>
            </div>
        </div>
        """

    def render_section(title: str, files_list: List[GameFileOut]) -> str:
        if not files_list:
            return ""
        cards = "".join(render_file_card(f) for f in files_list)
        return f"""
        <div class="section">
            <h2 class="section-title">{title}</h2>
            <div class="files-grid">
                {cards}
            </div>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{game["name"]} - OtterBot Files</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 2rem;
                color: #333;
            }}

            .container {{
                max-width: 1200px;
                margin: 0 auto;
            }}

            .header {{
                background: white;
                padding: 2rem;
                border-radius: 16px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                margin-bottom: 2rem;
                text-align: center;
            }}

            .header h1 {{
                font-size: 2.5rem;
                color: #667eea;
                margin-bottom: 0.5rem;
            }}

            .header .subtitle {{
                color: #666;
                font-size: 1.1rem;
            }}

            .otter-logo {{
                width: 120px;
                height: 120px;
                margin-bottom: 1rem;
                object-fit: contain;
            }}

            .section {{
                background: white;
                padding: 2rem;
                border-radius: 16px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                margin-bottom: 2rem;
            }}

            .section-title {{
                font-size: 1.8rem;
                color: #667eea;
                margin-bottom: 1.5rem;
                border-bottom: 3px solid #667eea;
                padding-bottom: 0.5rem;
            }}

            .files-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 1.5rem;
            }}

            .file-card {{
                background: #f8f9fa;
                border: 2px solid #e9ecef;
                border-radius: 12px;
                padding: 1.5rem;
                transition: all 0.3s ease;
                display: flex;
                flex-direction: column;
            }}

            .file-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.15);
                border-color: #667eea;
            }}

            .file-icon {{
                font-size: 3rem;
                text-align: center;
                margin-bottom: 1rem;
            }}

            .file-content {{
                flex: 1;
                display: flex;
                flex-direction: column;
            }}

            .file-title {{
                font-size: 1.2rem;
                color: #333;
                margin-bottom: 0.5rem;
                word-wrap: break-word;
            }}

            .badge {{
                display: inline-block;
                padding: 0.25rem 0.75rem;
                border-radius: 20px;
                font-size: 0.85rem;
                font-weight: 600;
                margin-bottom: 1rem;
                width: fit-content;
            }}

            .badge-local {{
                background: #d4edda;
                color: #155724;
            }}

            .badge-external {{
                background: #fff3cd;
                color: #856404;
            }}

            .preview {{
                margin: 1rem 0;
                border-radius: 8px;
                overflow: hidden;
                background: white;
            }}

            .file-actions {{
                display: flex;
                gap: 0.5rem;
                margin-top: auto;
                flex-wrap: wrap;
            }}

            .btn {{
                padding: 0.75rem 1.5rem;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 600;
                transition: all 0.2s ease;
                display: inline-block;
                text-align: center;
                font-size: 0.95rem;
            }}

            .btn-primary {{
                background: #667eea;
                color: white;
            }}

            .btn-primary:hover {{
                background: #5568d3;
                transform: scale(1.05);
            }}

            .btn-secondary {{
                background: #6c757d;
                color: white;
            }}

            .btn-secondary:hover {{
                background: #5a6268;
                transform: scale(1.05);
            }}

            .empty-state {{
                text-align: center;
                padding: 3rem;
                color: #666;
            }}

            .empty-state-icon {{
                font-size: 4rem;
                margin-bottom: 1rem;
            }}

            @media (max-width: 768px) {{
                body {{
                    padding: 1rem;
                }}

                .header h1 {{
                    font-size: 2rem;
                }}

                .files-grid {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img src="/assets/images/otterbotlogo.png" alt="OtterBot Logo" class="otter-logo" />
                <h1>{game["name"]}</h1>
                <p class="subtitle">Game Resources & Documentation</p>
            </div>

            {render_section("📄 PDF Documents", pdfs)}
            {render_section("🌐 Web Pages", htmls)}
            {render_section("🔗 External Links", links)}
            {render_section("📎 Other Files", others)}

            {('<div class="section"><div class="empty-state"><div class="empty-state-icon">🎲</div><p>No files found for this game yet.</p></div></div>' if not files else "")}
        </div>
    </body>
    </html>
    """
    return html
