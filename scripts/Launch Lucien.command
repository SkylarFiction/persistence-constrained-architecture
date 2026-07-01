#!/bin/zsh
set -e

PROJECT_DIR="/Users/nickwhitehead/Desktop/Master files /persistence_constrained_architecture"

cd "$PROJECT_DIR"
clear 2>/dev/null || true

PORT=$(python3 -c 'import socket
for port in range(8787, 8800):
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        sock.close()
        continue
    sock.close()
    print(port)
    break
else:
    raise SystemExit("No open Lucien port found between 8787 and 8799.")
')
URL="http://127.0.0.1:${PORT}/"

echo "Starting Lucien..."
echo
echo "Project: $PROJECT_DIR"
echo "Live cockpit will open at: $URL"
echo
echo "Leave this window open while using Lucien."
echo "Press Control-C here to stop the server."
echo

python3 pca_cli.py --ledger data/lucien_chat.log constitution --write >/dev/null
python3 pca_cli.py --ledger data/lucien_chat.log cockpit --html reports/lucien_cockpit.html >/dev/null

(sleep 1.5 && open "$URL") &

set +e
python3 pca_cli.py live-chat --port "$PORT"
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
