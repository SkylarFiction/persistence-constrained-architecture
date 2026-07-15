#!/bin/zsh
set -e

PROJECT_DIR="/Users/nickwhitehead/Desktop/Master files /persistence_constrained_architecture"

cd "$PROJECT_DIR"
clear 2>/dev/null || true

echo "Starting Lucien..."
echo
echo "Project: $PROJECT_DIR"
echo "Lucien will choose a free local port automatically."
echo
echo "Leave this window open while using Lucien."
echo "Press Control-C here to stop the server."
echo

python3 pca_cli.py --ledger data/lucien_chat.log constitution --write >/dev/null
python3 pca_cli.py --ledger data/lucien_chat.log cockpit --html reports/lucien_cockpit.html >/dev/null

set +e
python3 pca_cli.py --ledger data/lucien_chat.log live-chat --port 0 --open-browser
EXIT_CODE=$?
set -e

echo
if [ "$EXIT_CODE" -eq 130 ]; then
  echo "Lucien stopped."
else
  echo "Lucien stopped with exit code $EXIT_CODE."
fi
echo "You can close this window."
read -k 1 "?Press any key to close..."
