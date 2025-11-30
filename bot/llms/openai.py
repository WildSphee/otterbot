import json
import re
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from llms.prompt import (
    BGG_METADATA_EXTRACTION_PROMPT,
    GAME_DESCRIPTION_PROMPT,
    WEB_RESEARCH_PROMPT,
    WEB_SEARCH_QA_PROMPT,
)
from openai import OpenAI

load_dotenv()
client = OpenAI()


def chat(messages, model: str = "gpt-4o", tools: Optional[List] = None) -> str:
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools or [],
        temperature=0.2,
    )
    return completion.choices[0].message.content or ""


def call_openai(history, query: str, tools: List = []) -> str:
    messages = history + [{"role": "user", "content": query}]
    return chat(messages=messages, tools=tools)


def generate_game_description(game_name: str, sources_summary: str) -> str:
    """Generate a concise game description from research sources."""
    prompt = GAME_DESCRIPTION_PROMPT.format(
        game_name=game_name, sources_summary=sources_summary[:2000]
    )

    messages = [{"role": "user", "content": prompt}]
    description = chat(messages=messages, model="gpt-4o-mini")
    return description.strip()


# ---------- Responses API helpers ----------


def _extract_json_block(text: str) -> Optional[dict]:
    if not text:
        return None
    m = re.search(r"```json\s*([\s\S]+?)\s*```", text, flags=re.IGNORECASE)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    try:
        return json.loads(text)
    except Exception:
        return None


def web_search_answer(game_name: str, question: str, context: str = "") -> str:
    """
    Answer a game question using web search + internal context.
    Uses Responses API with web_search tool.
    """
    context_section = (
        "Internal knowledge base context:\n" + context
        if context
        else "No internal sources available - search the web for current information."
    )

    prompt = WEB_SEARCH_QA_PROMPT.format(
        game_name=game_name, question=question, context_section=context_section
    )

    try:
        resp = client.responses.create(
            model="gpt-4o",  # Using latest GPT-4o (GPT-5 not yet available)
            input=prompt,
            tools=[{"type": "web_search"}],
            temperature=0.2,
        )

        # Extract answer from response
        content = getattr(resp, "output_text", None)
        if not content:
            chunks = []
            for item in getattr(resp, "output", []) or []:
                if item.get("type") == "message" and "content" in item:
                    for block in item["content"]:
                        if block.get("type") == "output_text" and "text" in block:
                            chunks.append(block["text"])
            content = "\n".join(chunks)

        if content:
            # Strip markdown headers as fallback (in case LLM doesn't follow instructions)
            content = re.sub(
                r"^#{1,6}\s+(.+)$", r"<b>\1</b>", content, flags=re.MULTILINE
            )
            # Remove horizontal rules
            content = re.sub(r"^---+\s*$", "", content, flags=re.MULTILINE)
            content = re.sub(r"^\*\*\*+\s*$", "", content, flags=re.MULTILINE)
            return content.strip()

        return "I couldn't find an answer. Please try rephrasing your question."
    except Exception as e:
        print(f"Web search failed: {e}")
        return "Sorry, I encountered an error while searching for that information. Please try again."


def web_research_links(
    topic: str, model: str = "gpt-4o", max_sources: int = 30
) -> List[Dict[str, Any]]:
    """
    Uses the Responses API with the built-in Web Search tool to return a list of sources.
    Requires an SDK version that includes client.responses.create.
    """
    print(f"Web research for topic: {topic}")

    # IMPORTANT: Use Responses API (NOT chat.completions)
    resp = client.responses.create(
        model=model,
        input=WEB_RESEARCH_PROMPT.replace("{topic}", topic),
        tools=[{"type": "web_search"}],
        temperature=0.1,
    )

    # The Responses API returns output items; pick the text content
    # New SDKs expose .output_text; fall back to concatenating items if needed.
    content = getattr(resp, "output_text", None)
    if not content:
        # Fallback: try to collect text segments
        chunks = []
        for item in getattr(resp, "output", []) or []:
            if item.get("type") == "message" and "content" in item:
                for block in item["content"]:
                    if block.get("type") == "output_text" and "text" in block:
                        chunks.append(block["text"])
        content = "\n".join(chunks)

    data = _extract_json_block(content) or {"topic": topic, "sources": []}
    sources = data.get("sources") or []
    cleaned, seen = [], set()
    for s in sources:
        url = (s.get("url") or "").strip()
        title = (s.get("title") or url).strip()
        stype = (s.get("type") or "other").strip().lower()
        if not url or url in seen:
            continue
        seen.add(url)
        cleaned.append(
            {"title": title, "url": url, "type": stype, "notes": s.get("notes", "")}
        )
        if len(cleaned) >= max_sources:
            break
    return cleaned


def fetch_bgg_metadata(game_name: str, bgg_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch BoardGameGeek metadata by directly accessing the BGG page.
    Returns difficulty_score, player_count, and bgg_url.
    Only returns data if we can successfully fetch the actual BGG page.
    """
    import logging

    import requests
    from bs4 import BeautifulSoup

    logger = logging.getLogger(__name__)

    try:
        logger.info(f"[BGG Metadata] Fetching metadata for: '{game_name}'")
        logger.info(
            f"[BGG Metadata] BGG URL: {bgg_url or 'None - cannot fetch metadata'}"
        )

        # If no BGG URL provided, we can't fetch metadata
        if not bgg_url:
            logger.warning(
                "[BGG Metadata] No BGG URL provided, skipping metadata extraction"
            )
            return {"difficulty_score": None, "player_count": None, "bgg_url": None}

        # Fetch the actual BGG page
        logger.info(f"[BGG Metadata] Fetching page: {bgg_url}")
        headers = {
            "User-Agent": "OtterBot/1.0 (+https://github.com/yourusername/otterbot)"
        }

        response = requests.get(bgg_url, headers=headers, timeout=20)
        logger.info(f"[BGG Metadata] Response status: {response.status_code}")

        # If page not accessible, return nulls and no URL
        if response.status_code != 200:
            logger.warning(
                f"[BGG Metadata] ✗ BGG page not accessible (status {response.status_code}), removing link"
            )
            return {"difficulty_score": None, "player_count": None, "bgg_url": None}

        # Parse the HTML
        html_content = response.text
        logger.info(
            f"[BGG Metadata] Successfully fetched page ({len(html_content)} bytes)"
        )

        # BGG uses a lot of JavaScript - need to extract from structured data or specific elements
        soup = BeautifulSoup(html_content, "html.parser")

        # Try to find JSON-LD structured data first (BGG includes this)
        json_ld_scripts = soup.find_all("script", type="application/ld+json")
        structured_data = ""
        for script in json_ld_scripts:
            if script.string:
                structured_data += script.string + "\n"

        # Also get visible text from specific sections
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()

        # Get text content
        text_content = soup.get_text(separator="\n", strip=True)

        # Combine structured data and text (prioritize structured data)
        combined_content = structured_data + "\n" + text_content
        final_content = combined_content[
            :8000
        ]  # Increase to 8000 chars for better coverage

        logger.info(f"[BGG Metadata] Extracted content ({len(final_content)} chars)")
        logger.info(f"[BGG Metadata] Content preview: {final_content[:500]}...")

        # Use LLM to extract structured data from the ACTUAL BGG page
        extraction_prompt = BGG_METADATA_EXTRACTION_PROMPT.format(
            game_name=game_name, page_content=final_content
        )

        extraction_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": extraction_prompt}],
            temperature=0.1,
        )

        extraction_content = extraction_resp.choices[0].message.content or ""
        logger.info(f"[BGG Metadata] Extraction response: {extraction_content}")

        result = _extract_json_block(extraction_content)
        if result:
            # Always use the provided BGG URL (the one we actually fetched)
            result["bgg_url"] = bgg_url
            logger.info(
                f"[BGG Metadata] ✓ Final result from ACTUAL BGG page: difficulty={result.get('difficulty_score')}, players={result.get('player_count')}, url={bgg_url}"
            )
            return result

        logger.warning("[BGG Metadata] Failed to extract metadata from BGG page")
        # If extraction failed, still return the URL since the page is accessible
        return {"difficulty_score": None, "player_count": None, "bgg_url": bgg_url}

    except requests.Timeout:
        logger.error("[BGG Metadata] ✗ Timeout fetching BGG page, removing link")
        return {"difficulty_score": None, "player_count": None, "bgg_url": None}
    except requests.RequestException as e:
        logger.error(f"[BGG Metadata] ✗ Request error: {e}, removing link")
        return {"difficulty_score": None, "player_count": None, "bgg_url": None}
    except Exception as e:
        logger.error(f"[BGG Metadata] Error: {e}", exc_info=True)
        return {"difficulty_score": None, "player_count": None, "bgg_url": None}


def google_search_bgg_url(game_name: str) -> Optional[str]:
    """
    Use Google search to find the actual BoardGameGeek URL.
    More reliable than web_search tool for finding specific URLs.
    """
    import logging
    import re

    logger = logging.getLogger(__name__)

    try:
        logger.info(f"[Google BGG] Searching Google for: '{game_name}' BoardGameGeek")

        # Use Responses API with web_search to do a Google search
        resp = client.responses.create(
            model="gpt-4o",
            input=f"Search Google for: '{game_name}' site:boardgamegeek.com/boardgame\n\nReturn ONLY the exact BoardGameGeek URL in format: https://boardgamegeek.com/boardgame/[ID]/[slug]\nDo not return any other text, just the URL.",
            tools=[{"type": "web_search"}],
            temperature=0.0,
        )

        # Get content
        content = getattr(resp, "output_text", None)
        if not content:
            chunks = []
            for item in getattr(resp, "output", []) or []:
                if item.get("type") == "message" and "content" in item:
                    for block in item["content"]:
                        if block.get("type") == "output_text" and "text" in block:
                            chunks.append(block["text"])
            content = "\n".join(chunks)

        logger.info(f"[Google BGG] Response: {content[:300]}")

        # Extract URL from response
        bgg_pattern = (
            r"https?://(?:www\.)?boardgamegeek\.com/boardgame/\d+(?:/[a-z0-9-]+)?"
        )
        matches = re.findall(bgg_pattern, content, re.IGNORECASE)

        if matches:
            url = matches[0]
            logger.info(f"[Google BGG] ✓ Found URL: {url}")
            return url

        logger.warning("[Google BGG] ✗ No BGG URL found in response")
        return None

    except Exception as e:
        logger.error(f"[Google BGG] Error: {e}", exc_info=True)
        return None


def google_search_youtube(game_name: str) -> Dict[str, Any]:
    """
    Use Google search to find YouTube tutorial.
    More reliable than generic web_search.
    """
    import logging
    import re

    logger = logging.getLogger(__name__)

    try:
        logger.info(
            f"[Google YouTube] Searching for: '{game_name}' how to play tutorial"
        )

        # Use Responses API with web_search
        resp = client.responses.create(
            model="gpt-4o",
            input=f'Search YouTube or Google for: "how to play {game_name}" tutorial video\n\nFind the best quality tutorial video from channels like Watch It Played, JonGetsGames, Shut Up & Sit Down, or the official publisher.\n\nReturn ONLY a JSON object:\n{{"video_url": "https://www.youtube.com/watch?v=...", "video_title": "...", "channel_name": "..."}}',
            tools=[{"type": "web_search"}],
            temperature=0.0,
        )

        # Get content
        content = getattr(resp, "output_text", None)
        if not content:
            chunks = []
            for item in getattr(resp, "output", []) or []:
                if item.get("type") == "message" and "content" in item:
                    for block in item["content"]:
                        if block.get("type") == "output_text" and "text" in block:
                            chunks.append(block["text"])
            content = "\n".join(chunks)

        logger.info(f"[Google YouTube] Response: {content[:500]}")

        # Try to extract JSON
        result = _extract_json_block(content)
        if result and result.get("video_url"):
            logger.info(
                f"[Google YouTube] ✓ Found: {result.get('video_title')} - {result.get('video_url')}"
            )
            return result

        # Fallback: try to extract YouTube URL directly
        youtube_pattern = r"https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+"
        matches = re.findall(youtube_pattern, content, re.IGNORECASE)

        if matches:
            url = matches[0]
            logger.info(f"[Google YouTube] ✓ Found URL (regex): {url}")
            return {
                "video_url": url,
                "video_title": f"How to Play {game_name}",
                "channel_name": None,
            }

        logger.warning("[Google YouTube] ✗ No YouTube URL found")
        return {"video_url": None, "video_title": None, "channel_name": None}

    except Exception as e:
        logger.error(f"[Google YouTube] Error: {e}", exc_info=True)
        return {"video_url": None, "video_title": None, "channel_name": None}


def find_youtube_tutorial(game_name: str) -> Dict[str, Any]:
    """
    Find the best YouTube tutorial for the game using YouTube Data API v3.
    Returns video_url, video_title, and channel_name.
    Filters by relevance and view count.
    """
    import logging
    import os

    from dotenv import load_dotenv
    from googleapiclient.discovery import build

    load_dotenv()
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"[YouTube API] Searching for tutorial: '{game_name}'")

        # Get YouTube API key from environment
        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            logger.error("[YouTube API] YOUTUBE_API_KEY not found in environment")
            return {"video_url": None, "video_title": None, "channel_name": None}

        # Build YouTube API client
        youtube = build("youtube", "v3", developerKey=api_key)

        # Search for videos with specific query
        search_queries = [
            f"how to play {game_name} tutorial",
            f"{game_name} board game rules",
            f"learn to play {game_name}",
        ]

        best_video = None
        best_score = 0

        for query in search_queries:
            logger.info(f"[YouTube API] Trying query: '{query}'")

            # Search request
            search_response = (
                youtube.search()
                .list(
                    q=query,
                    part="id,snippet",
                    maxResults=10,
                    type="video",
                    order="relevance",  # Sort by relevance first
                    relevanceLanguage="en",
                    safeSearch="none",
                    videoDefinition="any",
                    videoDuration="any",
                )
                .execute()
            )

            video_ids = [
                item["id"]["videoId"] for item in search_response.get("items", [])
            ]

            if not video_ids:
                logger.warning(f"[YouTube API] No results for query: '{query}'")
                continue

            # Get video statistics (views, likes, etc.)
            videos_response = (
                youtube.videos()
                .list(part="snippet,statistics", id=",".join(video_ids))
                .execute()
            )

            # Score each video based on views, relevance, and channel quality
            for video in videos_response.get("items", []):
                video_id = video["id"]
                snippet = video["snippet"]
                stats = video.get("statistics", {})

                title = snippet.get("title", "")
                channel_name = snippet.get("channelTitle", "")
                view_count = int(stats.get("viewCount", 0))
                like_count = int(stats.get("likeCount", 0))

                # Calculate score
                score = 0

                # View count score (logarithmic, max 50 points)
                if view_count > 0:
                    import math

                    score += min(50, math.log10(view_count) * 10)

                # Channel quality boost (known tutorial channels)
                quality_channels = [
                    "watch it played",
                    "jongetsgames",
                    "shut up & sit down",
                    "the rules girl",
                    "rodney smith",
                    "man vs meeple",
                    "rahdo",
                    "dice tower",
                    "actualol",
                ]
                if any(
                    channel.lower() in channel_name.lower()
                    for channel in quality_channels
                ):
                    score += 30
                    logger.info(
                        f"[YouTube API] Quality channel detected: {channel_name}"
                    )

                # Title relevance boost
                title_lower = title.lower()
                if "how to play" in title_lower or "tutorial" in title_lower:
                    score += 20
                if game_name.lower() in title_lower:
                    score += 15

                # Like ratio boost (if available)
                if view_count > 0 and like_count > 0:
                    like_ratio = like_count / view_count
                    score += min(10, like_ratio * 1000)  # Max 10 points

                logger.info(
                    f"[YouTube API] Video: '{title[:50]}...' by {channel_name} - Score: {score:.1f}, Views: {view_count:,}"
                )

                # Update best video if this score is higher
                if score > best_score:
                    best_score = score
                    best_video = {
                        "video_url": f"https://www.youtube.com/watch?v={video_id}",
                        "video_title": title,
                        "channel_name": channel_name,
                        "view_count": view_count,
                        "score": score,
                    }

            # If we found a good match, stop searching
            if best_video and best_score > 50:
                break

        if best_video:
            logger.info(
                f"[YouTube API] ✓ Best match: '{best_video['video_title'][:50]}...' by {best_video['channel_name']} (score: {best_score:.1f}, views: {best_video['view_count']:,})"
            )
            return {
                "video_url": best_video["video_url"],
                "video_title": best_video["video_title"],
                "channel_name": best_video["channel_name"],
            }

        logger.warning(f"[YouTube API] ✗ No suitable tutorial found for '{game_name}'")
        return {"video_url": None, "video_title": None, "channel_name": None}

    except Exception as e:
        logger.error(f"[YouTube API] Error: {e}", exc_info=True)
        return {"video_url": None, "video_title": None, "channel_name": None}
