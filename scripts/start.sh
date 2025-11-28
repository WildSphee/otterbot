#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the project root directory (parent of scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo -e "${RED}Error: venv directory not found${NC}"
    exit 1
fi

source venv/bin/activate

# Arrays to store PIDs
declare -a PIDS=()

# Cleanup function - kills all child processes
cleanup() {
    echo -e "\n${YELLOW}Shutting down OtterBot services...${NC}"

    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${YELLOW}Killing process $pid${NC}"
            kill "$pid" 2>/dev/null || true
        fi
    done

    # Wait a moment for graceful shutdown
    sleep 1

    # Force kill if still running
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${RED}Force killing process $pid${NC}"
            kill -9 "$pid" 2>/dev/null || true
        fi
    done

    echo -e "${GREEN}All processes stopped${NC}"
    exit 0
}

# Trap SIGINT (Ctrl+C) and SIGTSTP (Ctrl+Z) and other signals
trap cleanup SIGINT SIGTERM SIGTSTP EXIT

echo -e "${GREEN}Starting OtterBot services...${NC}"

# Start FastAPI server in background
echo -e "${GREEN}Starting FastAPI server on 0.0.0.0:8000...${NC}"
uvicorn app.api:app --host 0.0.0.0 --port 8000 &
API_PID=$!
PIDS+=($API_PID)
echo -e "${GREEN}FastAPI started with PID: $API_PID${NC}"

# Give API a moment to start
sleep 2

# Start Telegram bot in background
echo -e "${GREEN}Starting Telegram bot...${NC}"
python3 app/main.py &
BOT_PID=$!
PIDS+=($BOT_PID)
echo -e "${GREEN}Telegram bot started with PID: $BOT_PID${NC}"

echo -e "\n${GREEN}================================${NC}"
echo -e "${GREEN}OtterBot is running!${NC}"
echo -e "${GREEN}================================${NC}"
echo -e "FastAPI: http://0.0.0.0:8000"
echo -e "Telegram bot: Active"
echo -e "\nPress ${YELLOW}Ctrl+C${NC} to stop all services"
echo -e "${GREEN}================================${NC}\n"

# Wait for all background processes
wait
