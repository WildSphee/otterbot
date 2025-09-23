import os
import re
import json
import time
import hashlib
import logging
import pathlib
import urllib.parse
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from dotenv import load_dotenv

from db.sqlite_db import DB
from schemas import Game, GameSource
from llms import openai as llm

load_dotenv()
logger = logging.getLogger(__name__)

# --------- Config ---------
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
GAMES_DIR = os.path.join(STORAGE_DIR, "games")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "OtterBot/1.0 (+https://example.com; board-game-rules-crawler)",
)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))

os.makedirs(GAMES_DIR, exist_ok=True)


# --------- Utilities ---------
def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    return s or "game"


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def save_text(path: str, text: str) -> None:
    pathlib.Path(os.path.dirname(path)).mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def sanitize_filename(url_or_name: str) -> str:
    name = urllib.parse.urlparse(url_or_name).path.split("/")[-1] or url_or_name
    name = re.sub(r"[^\w\.-]", "_", name)
    return name[:200] if len(name) > 200 else name


def http_get(url: str) -> Optional[requests.Response]:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r
        logger.warning("GET %s -> %s", url, r.status_code)
        return None
    except requests.RequestException as e:
        logger.warning("GET %s failed: %s", url, e)
        return None


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    # Collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --------- Very light “search” helpers (DuckDuckGo HTML) ---------
def ddg_search_urls(query: str, max_results: int = 6) -> List[Tuple[str, str]]:
    """
    Return list of (title, url) for a simple DuckDuckGo HTML search.
    NOTE: This uses public HTML. If it stops working, replace with your preferred method.
    """
    params = {"q": query}
    url = "https://duckduckgo.com/html/"
    try:
        r = requests.post(url, data=params, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            logger.warning("DDG search failed %s -> %s", url, r.status_code)
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for a in soup.select(".result__a")[:max_results]:
            title = a.get_text(strip=True)
            href = a.get("href")
            # DDG uses redirect links; try to resolve 'uddg' param
            if href and "uddg=" in href:
                try:
                    href = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [href])[0]
                except Exception:
                    pass
            if href:
                out.append((title, href))
        return out
    except requests.RequestException as e:
        logger.warning("DDG request failed: %s", e)
        return []


# --------- DB helpers (thin wrappers) ---------
db = DB()


def get_or_create_game(game_name: str) -> Game:
    slug = slugify(game_name)
    existing = db.get_game_by_slug(slug)
    if existing:
        return Game(**existing)
    store_dir = os.path.join(GAMES_DIR, slug)
    pathlib.Path(store_dir).mkdir(parents=True, exist_ok=True)
    db.create_game(name=game_name, slug=slug, store_dir=store_dir, status="created")
    return Game(**db.get_game_by_slug(slug))


def add_source(game_id: int, source_type: str, url: str, title: str, local_path: Optional[str]) -> None:
    db.add_game_source(game_id=game_id, source_type=source_type, url=url, title=title, local_path=local_path)


def list_source_files(game_slug: str) -> List[GameSource]:
    rows = db.list_sources_for_game_slug(game_slug)
    return [GameSource(**r) for r in rows]


# --------- LLM Prompt for QA ---------
QA_SYSTEM_PROMPT = """You are OtterBot, a helpful board game rules assistant.
- Answer questions about the specified board game using provided documents.
- Be concise, enumerate steps or rules clearly.
- If unsure or documents lack the answer, say so and suggest exact rule sections to check.
- When you use a specific document, include a short citation like: [see: {title}] and provide a file link if available."""

# --------- Tools ---------
class ResearchTool:
    """
    Researches a board game:
    - Checks DB; if exists -> returns 'already have'.
    - Otherwise:
        * Creates game record & folder
        * Collects sources (PDFs, HTML rule pages, video links)
        * Stores files + metadata in DB
        * Marks game ready
    """

    def research(self, game_name: str) -> str:
        game = get_or_create_game(game_name)
        if game.status in {"ready", "researched"}:
            return f"I already have research on **{game.name}**. How can I help?"

        db.update_game_status(game.slug, "researching")

        # Seed URLs heuristics
        seeds: List[Tuple[str, str]] = []

        # 1) Wikipedia page
        wiki_slug = game.name.strip().replace(" ", "_")
        seeds.append((f"{game.name} (Wikipedia)", f"https://en.wikipedia.org/wiki/{urllib.parse.quote(wiki_slug)}"))

        # 2) Try to find rulebook PDFs / rules pages via DuckDuckGo
        q_pdf = f'"{game.name}" board game rules filetype:pdf'
        q_rules = f'"{game.name}" board game rules'
        q_video = f'"{game.name}" board game rules site:youtube.com'

        for title, url in ddg_search_urls(q_pdf, 6):
            seeds.append((title, url))
        for title, url in ddg_search_urls(q_rules, 6):
            seeds.append((title, url))
        for title, url in ddg_search_urls(q_video, 6):
            seeds.append((title, url))

        # Deduplicate by URL
        seen = set()
        uniq_seeds: List[Tuple[str, str]] = []
        for title, url in seeds:
            if url not in seen:
                uniq_seeds.append((title, url))
                seen.add(url)

        downloaded = 0
        saved_links = 0

        for title, url in uniq_seeds:
            r = http_get(url)
            if r is None:
                # Save as link only (e.g., if site blocks scraping)
                add_source(game.id, "link", url, title, None)
                saved_links += 1
                continue

            content_type = (r.headers.get("Content-Type") or "").lower()

            # Decide how to store
            base_dir = db.get_game_by_slug(game.slug)["store_dir"]
            if "application/pdf" in content_type or url.lower().endswith(".pdf"):
                fname = sanitize_filename(url)
                if not fname.endswith(".pdf"):
                    fname += ".pdf"
                path = os.path.join(base_dir, fname)
                pathlib.Path(base_dir).mkdir(parents=True, exist_ok=True)
                with open(path, "wb") as f:
                    f.write(r.content)
                add_source(game.id, "pdf", url, title, path)
                downloaded += 1
                continue

            if "text/html" in content_type or True:
                # Save HTML and extracted text
                html_name = sanitize_filename(url)
                if not html_name.endswith(".html"):
                    html_name += ".html"
                html_path = os.path.join(base_dir, html_name)
                pathlib.Path(base_dir).mkdir(parents=True, exist_ok=True)
                with open(html_path, "wb") as f:
                    f.write(r.content)

                txt = html_to_text(r.text)
                txt_path = html_path.replace(".html", ".txt")
                save_text(txt_path, txt)
                add_source(game.id, "html", url, title, html_path)
                downloaded += 1
                continue

        db.update_game_status(game.slug, "ready")
        db.update_game_timestamps(game.slug)

        link = f"{API_BASE_URL}/games/{game.slug}/files"
        return (
            f"I've created a knowledge base for **{game.name}** "
            f"with {downloaded} saved files and {saved_links} links. "
            f"You can browse them here: {link}\n"
            f"Ask me anything about {game.name}!"
        )


class QueryTool:
    """
    Answers a rules question by:
    - Determining the game (explicit or inferred from chat history & installed games)
    - Gathering local documents (txt extracted from html/pdf) for context
    - Calling the LLM with those snippets
    """

    def _detect_game_from_text(self, text: str) -> Optional[str]:
        games = db.list_games()
        # Match longest name first
        names = sorted([g["name"] for g in games], key=len, reverse=True)
        for name in names:
            pattern = r"\b" + re.escape(name) + r"\b"
            if re.search(pattern, text, flags=re.IGNORECASE):
                return name
        return None

    def _infer_game_for_chat(self, chat_id: int) -> Optional[str]:
        recent = db.find_recent_game_for_chat(chat_id)
        if recent:
            return recent["name"]
        return None

    def _gather_text_snippets(self, game_slug: str, max_chars: int = 20000) -> Tuple[str, List[Tuple[str, str]]]:
        """
        Returns (context_text, citations)
        citations: list of (title, link)
        """
        sources = db.list_sources_for_game_slug(game_slug)
        base_url = f"{API_BASE_URL}/games/{game_slug}/files"
        ctx_parts: List[str] = []
        citations: List[Tuple[str, str]] = []

        for src in sources:
            title = src["title"] or src["url"]
            link_out = base_url  # list page; specific file links are also available
            if src.get("local_path"):
                # For a specific file link
                fname = os.path.basename(src["local_path"])
                link_out = f"{API_BASE_URL}/files/{game_slug}/{urllib.parse.quote(fname)}"

            # Prefer reading .txt versions for html pages we saved
            snippet = ""
            if src.get("local_path"):
                local_path = src["local_path"]
                alt_txt = None
                if local_path.endswith(".html"):
                    alt_txt = local_path.replace(".html", ".txt")
                elif local_path.endswith(".pdf"):
                    # naive: we don't extract PDF text by default here; you can add pypdf2 if desired
                    alt_txt = None

                try:
                    if alt_txt and os.path.exists(alt_txt):
                        with open(alt_txt, "r", encoding="utf-8", errors="ignore") as f:
                            snippet = f.read()
                    elif os.path.exists(local_path) and local_path.endswith(".txt"):
                        with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
                            snippet = f.read()
                except Exception as e:
                    logger.warning("Failed reading snippet from %s: %s", local_path, e)

            if snippet:
                citations.append((title, link_out))
                ctx_parts.append(f"[Source: {title}]")
                ctx_parts.append(snippet)

            if sum(len(p) for p in ctx_parts) > max_chars:
                break

        context_text = "\n\n".join(ctx_parts)
        return context_text, citations

    def answer(self, chat_id: int, user_text: str, explicit_game: Optional[str] = None) -> str:
        # 1) Determine game
        game_name = explicit_game or self._detect_game_from_text(user_text) or self._infer_game_for_chat(chat_id)
        if not game_name:
            # No inference possible; suggest research or clarify
            if db.list_games():
                known = ", ".join(sorted(set(g["name"] for g in db.list_games())))
                return (
                    "I’m not sure which game you mean. "
                    f"Games I currently have: {known}. "
                    "Say e.g. “yo otter, rules for Catan setup?” "
                    "Or ask me to research a new game: “hey otter, research Azul”."
                )
            else:
                return (
                    "I don’t have any games installed yet. "
                    "Ask me to research one: “hi otter, research Catan”."
                )

        # Ensure this game exists and is ready
        game = get_or_create_game(game_name)
        if game.status != "ready":
            return (
                f"**{game.name}** isn’t ready yet (status: {game.status}). "
                f"Try again in a bit, or ask me to continue research."
            )

        # 2) Gather context documents
        context_text, citations = self._gather_text_snippets(game.slug)
        if not context_text:
            link = f"{API_BASE_URL}/games/{game.slug}/files"
            return (
                f"I have **{game.name}** installed but no readable text snippets yet. "
                f"You can browse files here: {link}. "
                "Add text or enable PDF extraction, then try again."
            )

        # 3) Compose LLM messages
        messages = [
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": f"GAME: {game.name}\n\nQUESTION: {user_text}\n\nDOCUMENTS:\n{context_text[:20000]}"},
        ]

        answer = llm.chat(messages=messages)

        # 4) Append simple citations (just list top few)
        if citations:
            uniq = []
            seen = set()
            for title, link in citations[:5]:
                key = (title, link)
                if key not in seen:
                    uniq.append(key)
                    seen.add(key)
            cite_lines = "\n".join(f"- {t}: {l}" for t, l in uniq)
            answer = f"{answer}\n\nSources:\n{cite_lines}"

        return answer
