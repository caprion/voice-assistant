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
set -euo pipefail

UNITS=(kavi-whisper-server.service kavi-llama-server.service kavi.service kavi-xbindkeys.service kavi-indicator.service)

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
    *)
        usage
        ;;
esac
