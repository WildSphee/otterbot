import logging
import os
import pathlib
import re
import urllib.parse
from difflib import get_close_matches
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from datasources.faiss_ds import FAISSDS
from datasources.ingest import ingest_game_sources
from db.sqlite_db import DB
from dotenv import load_dotenv
from llms import openai as llm
from llms.prompt import (
    EXTRACT_GAME_NAME_PROMPT,
    INTENT_CLASSIFICATION_PROMPT,
)
from schemas import Game, GameNameExtraction, UserIntent
from youtube_transcript_api import YouTubeTranscriptApi

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
        r = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
        )
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


def extract_youtube_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from URL."""
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def validate_youtube_url(video_url: str) -> bool:
    """
    Validate if a YouTube video exists and is accessible.
    Returns True if video is valid, False otherwise.
    """
    try:
        video_id = extract_youtube_id(video_url)
        if not video_id:
            logger.warning(
                f"[YouTube Validation] Invalid YouTube URL format: {video_url}"
            )
            return False

        logger.info(f"[YouTube Validation] Checking if video exists: {video_id}")

        # Try to fetch video info using a HEAD request to the embed URL
        # This is lightweight and doesn't require API keys
        embed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"

        response = requests.get(embed_url, timeout=10)

        if response.status_code == 200:
            logger.info(f"[YouTube Validation] ✓ Video exists: {video_id}")
            return True
        else:
            logger.warning(
                f"[YouTube Validation] ✗ Video not found or unavailable: {video_id} (status: {response.status_code})"
            )
            return False

    except requests.RequestException as e:
        logger.error(f"[YouTube Validation] Error validating video: {e}")
        return False
    except Exception as e:
        logger.error(f"[YouTube Validation] Unexpected error: {e}")
        return False


def get_youtube_captions(video_id: str) -> Optional[str]:
    """Fetch YouTube video captions/transcript."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        captions = " ".join([entry["text"] for entry in transcript_list])
        return captions
    except Exception as e:
        logger.warning(f"Could not fetch captions for YouTube video {video_id}: {e}")
        return None


def bgg_canonical_url(game_name: str) -> Optional[str]:
    """Get BoardGameGeek URL using XML API search."""
    try:
        logger.info(f"[BGG] Searching for game: '{game_name}'")

        # BGG now requires authentication for XML API (as of late 2024)
        # Try without auth first, then fall back to Google if 401
        headers = {"User-Agent": USER_AGENT}

        # Try with exact=1 first for better matching
        params = {"query": game_name, "type": "boardgame", "exact": 1}

        s = requests.get(
            "https://boardgamegeek.com/xmlapi2/search",
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        logger.info(f"[BGG] API response status: {s.status_code}")

        # If 401, BGG requires authentication now - skip XML API
        if s.status_code == 401:
            logger.warning(
                "[BGG] API returned 401 (authentication required) - BGG now requires API token"
            )
            logger.info("[BGG] Falling back to Google search (more reliable)")
            return None

        if s.status_code != 200:
            logger.warning(f"[BGG] API returned non-200 status: {s.status_code}")
            return None

        if "<items" not in s.text:
            logger.warning(
                f"[BGG] No items in response. Response preview: {s.text[:200]}"
            )
            return None

        soup = BeautifulSoup(s.text, "xml")
        items = soup.find_all("item")

        if not items:
            logger.warning(f"[BGG] No game items found for '{game_name}'")
            return None

        logger.info(f"[BGG] Found {len(items)} results:")
        for idx, item in enumerate(items[:5]):  # Log first 5 results
            item_id = item.get("id")
            item_name = item.find("name")
            name_text = item_name.get("value") if item_name else "Unknown"
            logger.info(f"[BGG]   Result {idx + 1}: ID={item_id}, Name='{name_text}'")

        # Use first result
        first_item = items[0]
        game_id = first_item.get("id")
        game_title = first_item.find("name")
        title_text = game_title.get("value") if game_title else "Unknown"

        url = f"https://boardgamegeek.com/boardgame/{game_id}"
        logger.info(f"[BGG] ✓ Selected: '{title_text}' (ID: {game_id})")
        logger.info(f"[BGG] ✓ URL: {url}")
        return url

    except requests.RequestException as e:
        logger.error(f"[BGG] Request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"[BGG] Unexpected error: {e}")
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


def classify_user_intent(user_text: str, available_games: List[str]) -> UserIntent:
    """
    Use OpenAI structured outputs to classify user intent.
    Returns intent type and extracted game name if applicable.
    """
    from openai import OpenAI

    client = OpenAI()
    games_list = ", ".join(available_games) if available_games else "None"

    intent_prompt = INTENT_CLASSIFICATION_PROMPT.format(
        games_list=games_list, user_text=user_text
    )

    try:
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": intent_prompt}],
            response_format=UserIntent,
        )
        intent = response.choices[0].message.parsed
        logger.info(
            f"Intent classified: {intent.intent_type} (game: {intent.game_name}, confidence: {intent.confidence})"
        )
        return intent
    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        # Fallback to general_chat
        return UserIntent(
            intent_type="general_chat",
            game_name=None,
            confidence="low",
            reasoning="Classification failed, defaulting to general chat",
        )


def extract_game_name(user_text: str, available_games: List[str]) -> Optional[str]:
    """
    Use OpenAI structured output to extract game name from user text.
    Then fuzzy match against available games.
    """
    # Build context with available games
    games_list = ", ".join(available_games) if available_games else "none"

    try:
        response = llm.client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": EXTRACT_GAME_NAME_PROMPT.format(
                        games_list=games_list, user_text=user_text
                    ),
                }
            ],
            response_format=GameNameExtraction,
        )
        extraction = response.choices[0].message.parsed

        if not extraction or not extraction.game_name:
            return None

        # Fuzzy match against available games
        matches = get_close_matches(
            extraction.game_name, available_games, n=1, cutoff=0.6
        )
        if matches:
            logger.info(
                f"Extracted game: {extraction.game_name} -> Matched: {matches[0]}"
            )
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
        """Download if HTML/PDF/YouTube; otherwise record as a link. Returns (downloaded, linked) increments."""
        base_dir = game.store_dir

        # Check if it's a YouTube video
        video_id = extract_youtube_id(url)
        if video_id:
            captions = get_youtube_captions(video_id)
            if captions:
                # Save captions as text file
                filename = f"youtube_{video_id}.txt"
                path = os.path.join(base_dir, filename)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"YouTube Video: {title}\nURL: {url}\n\n{captions}")
                db.add_game_source(
                    game_id=game.id,
                    source_type="video",
                    url=url,
                    title=title,
                    local_path=path,
                )
                return (1, 0)
            else:
                # No captions available, save as link
                db.add_game_source(
                    game_id=game.id,
                    source_type="video",
                    url=url,
                    title=title,
                    local_path=None,
                )
                return (0, 1)

        r = http_get(url)
        if r is None:
            db.add_game_source(
                game_id=game.id,
                source_type="link",
                url=url,
                title=title,
                local_path=None,
            )
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
            db.add_game_source(
                game_id=game.id,
                source_type="pdf",
                url=url,
                title=title,
                local_path=path,
            )
            return (1, 0)

        # HTML (+ .txt extraction)
        html_name = (
            urllib.parse.quote(os.path.basename(urllib.parse.urlparse(url).path))
            or "page.html"
        )
        if not html_name.endswith(".html"):
            html_name += ".html"
        html_path = os.path.join(base_dir, html_name)
        with open(html_path, "wb") as f:
            f.write(r.content)
        txt = html_to_text(r.text)
        with open(html_path.replace(".html", ".txt"), "w", encoding="utf-8") as f:
            f.write(txt)
        db.add_game_source(
            game_id=game.id,
            source_type="html",
            url=url,
            title=title,
            local_path=html_path,
        )
        return (1, 0)

    def research(self, game_name: str) -> str:
        logger.info(f"[RESEARCH] Starting research for: '{game_name}'")
        game = get_or_create_game(game_name)
        logger.info(f"[RESEARCH] Game ID: {game.id}, Status: {game.status}")

        if game.status in {"ready", "researched"}:
            logger.info("[RESEARCH] Game already researched, skipping")
            return f"I already have research on <b>{game.name}</b>. How can I help? 🦦"

        db.update_game_status(game.id, "researching")
        logger.info("[RESEARCH] Updated status to 'researching'")

        # 1) First get deterministic BGG URL using XML API (prevents hallucination)
        logger.info("[RESEARCH] Step 1: Getting BGG URL via XML API...")
        bgg_url = bgg_canonical_url(game.name)
        logger.info(f"[RESEARCH] BGG URL result: {bgg_url or 'Not found'}")

        # If BGG XML API fails, try Google search as fallback
        if not bgg_url:
            logger.info(
                "[RESEARCH] BGG XML API failed, trying Google search fallback..."
            )
            bgg_url = llm.google_search_bgg_url(game.name)
            logger.info(f"[RESEARCH] Google BGG result: {bgg_url or 'Not found'}")

        # 2) Ask OpenAI Web Search to gather sources, BGG metadata, and YouTube tutorial in parallel
        logger.info(
            "[RESEARCH] Step 2: Starting parallel fetch (sources, BGG metadata, YouTube)..."
        )
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            sources_future = executor.submit(llm.web_research_links, game.name)
            # Pass the deterministic BGG URL to prevent hallucination
            bgg_future = executor.submit(llm.fetch_bgg_metadata, game.name, bgg_url)
            youtube_future = executor.submit(llm.find_youtube_tutorial, game.name)

            sources = sources_future.result()
            bgg_data = bgg_future.result()
            youtube_data = youtube_future.result()

        logger.info("[RESEARCH] Parallel fetch complete:")
        logger.info(f"[RESEARCH]   - Web sources found: {len(sources)}")
        logger.info(f"[RESEARCH]   - BGG data: {bgg_data}")
        logger.info(f"[RESEARCH]   - YouTube data: {youtube_data}")

        # If YouTube search failed, try Google search fallback
        if not youtube_data.get("video_url"):
            logger.info("[RESEARCH] YouTube search failed, trying Google fallback...")
            youtube_data = llm.google_search_youtube(game.name)
            logger.info(f"[RESEARCH] Google YouTube result: {youtube_data}")

        # Validate YouTube URL if we have one
        if youtube_data.get("video_url"):
            logger.info("[RESEARCH] Validating YouTube URL...")
            is_valid = validate_youtube_url(youtube_data["video_url"])
            if not is_valid:
                logger.warning("[RESEARCH] YouTube URL is invalid/broken, removing it")
                youtube_data = {
                    "video_url": None,
                    "video_title": None,
                    "channel_name": None,
                }

        # 3) Always also consider deterministic seeds as a fallback
        seeds: List[Tuple[str, str]] = []
        wiki_slug = game.name.strip().replace(" ", "_")
        seeds.append(
            (
                f"{game.name} (Wikipedia)",
                f"https://en.wikipedia.org/wiki/{urllib.parse.quote(wiki_slug)}",
            )
        )
        if bgg_url:
            seeds.append((f"{game.name} (BoardGameGeek)", bgg_url))

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
            n_downloaded, n_linked = self._save_source(game, title, url)
            downloaded += n_downloaded
            linked += n_linked

        # Create FAISS index from downloaded sources
        try:
            index_name = ingest_game_sources(game.id)
            logger.info(f"Created FAISS index: {index_name}")
        except Exception as e:
            logger.error(f"Failed to create FAISS index for game {game.id}: {e}")
            # Don't fail the whole research, just log the error

        # Generate game description from sources
        try:
            # Collect first chunk of text from sources for description generation
            sources_data = db.list_sources_for_game(game.id)
            summary_parts = []
            for source in sources_data[:5]:  # Use first 5 sources
                local_path = source.get("local_path")
                if local_path:
                    try:
                        # For HTML sources, check for .txt companion file
                        if local_path.endswith(".html"):
                            txt_path = local_path.replace(".html", ".txt")
                            if os.path.exists(txt_path):
                                with open(txt_path, "r", encoding="utf-8") as f:
                                    content = f.read()[:1000]  # First 1000 chars
                                    summary_parts.append(
                                        f"Source: {source.get('title', 'Unknown')}\n{content}"
                                    )
                        # For direct .txt files (YouTube captions, etc.)
                        elif local_path.endswith(".txt"):
                            with open(local_path, "r", encoding="utf-8") as f:
                                content = f.read()[:1000]  # First 1000 chars
                                summary_parts.append(
                                    f"Source: {source.get('title', 'Unknown')}\n{content}"
                                )
                    except Exception as e:
                        logger.warning(f"Failed to read source {local_path}: {e}")

            if summary_parts:
                sources_summary = "\n\n".join(summary_parts)
                description = llm.generate_game_description(game.name, sources_summary)
                db.update_game_description(game.id, description)
                logger.info(
                    f"Generated description for {game.name}: {description[:100]}..."
                )
            else:
                logger.warning(
                    f"No text content available to generate description for {game.name}"
                )
        except Exception as e:
            logger.error(f"Failed to generate description for game {game.id}: {e}")

        # Save BGG and YouTube metadata
        db.update_game_metadata(
            game.id,
            difficulty_score=bgg_data.get("difficulty_score"),
            player_count=bgg_data.get("player_count"),
            bgg_url=bgg_data.get("bgg_url"),
            tutorial_video_url=youtube_data.get("video_url"),
        )

        db.update_game_status(game.id, "ready")
        db.update_game_timestamps(game.id)

        # Build response message with metadata
        response_parts = [
            f"I've created a knowledge base for <b>{game.name}</b> "
            f"with {downloaded} saved files and {linked} links."
        ]

        # Add game description if available
        game_info = db.get_game_by_id(game.id)
        if game_info and game_info.get("description"):
            response_parts.append(f"\n\n<i>{game_info['description']}</i>")

        # Add metadata if available
        metadata_parts = []
        if bgg_data.get("difficulty_score"):
            difficulty = bgg_data["difficulty_score"]
            metadata_parts.append(f"Difficulty: {difficulty}/5.0")
        if bgg_data.get("player_count"):
            metadata_parts.append(f"Players: {bgg_data['player_count']}")

        if metadata_parts:
            response_parts.append("\n" + " • ".join(metadata_parts))

        # Add YouTube tutorial link if available
        if youtube_data.get("video_url"):
            video_title = youtube_data.get("video_title", "Tutorial Video")
            channel = youtube_data.get("channel_name", "")
            channel_text = f" by {channel}" if channel else ""
            response_parts.append(
                f'\n📺 <a href="{youtube_data["video_url"]}">{video_title}</a>{channel_text}'
            )

        # Add BGG link if available
        if bgg_data.get("bgg_url"):
            response_parts.append(
                f'\n🎲 <a href="{bgg_data["bgg_url"]}">View on BoardGameGeek</a>'
            )

        response_parts.append(
            f"\n\nTap the button below to browse files, or ask me anything about {game.name}! 🦦"
        )

        return "".join(response_parts)


class GamesListTool:
    def list_available_games(self) -> str:
        """List all available games with descriptions and recommendations."""
        games = db.list_games()

        if not games:
            return "I don't have any games in my library yet! Ask me to research a game with 'otter research [game name]'. 🦦"

        # Separate games by status
        ready_games = [g for g in games if g["status"] == "ready"]
        other_games = [g for g in games if g["status"] != "ready"]

        response_parts = ["<b>📚 My Board Game Library:</b>"]

        if ready_games:
            response_parts.append(
                "\nTap the buttons below to browse files, or ask me anything about these games! 🦦"
            )
            # for game in ready_games:
            #     name = game["name"]
            #     desc = game.get("description") or "No description available yet."
            #     response_parts.append(f"\n• <b>{name}</b>\n  {desc}")

        if other_games:
            response_parts.append(f"\n\n<b>⏳ In progress ({len(other_games)}):</b>")
            # for game in other_games[:5]:  # Show first 5
            #     name = game["name"]
            #     status = game["status"]
            #     response_parts.append(f"• {name} ({status})")

        return "\n".join(response_parts)


class QueryTool:
    def _search_faiss(
        self, game_id: int, query: str, top_k: int = 5
    ) -> Tuple[str, List[Tuple[str, str]]]:
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

                context_parts.append(
                    f"[Source: {search_key} (score: {score:.2f})]\n{content}"
                )
                citations.append((search_key, file_url))

            return "\n\n".join(context_parts), citations
        except Exception as e:
            logger.error(f"FAISS search failed for game {game_id}: {e}")
            return "", []

    def answer(
        self, chat_id: int, user_text: str, explicit_game: Optional[str] = None
    ) -> str:
        """
        Answer user question using:
        1. Structured output to extract game name
        2. Fuzzy matching against available games
        3. FAISS vector search for internal context
        4. Web search for additional/missing information
        5. LLM to generate answer with both sources
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

        # Try to get game from DB for internal context
        game_data = db.get_game_by_name(game_name)
        context_text = ""
        citations = []
        has_researched_game = False

        if game_data and game_data["status"] == "ready":
            # We have internal sources - search them
            game = Game(**game_data)
            context_text, citations = self._search_faiss(game.id, user_text, top_k=5)
            has_researched_game = True

        # Use web search to supplement or provide answer
        # This gives us fresh, comprehensive answers even if we have limited internal data
        answer = llm.web_search_answer(
            game_name=game_name,
            question=user_text,
            context=context_text[:10000] if context_text else "",
        )

        # Add internal citations if we have them
        if citations and game_data:
            uniq, seen = [], set()
            for title, link in citations[:5]:
                if (title, link) not in seen:
                    uniq.append((title, link))
                    seen.add((title, link))

            # Format sources with HTML links (now using original URLs)
            sources_html = "\n".join(
                f'• <a href="{link}">{text}</a>' for text, link in uniq
            )

            # Add link to view all files for this game
            game = Game(**game_data)
            all_files_link = f"{API_BASE_URL}/games/{game.id}/files"

            # Append internal sources section
            if not answer.strip().endswith("🦦"):
                answer = answer.strip()
            answer = f'{answer}\n\n<b>Internal Sources:</b>\n{sources_html}\n\n<a href="{all_files_link}">📂 View all files for {game.name}</a>'
        elif not has_researched_game:
            # Add disclaimer if game hasn't been researched yet
            if not answer.strip().endswith("🦦"):
                answer = answer.strip()
            answer = f'{answer}\n\n<i>Note: I haven\'t done thorough research on <b>{game_name}</b> yet. For more accurate and comprehensive results, you can say "otter research {game_name}".</i>'

        if not answer.strip().endswith("🦦"):
            answer = answer.strip() + " 🦦"

        return answer
