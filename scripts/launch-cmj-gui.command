#!/bin/bash
# CMJ analysis GUI launcher - double-click to run.
# Tries the installed entry point first, then falls back to the module form.
if command -v cmj-gui >/dev/null 2>&1; then
    cmj-gui
else
    echo "cmj-gui not on PATH - trying python3 -m cmj.app.gui ..."
    python3 -m cmj.app.gui
fi
status=$?
if [ $status -ne 0 ]; then
    echo ""
    echo "Launch failed (exit code $status). To fix, run in Terminal:"
    echo "  cd ~/Documents/Python\\ Environments/cmj-processor"
    echo "  python3 -m pip install -e ."
fi
echo ""
echo "Press any key to close this window..."
read -n 1 -s
