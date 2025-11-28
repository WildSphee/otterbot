import json
import re
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from llms.prompt import WEB_RESEARCH_PROMPT
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


def web_research_links(
    topic: str, model: str = "gpt-4o", max_sources: int = 16
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
