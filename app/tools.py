import os, re, logging, pathlib, urllib.parse
from typing import List, Optional, Tuple
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from db.sqlite_db import DB
from schemas import Game
from llms import openai as llm
from llms.prompt import QA_SYSTEM_PROMPT

load_dotenv()
logger = logging.getLogger(__name__)

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
GAMES_DIR = os.path.join(STORAGE_DIR, "games")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
USER_AGENT = os.getenv("CRAWLER_USER_AGENT", "OtterBot/1.0 (+https://example.com)")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))

os.makedirs(GAMES_DIR, exist_ok=True)

def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    return s or "game"

def http_get(url: str):
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
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def bgg_canonical_url(game_name: str) -> Optional[str]:
    try:
        s = requests.get(
            "https://boardgamegeek.com/xmlapi2/search",
            params={"query": game_name, "type": "boardgame"},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        if s.status_code != 200 or "<items" not in s.text:
            return None
        soup = BeautifulSoup(s.text, "xml")
        item = soup.find("item")
        if not item or not item.get("id"):
            return None
        game_id = item.get("id")
        return f"https://boardgamegeek.com/boardgame/{game_id}"
    except requests.RequestException:
        return None

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

class ResearchTool:
    def _save_source(self, game: Game, title: str, url: str) -> Tuple[int, int]:
        """Download if HTML/PDF; otherwise record as a link. Returns (downloaded, linked) increments."""
        base_dir = db.get_game_by_slug(game.slug)["store_dir"]
        r = http_get(url)
        if r is None:
            db.add_game_source(game_id=game.id, source_type="link", url=url, title=title, local_path=None)
            return (0, 1)

        ct = (r.headers.get("Content-Type") or "").lower()

        # PDF
        if "application/pdf" in ct or url.lower().endswith(".pdf"):
            fname = urllib.parse.quote(os.path.basename(url)) or "doc.pdf"
            if not fname.endswith(".pdf"):
                fname += ".pdf"
            path = os.path.join(base_dir, fname)
            with open(path, "wb") as f:
                f.write(r.content)
            db.add_game_source(game_id=game.id, source_type="pdf", url=url, title=title, local_path=path)
            return (1, 0)

        # HTML (+ .txt extraction)
        html_name = urllib.parse.quote(os.path.basename(urllib.parse.urlparse(url).path)) or "page.html"
        if not html_name.endswith(".html"):
            html_name += ".html"
        html_path = os.path.join(base_dir, html_name)
        with open(html_path, "wb") as f:
            f.write(r.content)
        txt = html_to_text(r.text)
        with open(html_path.replace(".html", ".txt"), "w", encoding="utf-8") as f:
            f.write(txt)
        db.add_game_source(game_id=game.id, source_type="html", url=url, title=title, local_path=html_path)
        return (1, 0)

    def research(self, game_name: str) -> str:
        game = get_or_create_game(game_name)
        if game.status in {"ready", "researched"}:
            return f"I already have research on **{game.name}**. How can I help? 🦦"

        db.update_game_status(game.slug, "researching")

        # 1) Ask OpenAI Web Search to gather sources
        sources = llm.web_research_links(game.name)

        # 2) Always also consider deterministic seeds as a fallback
        seeds: List[Tuple[str, str]] = []
        wiki_slug = game.name.strip().replace(" ", "_")
        seeds.append((f"{game.name} (Wikipedia)", f"https://en.wikipedia.org/wiki/{urllib.parse.quote(wiki_slug)}"))
        bgg = bgg_canonical_url(game.name)
        if bgg:
            seeds.append((f"{game.name} (BoardGameGeek)", bgg))

        for s in sources:
            seeds.append((s["title"], s["url"]))

        # Dedup
        seen = set()
        uniq: List[Tuple[str, str]] = []
        for title, url in seeds:
            if url not in seen:
                uniq.append((title, url))
                seen.add(url)

        downloaded = 0
        linked = 0
        for title, url in uniq:
            d, l = self._save_source(game, title, url)
            downloaded += d
            linked += l

        db.update_game_status(game.slug, "ready")
        db.update_game_timestamps(game.slug)

        link = f"{API_BASE_URL}/games/{game.slug}/files"
        return (
            f"I've created a knowledge base for **{game.name}** "
            f"with {downloaded} saved files and {linked} links. "
            f"You can browse them here: {link}\n"
            f"Ask me anything about {game.name}! 🦦"
        )

class QueryTool:
    # unchanged logic except we import QA_SYSTEM_PROMPT from llms.prompt
    def _detect_game_from_text(self, text: str) -> Optional[str]:
        games = db.list_games()
        names = sorted([g["name"] for g in games], key=len, reverse=True)
        for name in names:
            if re.search(r"\b" + re.escape(name) + r"\b", text, flags=re.IGNORECASE):
                return name
        return None

    def _infer_game_for_chat(self, chat_id: int) -> Optional[str]:
        recent = db.find_recent_game_for_chat(chat_id)
        if recent:
            return recent["name"]
        return None

    def _gather_text_snippets(self, game_slug: str, max_chars: int = 20000):
        sources = db.list_sources_for_game_slug(game_slug)
        base_url = f"{API_BASE_URL}/games/{game_slug}/files"
        ctx_parts, citations = [], []

        for src in sources:
            title = src["title"] or src["url"]
            link_out = base_url
            if src.get("local_path"):
                fname = os.path.basename(src["local_path"])
                link_out = f"{API_BASE_URL}/files/{game_slug}/{urllib.parse.quote(fname)}"

            snippet = ""
            if src.get("local_path"):
                lp = src["local_path"]
                alt_txt = lp.replace(".html", ".txt") if lp.endswith(".html") else (lp if lp.endswith(".txt") else None)
                try:
                    if alt_txt and os.path.exists(alt_txt):
                        with open(alt_txt, "r", encoding="utf-8", errors="ignore") as f:
                            snippet = f.read()
                except Exception as e:
                    logger.warning("Failed reading snippet from %s: %s", lp, e)

            if snippet:
                citations.append((title, link_out))
                ctx_parts.append(f"[Source: {title}]\n{snippet}")

            if sum(len(p) for p in ctx_parts) > max_chars:
                break

        return "\n\n".join(ctx_parts), citations

    def answer(self, chat_id: int, user_text: str, explicit_game: Optional[str] = None) -> str:
        game_name = explicit_game or self._detect_game_from_text(user_text) or self._infer_game_for_chat(chat_id)
        if not game_name:
            known = ", ".join(sorted(set(g["name"] for g in db.list_games()))) or "none yet"
            return (
                "I'm not sure which game you mean. "
                f"Games I currently have: {known}. "
                "Say e.g. “yo otter, rules for Catan setup?” "
                "Or ask me to research a new game: “hey otter, research Azul”. 🦦"
            )

        game = get_or_create_game(game_name)
        if game.status != "ready":
            return (
                f"**{game.name}** isn’t ready yet (status: {game.status}). "
                f"Try again in a bit, or ask me to continue research. 🦦"
            )

        context_text, citations = self._gather_text_snippets(game.slug)
        if not context_text:
            link = f"{API_BASE_URL}/games/{game.slug}/files"
            return (
                f"I have **{game.name}** installed but no readable text snippets yet. "
                f"Browse files here: {link} and try again. 🦦"
            )

        messages = [
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": f"GAME: {game.name}\n\nQUESTION: {user_text}\n\nDOCUMENTS:\n{context_text[:20000]}"},
        ]
        answer = llm.chat(messages=messages)
        if citations:
            uniq, seen = [], set()
            for title, link in citations[:5]:
                if (title, link) not in seen:
                    uniq.append((title, link)); seen.add((title, link))
            answer = f"{answer}\n\nSources:\n" + "\n".join(f"- {t}: {l}" for t, l in uniq)

        if not answer.strip().endswith("🦦"):
            answer = answer.strip() + " 🦦"
        return answer
