# Otterbot 🦦

A Telegram chatbot that serves as a board game assistant for the NCS MA boardgames group. It answers queries about board games, researches game rules from the web, and acts as a knowledgeable assistant during game sessions.

## Features

### Core Capabilities
- 🔍 **Research Mode**: Downloads and indexes game rules, PDFs, YouTube captions, and documentation from the web (up to 30 sources per game)
- 💬 **Hybrid Q&A**: Combines internal knowledge base with live web search for comprehensive, up-to-date answers
- 📚 **Web Interface**: Beautiful HTML interface to browse downloaded game resources with PDF previews
- 🤖 **Smart Intent Routing**: AI-powered intent classification understands natural language queries
- 🎯 **Context-Aware**: Remembers conversation history to infer which game you're asking about

### Intelligence & Automation
- 🧠 **AI Intent Detection**: OpenAI-powered intent classification (research, query, list games, general chat)
- 🌐 **Web Search Integration**: GPT-4o with web search for fresh, accurate answers
- 📝 **Auto-Generated Descriptions**: Automatically creates game descriptions from research sources
- 🎥 **YouTube Caption Extraction**: Downloads and indexes video tutorial transcripts
- 📊 **Smart Chat Type Detection**: Responds differently in groups (requires "otter" mention) vs DMs (no prefix needed)

### User Experience
- ✨ **Telegram-Optimized Formatting**: Converts markdown/HTML to Telegram-compatible markup
- 🎨 **Beautiful File Browser**: Modern web interface with OtterBot logo, categorized files, and preview cards
- 🔗 **Citation Links**: All answers include clickable source citations
- 📁 **Game Library**: Browse all available games with AI-generated descriptions

## Quick Start

### Prerequisites

- Python 3.13+
- Poetry (for dependency management)
- Telegram bot token (from [@BotFather](https://t.me/botfather))
- OpenAI API key

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd otterbot

# Install dependencies
poetry install

# Activate virtual environment
source venv/bin/activate

# Create .env file with your credentials
cat > .env << EOF
OTTER_BOT_TOKEN=your-telegram-bot-token
OPENAI_API_KEY=your-openai-api-key
STORAGE_DIR=storage
DATABASE_NAME=database
API_BASE_URL=http://localhost:8000
EOF
```

### Running the Bot

**Option 1: Run both services with one command (Recommended)**
```bash
bash scripts/start.sh
```

This starts:
- Telegram bot (listens for messages)
- FastAPI web server on `0.0.0.0:8000` (browse game files)

Press `Ctrl+C` to stop both services cleanly.

**Option 2: Run services separately**
```bash
# Terminal 1: Start the Telegram bot
python3 bot/main.py

# Terminal 2: Start the FastAPI server
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
```

### Using the Bot

**In Group Chats** (requires "otter" mention):
```
hey otter, research Catan
otter what games do you have?
otter how do you win in Wingspan?
```

**In Direct Messages** (no prefix needed):
```
research Catan
what games are available?
how do tiebreakers work in Catan?
```

**Available Commands:**
- **Research a game**: `otter research [game name]` - Downloads rules, PDFs, YouTube tutorials
- **Ask questions**: `otter [question about game]` - Answers using internal docs + web search
- **List games**: `otter what games do you have?` - Shows library with AI-generated descriptions
- **General chat**: `otter hello` - Friendly conversation

**Browse Files:**
- **In Telegram**: Use WebApp buttons sent by the bot (tap "📂 View [Game] Files")
- **In Browser**: Visit `http://your-server:8000/games/{game_id}/files` for a beautiful interface
- **Mobile-optimized**: 2 files per row on phones, responsive grid on larger screens

## How It Works

### Research Logic Flow

When you ask OtterBot to research a game (e.g., `otter research Catan`), here's what happens under the hood:

```mermaid
graph TD
    A[User: otter research Catan] --> B[Intent Classification<br/>GPT-4o-mini Structured Output]
    B --> C{Intent: research_game}
    C --> D[Create/Get Game Record<br/>Status: researching]

    D --> E[Step 1: BGG URL Discovery]
    E --> F1{Try BGG XML API<br/>with exact=1}
    F1 -->|Success 200| G1[Use BGG URL]
    F1 -->|401 Auth Required| F2[Google Search Fallback<br/>site:boardgamegeek.com]
    F1 -->|Other Error| F2
    F2 --> G1

    G1 --> H[Step 2: Parallel Fetch<br/>3 concurrent tasks]

    H --> I1[Task 1: Web Research<br/>OpenAI Responses API<br/>Find 20-30 sources]
    H --> I2[Task 2: BGG Metadata<br/>Fetch actual BGG page<br/>Extract difficulty & players]
    H --> I3[Task 3: YouTube Search<br/>Find tutorial video]

    I1 --> J1[Source URLs List]

    I2 --> K1{BGG Page Accessible?}
    K1 -->|200 OK| K2[Parse HTML + JSON-LD<br/>Extract 8000 chars]
    K1 -->|404/Error| K3[No BGG data<br/>bgg_url = null]
    K2 --> K4[LLM Extracts:<br/>difficulty, player_count]
    K4 --> J2[BGG Metadata]
    K3 --> J2

    I3 --> L1{Video Found?}
    L1 -->|No| L2[Google YouTube Fallback]
    L1 -->|Yes| L3[Validate Video URL<br/>YouTube oEmbed API]
    L2 --> L3
    L3 -->|Valid| J3[YouTube URL]
    L3 -->|Invalid/Deleted| L4[No video<br/>video_url = null]
    L4 --> J3

    J1 --> M[Combine & Deduplicate Sources]
    J2 --> M
    J3 --> M

    M --> N{For Each Source}
    N -->|PDF| O1[Download PDF<br/>Save to storage/]
    N -->|HTML| O2[Download HTML<br/>Extract text to .txt]
    N -->|YouTube| O3[Fetch captions<br/>Save as .txt]
    N -->|Link only| O4[Save URL<br/>No download]

    O1 --> P[Create FAISS Index<br/>Embed all text chunks<br/>OpenAI embeddings]
    O2 --> P
    O3 --> P
    O4 --> P

    P --> Q[Generate Description<br/>GPT-4o-mini<br/>From source summaries]

    Q --> R[Save All Metadata<br/>BGG URL, YouTube, difficulty, players, description]

    R --> S[Status: ready]

    S --> T["Send Response:<br/>📚 Files count<br/>📝 Description<br/>📊 Difficulty & Players<br/>📺 YouTube tutorial<br/>🎲 BGG link<br/>📂 WebApp button"]

    style A fill:#e1f5ff
    style T fill:#d4edda
    style H fill:#fff3cd
    style K1 fill:#ffe6e6
    style L3 fill:#ffe6e6
    style P fill:#f8d7da
```

#### Key Steps Explained

1. **Intent Classification** (bot/otterrouter.py:60)
   - Uses GPT-4o-mini structured output to classify user intent
   - Extracts game name from natural language

2. **BGG URL Discovery** (bot/tools.py:118-165)
   - **First**: Try BGG XML API with `exact=1` parameter for better matching
   - **If 401**: BGG now requires authentication - falls back to Google search
   - **Google Fallback**: Searches `site:boardgamegeek.com/boardgame` for accurate URL

3. **Parallel Data Fetching** (bot/tools.py:390-418) - 3 concurrent tasks:
   - **Task 1 - Web Research**: OpenAI Responses API finds 20-30 authoritative sources
   - **Task 2 - BGG Metadata**: Fetches actual BGG page HTML, extracts 8000 chars including JSON-LD, LLM parses difficulty & player count
   - **Task 3 - YouTube**: Searches for tutorial, validates URL with oEmbed API, falls back to Google if needed

4. **YouTube Validation** (bot/tools.py:73-105, 425-431)
   - Uses YouTube oEmbed API to check if video exists
   - Filters out deleted/unavailable videos
   - Google search fallback if initial search fails

5. **Source Download & Processing** (bot/tools.py:244-361)
   - **PDFs**: Downloaded and stored as-is
   - **HTML Pages**: Downloaded + text extracted to companion .txt file
   - **YouTube Videos**: Captions fetched via YouTube Transcript API and saved as .txt
   - **External Links**: URL saved without download (for references, videos without captions)

6. **Vector Index Creation** (datasources/ingest.py)
   - All text files chunked into ~500-token segments
   - Embedded using OpenAI text-embedding-3-small
   - Stored in FAISS index for semantic search

7. **Metadata Enrichment** (bot/llms/openai.py:161-240, bot/tools.py:467-511)
   - LLM extracts **actual** difficulty score and player count from real BGG HTML content
   - Auto-generates 2-3 sentence game description from downloaded sources
   - Saves BGG URL (validated), YouTube link (validated), difficulty, player count, description

8. **Response** (bot/tools.py:525-561, bot/otterrouter.py:135-140)
   - Sends message with game description, metadata, and links
   - Includes difficulty, player count, YouTube tutorial, BGG link
   - Attaches WebApp button to browse files in Telegram
   - Updates game status to "ready"

### Query Logic Flow

When you ask a question about a game (e.g., `otter how do you win in Catan?`):

```mermaid
graph TD
    A[User: otter how do you win in Catan?] --> B[Intent Classification<br/>OpenAI GPT-4o-mini]
    B --> C{Intent Type}
    C -->|query_game| D[Extract Game Name<br/>Structured Output + Fuzzy Match]

    D --> E{Game Identified?}
    E -->|No| F1[Check Recent Chat History<br/>Find last mentioned game]
    F1 --> E
    E -->|Still No| G[Ask User to Clarify]

    E -->|Yes| H{Game in DB?}

    H -->|Yes, Ready| I1[FAISS Vector Search<br/>Find top 5 relevant chunks]
    H -->|No or Not Ready| I2[No Internal Context<br/>Use web search only]

    I1 --> J1[Internal Context + Citations]
    I2 --> J2[Empty Context]

    J1 --> K[OpenAI Responses API<br/>with Web Search]
    J2 --> K

    K --> L[Generate Answer<br/>Hybrid: Internal Docs + Web]

    L --> M{Has Internal Sources?}

    M -->|Yes| N1[Append Internal Citations<br/>with file links]
    M -->|No| N2[Add Disclaimer:<br/>Haven't researched this game yet]

    N1 --> O[Send Answer + Sources + 🦦]
    N2 --> O

    style A fill:#e1f5ff
    style O fill:#d4edda
    style K fill:#fff3cd
    style N2 fill:#f8d7da
```

#### Query Steps Explained

1. **Game Name Extraction** (bot/tools.py:164-207)
   - LLM extracts game name from question
   - Fuzzy matches against available games (60% similarity threshold)
   - Falls back to recent chat history if no explicit mention

2. **Context Retrieval** (bot/tools.py:481-507)
   - If game is researched: FAISS semantic search for relevant chunks
   - Returns top 5 most relevant passages + source citations

3. **Hybrid Answer Generation** (bot/llms/openai.py:63-110)
   - OpenAI Responses API with web_search tool
   - Combines internal knowledge base + live web search
   - Ensures fresh, comprehensive answers

4. **Source Attribution** (bot/tools.py:566-600)
   - **Researched games**: Shows internal file citations + link to full file browser
   - **Non-researched games**: Adds disclaimer suggesting research for better results
   - All answers end with 🦦

## Development

### Code Quality

```bash
# Format and lint code
bash scripts/lint.sh

# Check only (no fixes)
bash scripts/lint.sh . --check

# Individual tools
ruff format .              # Format code
ruff check . --fix         # Lint and fix
mypy .                     # Type checking
```

### Project Structure

```
otterbot/
├── bot/                     # Telegram bot code
│   ├── main.py              # Bot entry point
│   ├── otterrouter.py       # Message routing with AI intent classification
│   ├── tools.py             # Research, Query, and GamesListTool
│   ├── webapp.py            # Telegram WebApp button utilities
│   ├── utils.py             # Utility functions (chat detection, markdown conversion)
│   ├── schemas.py           # Pydantic models (Game, UserIntent, etc.)
│   ├── db/
│   │   └── sqlite_db.py     # Database layer with game descriptions
│   ├── llms/
│   │   ├── openai.py        # GPT-4o integration with web search
│   │   └── prompt.py        # Centralized prompt templates
│   └── datasources/
│       ├── faiss_ds.py      # FAISS vector store with source URLs
│       └── ingest.py        # Document ingestion (PDFs, HTML, YouTube)
├── api/                     # FastAPI web server
│   ├── server.py            # API endpoints
│   ├── render.py            # HTML rendering logic
│   ├── templates/           # HTML templates
│   │   └── game_files.html
│   └── static/
│       └── css/
│           └── styles.css   # Mobile-optimized responsive styles
├── assets/
│   └── images/
│       └── otterbotlogo.png # Bot logo for web interface
├── scripts/
│   ├── start.sh             # Start both services
│   └── lint.sh              # Code formatting and linting
├── storage/                 # Downloaded files and database
│   ├── games/               # Game files organized by ID
│   └── datasources/         # FAISS indices per game
├── CLAUDE.md                # AI assistant documentation
└── README.md                # This file
```

## Recent Updates

### 2025-11-30: Critical Reliability & Accuracy Fixes

#### BGG Integration Fixes
- 🔧 **Fixed BGG XML API 401 Errors**: BGG now requires authentication tokens - added automatic Google search fallback
- ✅ **Accurate BGG Metadata**: Now fetches actual BGG page HTML (8000 chars + JSON-LD) instead of using web search
- 🎯 **Ground Truth Data**: Difficulty and player count are guaranteed from real BGG pages (never hallucinated)
- 🔗 **URL Validation**: If BGG page is inaccessible (404/timeout), link is removed entirely

#### YouTube Validation
- ✓ **Video Validation**: Added YouTube oEmbed API validation to filter out deleted/unavailable videos
- 🔄 **Google Fallback**: If initial YouTube search fails, automatically tries Google search
- 📺 **Reliable Links**: Only shows YouTube tutorials that are verified to exist

#### Enhanced Research Output
- 📝 **Game Descriptions**: Now includes AI-generated game description in research completion message
- 🐛 **Debug Logging**: Comprehensive logging at all decision points ([BGG], [YouTube], [Research])
- 📊 **Transparent**: Logs show exactly what's being fetched and extracted

### 2025-11-29: Architecture & Features

### Refactoring & Architecture
- 📁 **Reorganized Project**: Renamed `app/` to `bot/`, created separate `api/` folder
- 🎨 **Decoupled Frontend**: Extracted CSS/HTML into `api/static/` and `api/templates/`
- 📱 **Mobile-First UI**: Responsive CSS with 2-column grid on phones, adaptive on larger screens
- 🔧 **Updated Scripts**: Modified `start.sh` to work with new structure

### Major Features Added
- 📲 **Telegram WebApp Integration**: View files within Telegram (no external browser needed)
- 🌐 **Web Search Integration**: GPT-4o with live web search for comprehensive answers
- 🧠 **AI Intent Routing**: Replaced regex with OpenAI-powered intent classification
- 🎥 **YouTube Caption Support**: Automatically downloads and indexes video tutorial transcripts
- 📝 **Auto-Generated Descriptions**: Creates game descriptions from research sources using GPT-4o-mini
- 📚 **Games Library View**: Beautiful listing of all games with descriptions and WebApp buttons
- 💬 **Smart Chat Detection**: Different behavior in groups vs direct messages
- 🔗 **Better Citations**: Shows both web sources and internal documents with clickable links

### Technical Improvements
- Centralized all prompts in `bot/llms/prompt.py` for maintainability
- Improved markdown/HTML conversion with support for mixed formats
- Added Telegram-safe formatting (no tables, headers, or horizontal rules)
- Enhanced error handling with user-friendly failure messages
- Increased research sources from 16 to 30 per game
- Fixed game description generation bug
- Clean separation of concerns: bot logic in `bot/`, API in `api/`

## License

MIT License - You're welcome to fork it for your own purpose.

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.
