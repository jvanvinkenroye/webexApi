#!/usr/bin/env bash
# install-service.sh — Installiert webex-bridge als systemd-Service
set -euo pipefail

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

readonly SERVICE_NAME="webex-bridge"
readonly SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
readonly DEFAULT_PORT=9000

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Installiert 'webex serve' als systemd-Service auf SLES/Linux.

OPTIONS:
  -p PORT    Port der Bridge (Standard: ${DEFAULT_PORT})
  -u USER    Benutzer der den Service ausführt (Standard: aktueller Benutzer)
  -r         Service deinstallieren
  -h         Diese Hilfe anzeigen

BEISPIELE:
  $(basename "$0")                    # installieren mit Standardwerten
  $(basename "$0") -p 8080            # anderen Port
  $(basename "$0") -u deploy          # anderen Benutzer
  $(basename "$0") -r                 # deinstallieren
EOF
}

log()  { echo "[INFO]  $*"; }
err()  { echo "[ERROR] $*" >&2; }
die()  { err "$*"; exit 1; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        die "Root-Rechte erforderlich. Bitte mit sudo ausführen."
    fi
}

find_webex_binary() {
    local user="$1"
    local home_dir
    home_dir=$(getent passwd "$user" | cut -d: -f6)

    # Reihenfolge: uv tool install, pipx, system PATH
    local candidates=(
        "${home_dir}/.local/bin/webex"
        "/usr/local/bin/webex"
        "/usr/bin/webex"
    )

    for candidate in "${candidates[@]}"; do
        if [[ -x "$candidate" ]]; then
            echo "$candidate"
            return 0
        fi
    done

    # Letzter Versuch: which als Ziel-User
    if su - "$user" -c "which webex" 2>/dev/null; then
        return 0
    fi

    return 1
}

install_service() {
    local port="$1"
    local run_user="$2"

    log "Suche webex-Binary für Benutzer '${run_user}'..."
    local webex_bin
    if ! webex_bin=$(find_webex_binary "$run_user"); then
        die "'webex' nicht gefunden für Benutzer '${run_user}'.\n" \
            "Bitte zuerst installieren: uv tool install /pfad/zum/repo"
    fi
    log "Binary gefunden: ${webex_bin}"

    local home_dir
    home_dir=$(getent passwd "$run_user" | cut -d: -f6)

    log "Erstelle ${SERVICE_FILE}..."
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Webex Webhook Bridge
Documentation=https://github.com/$(git -C "$(dirname "$0")" remote get-url origin 2>/dev/null | sed 's|.*github.com[:/]||;s|\.git$||' || echo "webexapi")
After=network.target

[Service]
Type=simple
User=${run_user}
ExecStart=${webex_bin} serve --port ${port}
Restart=on-failure
RestartSec=5
Environment=HOME=${home_dir}

StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

    log "Lade systemd-Konfiguration neu..."
    systemctl daemon-reload

    log "Aktiviere und starte Service..."
    systemctl enable "${SERVICE_NAME}.service"
    systemctl restart "${SERVICE_NAME}.service"

    echo ""
    log "Service installiert. Status:"
    systemctl status "${SERVICE_NAME}.service" --no-pager || true

    echo ""
    log "Nützliche Befehle:"
    echo "  sudo systemctl status  ${SERVICE_NAME}"
    echo "  sudo systemctl restart ${SERVICE_NAME}"
    echo "  sudo journalctl -u ${SERVICE_NAME} -f"
    echo ""
    log "Bridge erreichbar unter: http://$(hostname -f):${port}/notify/<raum>"
}

uninstall_service() {
    if [[ ! -f "$SERVICE_FILE" ]]; then
        die "Service-Datei nicht gefunden: ${SERVICE_FILE}"
    fi

    log "Stoppe und deaktiviere ${SERVICE_NAME}..."
    systemctl stop "${SERVICE_NAME}.service"    || true
    systemctl disable "${SERVICE_NAME}.service" || true

    log "Lösche ${SERVICE_FILE}..."
    rm -f "$SERVICE_FILE"

    systemctl daemon-reload
    log "Service deinstalliert."
}

# ---------------------------------------------------------------------------
# Argumente parsen
# ---------------------------------------------------------------------------

port="${DEFAULT_PORT}"
run_user="${SUDO_USER:-$(whoami)}"
remove=false

while getopts ":p:u:rh" opt; do
    case "$opt" in
        p) port="$OPTARG" ;;
        u) run_user="$OPTARG" ;;
        r) remove=true ;;
        h) usage; exit 0 ;;
        :) die "Option -${OPTARG} benötigt ein Argument." ;;
        \?) die "Unbekannte Option: -${OPTARG}" ;;
    esac
done

# ---------------------------------------------------------------------------
# Hauptlogik
# ---------------------------------------------------------------------------

check_root

if [[ "$remove" == true ]]; then
    uninstall_service
else
    # Benutzer validieren
    if ! id "$run_user" &>/dev/null; then
        die "Benutzer '${run_user}' existiert nicht."
    fi

    # Port validieren
    if ! [[ "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
        die "Ungültiger Port: ${port}"
    fi

    install_service "$port" "$run_user"
fi
