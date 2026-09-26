#!/bin/bash
# CMJ analysis GUI launcher - double-click to run.

# Find the project directory relative to this launcher.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "CMJ Processor virtual environment not found."
    echo ""
    echo "Expected:"
    echo "  $VENV_PYTHON"
    echo ""
    echo "To create it, run:"
    echo "  cd \"$PROJECT_DIR\""
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  python -m pip install -e ."
    echo ""
    echo "Press any key to close this window..."
    read -n 1 -s
    exit 1
fi

cd "$PROJECT_DIR"

MPLBACKEND=TKAgg "$VENV_PYTHON" -m cmj.app.gui

status=$?

if [ $status -ne 0 ]; then
    echo ""
    echo "CMJ Processor failed to launch (exit code $status)."
    echo ""
    echo "Press any key to close this window..."
    read -n 1 -s
fi

exit $status