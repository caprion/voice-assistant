#!/usr/bin/env bash
# install.sh - wire up Kavi as a proper installable app on this machine.
# Idempotent: safe to re-run after pulling changes.
#
# What this does:
#   1. Creates ~/.config/kavi/kavi.env from config/kavi.env.example
#      (only if it doesn't already exist - never overwrites your edits)
#   2. Symlinks the systemd unit files into ~/.config/systemd/user/
#   3. Symlinks the `kavi` control CLI into ~/.local/bin/
#   4. Reloads systemd, enables the three services (autostart at login),
#      and starts them now.
#
# To install on a second machine: copy this whole repo over and run this
# script. It fills in your $HOME and repo path automatically. Only edit
# ~/.config/kavi/kavi.env afterwards if your binaries/models live somewhere
# other than the defaults (whisper.cpp/llama.cpp under ~/learn, models
# under ~/.cache - see comments in config/kavi.env.example).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$PROJECT_DIR/.." && pwd)"
CONFIG_DIR="$HOME/.config/kavi"
SYSTEMD_DIR="$HOME/.config/systemd/user"
BIN_DIR="$HOME/.local/bin"

mkdir -p "$CONFIG_DIR" "$SYSTEMD_DIR" "$BIN_DIR"

# --- 1. Config file (never overwrite existing) ---
if [[ ! -f "$CONFIG_DIR/kavi.env" ]]; then
    sed -e "s#__HOME__#$HOME#g" -e "s#__REPO_DIR__#$REPO_DIR#g" \
        "$PROJECT_DIR/config/kavi.env.example" > "$CONFIG_DIR/kavi.env"
    echo "Created $CONFIG_DIR/kavi.env from template (paths filled in for this machine)."
else
    echo "$CONFIG_DIR/kavi.env already exists, leaving it alone."
fi

# --- 2. systemd unit files (symlink, so repo edits take effect on daemon-reload) ---
for unit in kavi-whisper-server.service kavi-llama-server.service kavi.service kavi-xbindkeys.service kavi-indicator.service; do
    ln -sf "$PROJECT_DIR/systemd/$unit" "$SYSTEMD_DIR/$unit"
done
echo "Linked systemd units into $SYSTEMD_DIR"

# --- 3. CLI wrapper ---
ln -sf "$PROJECT_DIR/scripts/kavi-cli.sh" "$BIN_DIR/kavi"
echo "Linked kavi CLI into $BIN_DIR/kavi (make sure $BIN_DIR is on PATH)"

# --- 4. Enable + start ---
systemctl --user daemon-reload
systemctl --user enable kavi-whisper-server.service kavi-llama-server.service kavi.service kavi-xbindkeys.service kavi-indicator.service
systemctl --user start kavi-whisper-server.service kavi-llama-server.service kavi.service kavi-xbindkeys.service kavi-indicator.service

echo ""
echo "Done. Run 'kavi status' to check, 'kavi logs' to follow the daemon log."
echo "Press Print Screen or Right Ctrl to trigger a dictation/chat cycle."
