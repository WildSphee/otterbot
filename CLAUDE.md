# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Otterbot is a Telegram chatbot that serves as a board game assistant for the NCS MA boardgames group. It has two primary functions:

1. **Research**: Downloads and stores game rules/documentation from the web
2. **Q&A**: Answers user questions about game rules using RAG (retrieval-augmented generation)

## Development Commands

### Environment Setup
```bash
# Install dependencies
poetry install

# Activate virtual environment (if not using poetry shell)
source venv/bin/activate
```

### Running the Application
```bash
# Start the Telegram bot (main app)
python -m app.main

# Start the FastAPI file server (optional, for browsing stored files)
uvicorn app.api:app --reload
```

### Linting and Code Quality
```bash
# Format and lint code (applies fixes)
sh scripts/lint.sh

# Check only (no fixes)
sh scripts/lint.sh . --check

# Individual tools
ruff format .              # Format code
ruff check . --fix         # Lint and fix
mypy .                     # Type checking
```

## Architecture

### Core Flow

**Message handling** (app/otterrouter.py:46 `otterhandler`)
- All Telegram messages are filtered through one handler
- Only responds to messages mentioning "otter" in the first 32 chars
- Routes to either Research or Query workflow based on intent parsing

**Research workflow** (app/tools.py:115 `ResearchTool.research`)
1. Parse "research <game>" intent from message
2. Call OpenAI Responses API with web_search tool to find sources
3. Download PDFs and HTML pages, extract text from HTML
4. Store files in `storage/games/<game-slug>/`
5. Record sources in SQLite `game_sources` table
6. Update game status to "ready"

**Query workflow** (app/tools.py:210 `QueryTool.answer`)
1. Infer which game user is asking about via:
   - Explicit game name in message
   - Chat history (most recent game mentioned)
2. Gather text snippets from stored sources
3. Build context (max 20k chars) and send to OpenAI with QA prompt
4. Return answer with source citations

### Database Schema (app/db/sqlite_db.py)

**games**: Core game records with status tracking
- `slug`: URL-safe identifier derived from name
- `status`: created → researching → ready
- `store_dir`: Local path for downloaded files

**game_sources**: Downloaded/linked resources per game
- `source_type`: pdf|html|link|video|txt|other
- `local_path`: Where file is stored (if downloaded)

**chat_log**: Telegram conversation history
- Stores user/assistant/system messages
- `game_slug`: Tagged game for context inference
- Used to infer which game user is asking about

### LLM Integration (app/llms/openai.py)

**Research**: Uses OpenAI Responses API (NOT Chat Completions)
- `client.responses.create()` with `web_search` tool
- Returns structured JSON with source URLs
- Prompt in app/llms/prompt.py:15 `WEB_RESEARCH_PROMPT`

**Q&A**: Uses Chat Completions API
- `client.chat.completions.create()`
- Prompt in app/llms/prompt.py:7 `QA_SYSTEM_PROMPT`

### Key Dependencies

- **python-telegram-bot**: Telegram bot framework
- **openai**: For Responses API (web research) and Chat API (Q&A)
- **beautifulsoup4**: HTML parsing and text extraction
- **fastapi**: Optional file server to browse stored docs
- **sqlite3**: Built-in, no external DB required

## Important Patterns

### Slug Generation (app/tools.py:23)
All game names are converted to URL-safe slugs (lowercase, hyphens, no special chars). Used consistently for directories, DB lookups, and file paths.

### Singleton DB (app/db/sqlite_db.py:10)
The `DB` class uses singleton pattern with thread-safe initialization. Always instantiate as `db = DB()` - you'll get the same instance.

### Game Inference (app/tools.py:172)
When user asks a question without naming the game, system checks:
1. Explicit `game_slug` tags in recent chat messages
2. Text matching of known game names in conversation history (last 200 msgs)

### File Storage Structure
```
storage/
  games/
    <game-slug>/
      page.html        # Downloaded HTML
      page.txt         # Extracted text from HTML
      rulebook.pdf     # Downloaded PDFs
      ...
```

## Configuration

Environment variables (create `.env` file):
```bash
OTTER_BOT_TOKEN=<telegram-bot-token>     # Required
OPENAI_API_KEY=<openai-key>              # Required (loaded by openai SDK)
STORAGE_DIR=storage                       # Optional, defaults to "storage"
DATABASE_NAME=database                    # Optional, defaults to "database"
API_BASE_URL=http://localhost:8000        # For file server links
```

## Testing Notes

No test suite currently exists. When adding tests:
- Mock `DB` by passing a test SQLite connection to `DB(conn=...)`
- Mock OpenAI calls in `llms/openai.py`
- Use test fixtures for sample HTML/PDF content
