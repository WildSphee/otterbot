import logging
import os
from typing import Iterator

from datasources.faiss_ds import FAISSDS
from db.sqlite_db import DB

logger = logging.getLogger(__name__)
db = DB()


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> Iterator[str]:
    """
    Split text into overlapping chunks.
    """
    words = text.split()
    for i in range(0, len(words), chunk_size - overlap):
        chunk_words = words[i : i + chunk_size]
        chunk = " ".join(chunk_words)
        if chunk.strip():
            yield chunk


def ingest_game_sources(game_id: int) -> str:
    """
    Create FAISS index from all downloaded sources for a game.

    Args:
        game_id: The game ID to create index for

    Returns:
        index_name: The name of the created index (str(game_id))
    """
    game = db.get_game_by_id(game_id)
    if not game:
        raise ValueError(f"Game with ID {game_id} not found")

    sources = db.list_sources_for_game(game_id)

    sections = []
    section_id = 0

    for source in sources:
        local_path = source.get("local_path")
        title = source.get("title", "Unknown")

        if not local_path or not os.path.exists(local_path):
            continue

        # Read text content
        text_content = ""
        try:
            # For HTML files, read the extracted .txt version
            if local_path.endswith(".html"):
                txt_path = local_path.replace(".html", ".txt")
                if os.path.exists(txt_path):
                    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                        text_content = f.read()
            # For .txt files, read directly
            elif local_path.endswith(".txt"):
                with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
                    text_content = f.read()
            # For PDFs, skip for now (would need pypdf or similar)
            elif local_path.endswith(".pdf"):
                logger.warning(
                    f"Skipping PDF ingestion for {local_path} - PDF parsing not implemented"
                )
                continue

        except Exception as e:
            logger.error(f"Failed to read {local_path}: {e}")
            continue

        if not text_content.strip():
            continue

        # Chunk the text
        for chunk in chunk_text(text_content, chunk_size=1000, overlap=200):
            sections.append(
                {
                    "id": section_id,
                    "search_key": f"{title} - chunk {section_id}",
                    "content": chunk,
                    "file_url": f"{game_id}/{os.path.basename(local_path)}",
                }
            )
            section_id += 1

    if not sections:
        logger.warning(f"No sections to index for game {game_id}")
        return str(game_id)

    # Create FAISS index
    index_name = str(game_id)
    FAISSDS.create(section=iter(sections), index_name=index_name)

    logger.info(f"Created FAISS index for game {game_id} with {len(sections)} sections")
    return index_name
