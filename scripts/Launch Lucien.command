#!/bin/zsh
set -e

PROJECT_DIR="/Users/nickwhitehead/Desktop/Master files /persistence_constrained_architecture"

cd "$PROJECT_DIR"
clear
echo "Starting Lucien..."
echo
echo "Project: $PROJECT_DIR"
echo "Live cockpit will open at: http://127.0.0.1:8787/"
echo
echo "Leave this window open while using Lucien."
echo "Press Control-C here to stop the server."
echo

python3 pca_cli.py demo --skip-checks

echo
echo "Lucien has stopped."
echo "You can close this window."
read -k 1 "?Press any key to close..."
