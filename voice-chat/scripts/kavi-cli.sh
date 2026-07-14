#!/usr/bin/env bash
# kavi - control CLI for the Kavi voice assistant (systemd --user wrapper)
#
# Usage:
#   kavi start          start all three services (whisper-server, llama-server, kavi daemon)
#   kavi stop           stop all three
#   kavi restart        restart all three
#   kavi status         show status of all three
#   kavi logs           follow the kavi daemon log (Ctrl+C to exit)
#   kavi logs whisper   follow the whisper-server log
#   kavi logs llama     follow the llama-server log
#   kavi correct "wrong phrase" "right phrase"   add/update a transcript correction
#                       (applied to every future transcript, no restart needed)
#   kavi corrections    list all saved corrections
#   kavi uncorrect "wrong phrase"   delete a saved correction
set -euo pipefail

UNITS=(kavi-whisper-server.service kavi-llama-server.service kavi.service kavi-xbindkeys.service kavi-indicator.service)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORRECTIONS_FILE="${KAVI_CORRECTIONS_PATH:-$PROJECT_DIR/config/corrections.json}"

usage() {
    grep '^#   kavi' "$0" | sed 's/^# //'
    exit 1
}

cmd="${1:-}"
case "$cmd" in
    start)
        systemctl --user start "${UNITS[@]}"
        ;;
    stop)
        systemctl --user stop "${UNITS[@]}"
        ;;
    restart)
        systemctl --user restart "${UNITS[@]}"
        ;;
    status)
        systemctl --user status "${UNITS[@]}" --no-pager -l
        ;;
    logs)
        case "${2:-daemon}" in
            whisper) journalctl --user -u kavi-whisper-server.service -f ;;
            llama)   journalctl --user -u kavi-llama-server.service -f ;;
            xbind)   journalctl --user -u kavi-xbindkeys.service -f ;;
            indicator) journalctl --user -u kavi-indicator.service -f ;;
            daemon|*) journalctl --user -u kavi.service -f ;;
        esac
        ;;
    correct)
        wrong="${2:-}"; right="${3:-}"
        if [[ -z "$wrong" || -z "$right" ]]; then
            echo "usage: kavi correct \"wrong phrase\" \"right phrase\"" >&2
            exit 1
        fi
        python3 - "$CORRECTIONS_FILE" "$wrong" "$right" <<'EOF'
import json, sys
from pathlib import Path
path, wrong, right = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
data = json.loads(path.read_text()) if path.exists() else {}
data[wrong] = right
path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
print(f"saved: \"{wrong}\" -> \"{right}\" ({path})")
EOF
        ;;
    corrections)
        if [[ -s "$CORRECTIONS_FILE" ]]; then
            python3 -c "import json,sys; d=json.load(open(sys.argv[1])); [print(f'{k!r} -> {v!r}') for k,v in d.items()]" "$CORRECTIONS_FILE"
        else
            echo "(no corrections saved yet)"
        fi
        ;;
    uncorrect)
        wrong="${2:-}"
        if [[ -z "$wrong" ]]; then
            echo "usage: kavi uncorrect \"wrong phrase\"" >&2
            exit 1
        fi
        python3 - "$CORRECTIONS_FILE" "$wrong" <<'EOF'
import json, sys
from pathlib import Path
path, wrong = Path(sys.argv[1]), sys.argv[2]
data = json.loads(path.read_text()) if path.exists() else {}
if wrong in data:
    del data[wrong]
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"deleted: \"{wrong}\"")
else:
    print(f"not found: \"{wrong}\" (run 'kavi corrections' to see exact saved phrases)")
EOF
        ;;
    *)
        usage
        ;;
esac
