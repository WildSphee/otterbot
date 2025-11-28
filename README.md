# Otterbot 🦦

A Telegram chatbot that serves as a board game assistant for the NCS MA boardgames group. It answers queries about board games, researches game rules from the web, and acts as a knowledgeable assistant during game sessions.

## Features

- 🔍 **Research Mode**: Downloads and indexes game rules, PDFs, and documentation from the web
- 💬 **Q&A Mode**: Answers questions about game rules using RAG (retrieval-augmented generation)
- 📚 **Web Interface**: Beautiful HTML interface to browse downloaded game resources
- 🤖 **Context-Aware**: Remembers conversation history to infer which game you're asking about

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
python app/main.py

# Terminal 2: Start the FastAPI server
uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

### Using the Bot

**Research a game:**
```
hey otter, research Catan
hey otter, i wanna learn about Wingspan
```

**Ask questions:**
```
hey otter, what's the setup for Catan?
hey otter, tell me about winning conditions
```

**Browse files:**
Visit `http://your-server:8000/games/{game_id}/files` in your browser for a beautiful interface showing all downloaded resources.

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
├── app/
│   ├── main.py           # Telegram bot entry point
│   ├── api.py            # FastAPI web server
│   ├── otterrouter.py    # Message routing and handlers
│   ├── tools.py          # Research and query tools
│   ├── utils.py          # Utility functions (HTML/Markdown conversion)
│   ├── db/               # Database layer
│   ├── llms/             # OpenAI integration
│   └── datasources/      # FAISS vector store
├── scripts/
│   ├── start.sh          # Start both services
│   └── lint.sh           # Linting script
├── storage/              # Downloaded files and database
├── CLAUDE.md             # AI assistant documentation
└── README.md             # This file
```

## License

MIT License - You're welcome to fork it for your own purpose.

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.
