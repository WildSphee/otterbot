# Refactoring Summary: Slug Removal & FAISS Integration

## Overview

This refactoring removed the slug-based architecture and replaced it with:
1. **Game ID-based lookups** - All operations now use database IDs
2. **AI-powered game name extraction** - OpenAI structured output with fuzzy matching
3. **FAISS vector search** - Semantic search instead of raw text dumps

## Key Changes

### 1. Database Schema (`app/db/sqlite_db.py`)

**Changes:**
- Removed `slug` column from `games` table
- Made `name` column UNIQUE for direct lookups
- Changed `game_slug` to `game_id` in `chat_log` table (with foreign key)
- Added `get_game_by_id()` method
- Updated all methods to use `game_id` instead of `slug`:
  - `update_game_status(game_id, status)`
  - `update_game_timestamps(game_id)`
  - `list_sources_for_game(game_id)` (new)
- Simplified `find_recent_game_for_chat()` to only check explicit game_id tags

**Migration Note:**
Existing databases will need migration. The table structure has changed. You may need to drop the old database or manually alter tables.

### 2. Schemas (`app/schemas.py`)

**Changes:**
- Removed `slug` field from `Game` model
- Changed `game_slug` to `game_id` in `ChatLog` model
- **Added** `GameNameExtraction` model for structured output:
  ```python
  class GameNameExtraction(BaseModel):
      game_name: Optional[str]
      confidence: str  # high|medium|low
      reasoning: Optional[str]
  ```

### 3. Tools (`app/tools.py`)

**Major Changes:**

**Removed:**
- `slugify()` function - no longer needed

**Added:**
- `extract_game_name(user_text, available_games)` - Uses OpenAI structured output to extract game names, then fuzzy matches against available games using `difflib.get_close_matches()`

**Updated:**
- `get_or_create_game()` - Now uses game IDs for directory names (`storage/games/<game_id>/`)
- `ResearchTool.research()` - Creates FAISS index after downloading sources via `ingest_game_sources()`
- `ResearchTool._save_source()` - Uses `game.store_dir` directly instead of slug lookup

**Completely Rewritten:**
- `QueryTool` class:
  - Removed `_detect_game_from_text()` (regex matching)
  - Removed `_gather_text_snippets()` (raw text gathering)
  - **Added** `_search_faiss()` - Performs semantic search using FAISS
  - **Rewrote** `answer()` to:
    1. Extract game name using structured output
    2. Fuzzy match against available games
    3. Fallback to chat history if no extraction
    4. Use FAISS vector search for context
    5. Generate answer with LLM

### 4. Message Router (`app/otterrouter.py`)

**Changes:**
- Removed `slugify` import
- Updated all `game_slug` parameters to `game_id`
- Changed tagging messages from slugified names to actual game names
- Lookup game ID from DB before logging chat messages

### 5. FAISS Ingestion (`app/datasources/ingest.py`)

**Complete Rewrite:**
- Implemented `ingest_game_sources(game_id)` function
- Reads all text sources for a game (HTML → TXT, direct TXT files)
- Chunks text using `chunk_text()` with 1000-word chunks and 200-word overlap
- Creates FAISS index named after game ID (e.g., `"1"`, `"2"`)
- Stores index in `storage/datasources/<game_id>/`

**Note:** PDF parsing not implemented yet (requires pypdf library)

### 6. FAISS Datasource (`app/datasources/faiss_ds.py`)

**Changes:**
- Updated `DATASOURCE_PATH` to use `storage/datasources/` instead of hardcoded `"datasources"`

### 7. API (`app/api.py`)

**Changes:**
- Removed `slug` from `GameOut` model, added `id`
- Updated all endpoints:
  - `/games` - Returns `id` instead of `slug`
  - `/games/{game_id}` - Changed from `/games/{slug}`
  - `/games/{game_id}/files` - Changed from `/games/{slug}/files`
- File URLs now use game IDs: `/files/{game_id}/{filename}`

## New Workflow

### Research Flow
1. User: "hey otter, research Catan"
2. System parses research intent → game name = "Catan"
3. `ResearchTool.research("Catan")`:
   - Creates game in DB (or gets existing)
   - Downloads sources (Wikipedia, BGG, etc.)
   - **NEW:** Calls `ingest_game_sources(game_id)` to create FAISS index
   - Returns success message

### Query Flow
1. User: "what are the setup rules?"
2. `QueryTool.answer()`:
   - **NEW:** Calls `extract_game_name(user_text, available_games)`
   - Uses OpenAI structured output to extract "setup" context
   - Fuzzy matches against available games
   - Falls back to recent chat history if no match
   - **NEW:** Calls `_search_faiss(game_id, query)` for top-k relevant chunks
   - Builds context from FAISS results (not raw text)
   - Generates answer with LLM
   - Returns answer with citations

## Benefits

1. **No more slug conflicts** - Game IDs are unique by design
2. **Better game name matching** - AI understands "Settlers of Catan" = "Catan"
3. **Semantic search** - FAISS finds relevant chunks, not just keyword matches
4. **Scalable** - FAISS vector search scales better than loading all text
5. **Cleaner architecture** - IDs are natural database keys

## Breaking Changes

⚠️ **Database Migration Required:**
- Old databases with `slug` column will fail
- Chat logs with `game_slug` need migration to `game_id`
- Recommend: Delete old `database.db` for fresh start

⚠️ **API Changes:**
- All `/games/{slug}` endpoints now `/games/{game_id}`
- File URLs changed from `/files/{slug}/` to `/files/{game_id}/`

⚠️ **Storage Structure:**
- Old: `storage/games/<slug>/`
- New: `storage/games/<game_id>/`
- Recommend: Delete old `storage/` directory

## Dependencies

**New:**
- `difflib` (built-in) - For fuzzy matching
- `faiss-cpu` or `faiss-gpu` (assumed installed)
- OpenAI SDK with structured output support (beta.chat.completions.parse)

## Testing Recommendations

1. Test game name extraction with various phrasings
2. Test fuzzy matching (e.g., "Settlers" → "Settlers of Catan")
3. Test FAISS search with different query types
4. Test fallback to chat history
5. Verify FAISS indexes are created during research
6. Check that citations point to correct files

## Future Improvements

1. **PDF Support** - Add PDF text extraction to ingestion
2. **Better Chunking** - Use semantic chunking instead of word count
3. **Rerank Results** - Add cross-encoder reranking after FAISS retrieval
4. **Game Name Cache** - Cache extracted game names to reduce API calls
5. **Hybrid Search** - Combine FAISS with keyword search
