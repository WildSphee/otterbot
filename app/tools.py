import os, re, logging, pathlib, urllib.parse
from typing import List, Optional, Tuple
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from difflib import get_close_matches

from db.sqlite_db import DB
from schemas import Game, GameNameExtraction
from llms import openai as llm
from llms.prompt import QA_SYSTEM_PROMPT
from datasources.faiss_ds import FAISSDS
from datasources.ingest import ingest_game_sources

load_dotenv()
logger = logging.getLogger(__name__)

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
GAMES_DIR = os.path.join(STORAGE_DIR, "games")
DATASOURCES_DIR = os.path.join(STORAGE_DIR, "datasources")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
USER_AGENT = os.getenv("CRAWLER_USER_AGENT", "OtterBot/1.0 (+https://example.com)")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))

os.makedirs(GAMES_DIR, exist_ok=True)
os.makedirs(DATASOURCES_DIR, exist_ok=True)

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
    """Get existing game by name or create new one."""
    existing = db.get_game_by_name(game_name)
    if existing:
        return Game(**existing)

    # Use game ID for directory name (will be created after insert)
    # For now, use a temp placeholder, then update after we get the ID
    game_id = db.create_game(name=game_name, store_dir="temp", status="created")
    store_dir = os.path.join(GAMES_DIR, str(game_id))
    pathlib.Path(store_dir).mkdir(parents=True, exist_ok=True)

    # Update with actual store_dir
    cursor = db.conn.cursor()
    cursor.execute("UPDATE games SET store_dir = ? WHERE id = ?", (store_dir, game_id))
    db.conn.commit()

    game_data = db.get_game_by_id(game_id)
    return Game(**game_data)


def extract_game_name(user_text: str, available_games: List[str]) -> Optional[str]:
    """
    Use OpenAI structured output to extract game name from user text.
    Then fuzzy match against available games.
    """
    # Build context with available games
    games_list = ", ".join(available_games) if available_games else "none"
    prompt = f"""Extract the board game name from the user's message.

Available games in database: {games_list}

User message: {user_text}

If the user is asking about a game, extract its name. If no specific game is mentioned, return null.
Match against available games if possible."""

    try:
        response = llm.client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format=GameNameExtraction,
        )
        extraction = response.choices[0].message.parsed

        if not extraction or not extraction.game_name:
            return None

        # Fuzzy match against available games
        matches = get_close_matches(extraction.game_name, available_games, n=1, cutoff=0.6)
        if matches:
            logger.info(f"Extracted game: {extraction.game_name} -> Matched: {matches[0]}")
            return matches[0]

        # If no match but extraction was confident, return the extracted name
        if extraction.confidence == "high":
            return extraction.game_name

        return None
    except Exception as e:
        logger.error(f"Game name extraction failed: {e}")
        return None

class ResearchTool:
    def _save_source(self, game: Game, title: str, url: str) -> Tuple[int, int]:
        """Download if HTML/PDF; otherwise record as a link. Returns (downloaded, linked) increments."""
        base_dir = game.store_dir
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
            return f"I already have research on <b>{game.name}</b>. How can I help? 🦦"

        db.update_game_status(game.id, "researching")

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

        # Create FAISS index from downloaded sources
        try:
            index_name = ingest_game_sources(game.id)
            logger.info(f"Created FAISS index: {index_name}")
        except Exception as e:
            logger.error(f"Failed to create FAISS index for game {game.id}: {e}")
            # Don't fail the whole research, just log the error

        db.update_game_status(game.id, "ready")
        db.update_game_timestamps(game.id)

        link = f"{API_BASE_URL}/games/{game.id}/files"
        return (
            f"I've created a knowledge base for <b>{game.name}</b> "
            f"with {downloaded} saved files and {linked} links. "
            f"You can browse them <a href=\"{link}\">here</a>\n"
            f"Ask me anything about {game.name}! 🦦"
        )

class QueryTool:
    def _search_faiss(self, game_id: int, query: str, top_k: int = 5) -> Tuple[str, List[Tuple[str, str]]]:
        """
        Search FAISS index for relevant chunks and return context + citations.
        """
        try:
            faiss_ds = FAISSDS(index_name=str(game_id))
            hits = faiss_ds.search_request(search_query=query, topk=top_k)

            context_parts = []
            citations = []
            for hit in hits:
                content = hit.get("content", "")
                search_key = hit.get("search_key", "")
                file_url = hit.get("file_url", "")
                score = hit.get("score", 0)

                context_parts.append(f"[Source: {search_key} (score: {score:.2f})]\n{content}")
                citations.append((search_key, file_url))

            return "\n\n".join(context_parts), citations
        except Exception as e:
            logger.error(f"FAISS search failed for game {game_id}: {e}")
            return "", []

    def answer(self, chat_id: int, user_text: str, explicit_game: Optional[str] = None) -> str:
        """
        Answer user question using:
        1. Structured output to extract game name
        2. Fuzzy matching against available games
        3. FAISS vector search for context
        4. LLM to generate answer
        """
        # Get available games
        games = db.list_games()
        available_game_names = [g["name"] for g in games]

        # Extract game name from user text
        game_name = None
        if explicit_game:
            game_name = explicit_game
        else:
            # Try structured extraction first
            game_name = extract_game_name(user_text, available_game_names)

            # Fallback to recent chat context if extraction failed
            if not game_name:
                recent_game = db.find_recent_game_for_chat(chat_id)
                if recent_game:
                    game_name = recent_game["name"]

        if not game_name:
            known = ", ".join(sorted(set(g["name"] for g in games))) or "none yet"
            return (
                "I'm not sure which game you mean. "
                f"Games I currently have: {known}. "
                "Say e.g. 'yo otter, what are the setup rules for Catan?' "
                "Or ask me to research a new game: 'hey otter, research Azul'. 🦦"
            )

        # Get game from DB
        game_data = db.get_game_by_name(game_name)
        if not game_data:
            return f"I don't have information about <b>{game_name}</b> yet. Ask me to research it first! 🦦"

        game = Game(**game_data)

        if game.status != "ready":
            return (
                f"<b>{game.name}</b> isn't ready yet (status: {game.status}). "
                f"Try again in a bit, or ask me to continue research. 🦦"
            )

        # Search FAISS index for relevant context
        context_text, citations = self._search_faiss(game.id, user_text, top_k=5)

        if not context_text:
            link = f"{API_BASE_URL}/games/{game.id}/files"
            return (
                f"I have <b>{game.name}</b> in my database but couldn't find relevant information. "
                f"Browse files <a href=\"{link}\">here</a> 🦦"
            )

        # Generate answer using LLM
        messages = [
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": f"GAME: {game.name}\n\nQUESTION: {user_text}\n\nDOCUMENTS:\n{context_text[:20000]}"},
        ]
        answer = llm.chat(messages=messages)

        # Add citations with HTML links
        if citations:
            uniq, seen = [], set()
            for title, link in citations[:5]:
                if (title, link) not in seen:
                    uniq.append((title, link))
                    seen.add((title, link))

            # Format sources with HTML links
            sources_html = "\n".join(f"• <a href=\"{l}\">{t}</a>" for t, l in uniq)
            answer = f"{answer}\n\n<b>Sources:</b>\n{sources_html}"

        if not answer.strip().endswith("🦦"):
            answer = answer.strip() + " 🦦"

        return answer
