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

## Recent Updates (2025-11-29)

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
