#!/bin/bash
# CMJ analysis GUI launcher - double-click to run.

# Use the adjacent project when launched from scripts/. A copied launcher
# reuses the last project location, or asks for it on its first launch.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/cmj-processor/project-directory"

if [ ! -f "$PROJECT_DIR/src/cmj/app/gui.py" ] && [ -f "$PROJECT_FILE" ]; then
    IFS= read -r PROJECT_DIR < "$PROJECT_FILE"
fi

while [ ! -f "$PROJECT_DIR/src/cmj/app/gui.py" ]; do
    PROJECT_DIR="$(osascript -e 'POSIX path of (choose folder with prompt "Choose the cmj-processor project folder (containing src and scripts).")')" || exit 0
    PROJECT_DIR="${PROJECT_DIR%/}"
done

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

cd "$PROJECT_DIR" || exit 1

# Remember the location for copies on the Desktop or elsewhere.
if mkdir -p "$(dirname "$PROJECT_FILE")"; then
    printf '%s\n' "$PROJECT_DIR" > "$PROJECT_FILE"
fi

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
