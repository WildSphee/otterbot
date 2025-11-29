# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Otterbot is a Telegram chatbot that serves as a board game assistant for the NCS MA boardgames group. It has two primary functions:

1. **Research**: Downloads and stores game rules/documentation from the web
2. **Q&A**: Answers user questions about game rules using RAG (retrieval-augmented generation)

## Project Structure

```
otterbot/
├── bot/              # Telegram bot code
│   ├── main.py       # Bot entry point
│   ├── otterrouter.py # Message routing and intent handling
│   ├── tools.py      # Research, Query, and Games List tools
│   ├── webapp.py     # WebApp button utilities
│   ├── utils.py      # Message formatting helpers
│   ├── db/           # Database layer
│   ├── llms/         # OpenAI integration
│   └── datasources/  # FAISS vector search
├── api/              # FastAPI web server
│   ├── server.py     # API endpoints
│   ├── render.py     # HTML rendering
│   ├── templates/    # HTML templates
│   └── static/       # CSS and assets
├── storage/          # Game files and databases
├── assets/           # Static assets (images, etc.)
└── scripts/          # Utility scripts
```

## Development Commands

### Environment Setup
```bash
# Install dependencies
poetry install

# Activate virtual environment (if not using poetry shell)
source venv/bin/activate
```

### Running the Application

**Recommended: Start both services together**
```bash
# Start both Telegram bot and FastAPI server with one command
bash scripts/start.sh

# This script:
# - Starts FastAPI on 0.0.0.0:8000 (api/server.py)
# - Starts Telegram bot (bot/main.py)
# - Tracks PIDs for both processes
# - Handles cleanup on Ctrl+C (kills both processes)
```

**Alternative: Start services separately**
```bash
# Terminal 1: Start the Telegram bot
python3 bot/main.py

# Terminal 2: Start the FastAPI file server (for browsing stored files)
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
```

**Important:** The FastAPI server must bind to `0.0.0.0` (not `127.0.0.1`) to be accessible from external browsers. Links sent by the bot (e.g., `https://otterbot.space/games/1/files`) require the API server to be running and accessible.

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

### Telegram WebApp Integration

The bot uses Telegram's WebApp feature to display game files in a native in-app interface:

**Components:**
- **WebApp Utilities** (bot/webapp.py): Reusable functions for creating WebApp buttons
  - `create_game_files_button(game_id, game_name)` - Button to view files for a specific game
  - `create_games_library_button()` - Button to browse all games
- **Research workflow** (bot/otterrouter.py:110-115): Sends WebApp button after researching
- **Games list** (bot/otterrouter.py:72-90): Displays WebApp buttons (2 per row) for all ready games
- **Display**: FastAPI (api/server.py) serves beautiful HTML pages within Telegram's WebApp viewer
  - **Templates**: HTML in api/templates/game_files.html
  - **Styles**: Responsive CSS in api/static/css/styles.css (mobile-optimized, 2 files per row on phones)

**User Experience:**
1. User researches a game → Bot sends "📂 View [Game] Files" button
2. User taps button → WebApp opens in-app showing all downloaded files
3. User can view PDFs, HTML pages, and external links without leaving Telegram

### Core Flow

**Message handling** (bot/otterrouter.py:20 `otterhandler`)
- All Telegram messages are filtered through one handler
- Only responds to messages mentioning "otter" in the first 32 chars (or private chats)
- Routes to either Research or Query workflow based on intent parsing

**Research workflow** (bot/tools.py:297 `ResearchTool.research`)
1. Parse "research <game>" intent from message
2. Call OpenAI Responses API with web_search tool to find sources
3. Download PDFs and HTML pages, extract text from HTML
4. Store files in `storage/games/<game-id>/`
5. Record sources in SQLite `game_sources` table
6. Generate game description using LLM
7. Update game status to "ready"
8. Send WebApp button for file browsing

**Query workflow** (bot/tools.py:451 `QueryTool.answer`)
1. Infer which game user is asking about via:
   - Explicit game name in message
   - Chat history (most recent game mentioned)
2. Search FAISS vector index for relevant text chunks
3. Use web search to supplement internal knowledge
4. Build context and send to OpenAI with QA prompt
5. Return answer with source citations

### Database Schema (bot/db/sqlite_db.py)

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

### LLM Integration (bot/llms/openai.py)

**Research**: Uses OpenAI Responses API (NOT Chat Completions)
- `client.responses.create()` with `web_search` tool
- Returns structured JSON with source URLs
- Prompt in bot/llms/prompt.py:31 `WEB_RESEARCH_PROMPT`

**Q&A**: Uses Responses API with web_search
- `client.responses.create()` with `web_search` tool
- Combines internal FAISS results with web search
- Prompt in bot/llms/prompt.py:95 `WEB_SEARCH_QA_PROMPT`

**Description Generation**: Uses Chat Completions API
- `client.chat.completions.create()`
- Generates 2-3 sentence game descriptions
- Prompt in bot/llms/prompt.py:64 `GAME_DESCRIPTION_PROMPT`

### FastAPI Web Interface (api/server.py)

The FastAPI server (api/server.py) provides:
1. **JSON API endpoints** for programmatic access
2. **Beautiful HTML interface** for browsing game files (WebApp-ready)

**Key endpoints:**
- `GET /games` - List all games (JSON)
- `GET /games/{game_id}` - Get game details (JSON)
- `GET /games/{game_id}/files` - Browse game files (HTML by default, add `?format=json` for JSON)
- `GET /files/{game_id}/{filename}` - Serve static files (PDFs, HTML, etc.)

**HTML Interface Features:**
- **Mobile-optimized**: 2 files per row on phones, responsive grid on tablets/desktop
- **Clean separation**: HTML templates (api/templates/) and CSS (api/static/css/)
- **Rendering**: api/render.py handles HTML generation
- Files grouped by type (PDFs, Web Pages, External Links)
- PDF preview thumbnails embedded in cards
- Hover animations and modern UI
- Badges showing downloaded vs. external files
- Direct links to view files and original sources

### Key Dependencies

- **python-telegram-bot**: Telegram bot framework
- **openai**: For Responses API (web research) and Chat API (Q&A)
- **beautifulsoup4**: HTML parsing and text extraction
- **fastapi**: Web server for browsing stored docs with beautiful HTML interface
- **uvicorn**: ASGI server for FastAPI
- **faiss-cpu**: Vector database for semantic search
- **sqlite3**: Built-in, no external DB required

## Important Patterns

### Singleton DB (bot/db/sqlite_db.py:10)
The `DB` class uses singleton pattern with thread-safe initialization. Always instantiate as `db = DB()` - you'll get the same instance.

### Game Inference (bot/tools.py:451)
When user asks a question without naming the game, system checks:
1. Explicit game names extracted via LLM structured output
2. Fuzzy matching against available games
3. Recent chat context (tagged game_id in chat_log)

### File Storage Structure
```
storage/
  games/
    <game-id>/         # Uses numeric game ID, not slug
      page.html        # Downloaded HTML
      page.txt         # Extracted text from HTML
      rulebook.pdf     # Downloaded PDFs
      ...
  datasources/
    <game-id>/         # FAISS vector indices per game
      index.faiss
      metadata.pkl
```

**Note:** Storage directories use numeric game IDs (e.g., `storage/games/1/`) for simplicity and to avoid issues with special characters in game names.

## Configuration

Environment variables (create `.env` file):
```bash
OTTER_BOT_TOKEN=<telegram-bot-token>     # Required - from @BotFather
OPENAI_API_KEY=<openai-key>              # Required - for LLM and embeddings
DATABASE_NAME=otterbot                    # Optional, defaults to "database"
STORAGE_DIR=storage                    # Optional, defaults to "storage"
API_BASE_URL=https://otterbot.space       # Required - public URL for file links in bot messages
```

**Critical:** `API_BASE_URL` should be your public-facing URL (e.g., `https://otterbot.space`), not `localhost`. The bot sends links like `{API_BASE_URL}/games/1/files` to users in Telegram.

## Common Issues

### Multiple Bot Instances
**Symptom:** Telegram API errors about "terminated by other getUpdates request"

**Solution:** Only run one bot instance at a time. Check for existing processes:
```bash
ps aux | grep "python.*main.py" | grep -v grep
```
Kill any existing instances before starting a new one.

### HTML Parsing Errors in Telegram
**Symptom:** Messages fail with "Can't parse entities: unsupported start tag"

**Solution:** Telegram's HTML parser only supports: `<b>`, `<i>`, `<a>`, `<code>`, `<pre>`. The bot uses `app/utils.py:md_to_html()` to convert markdown to Telegram-compatible HTML. Never use `<br>` tags - use newlines instead.

### API Not Accessible from Browser
**Symptom:** Can't access `http://your-server:8000` from browser

**Solution:** Ensure uvicorn binds to `0.0.0.0` (not `127.0.0.1`):
```bash
uvicorn app.api:app --host 0.0.0.0 --port 8000
```

## Testing Notes

No test suite currently exists. When adding tests:
- Mock `DB` by passing a test SQLite connection to `DB(conn=...)`
- Mock OpenAI calls in `llms/openai.py`
- Use test fixtures for sample HTML/PDF content
