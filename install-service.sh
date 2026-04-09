#!/usr/bin/env bash
# install-service.sh — Installiert webex-bridge als systemd-Service
set -euo pipefail

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

readonly SERVICE_NAME="webex-bridge"
readonly SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
readonly DEFAULT_PORT=9000
readonly DEFAULT_VENV="/opt/webexapi"

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Installiert 'webex serve' als systemd-Service auf SLES/Linux.

OPTIONS:
  -p PORT      Port der Bridge (Standard: ${DEFAULT_PORT})
  -u USER      Benutzer der den Service ausführt (Standard: aktueller Benutzer)
  -i REPO      Repo-Pfad: installiert Tool via venv (ohne uv/pipx)
  -v VENV      Venv-Pfad bei -i (Standard: ${DEFAULT_VENV})
  -r           Service deinstallieren
  -h           Diese Hilfe anzeigen

BEISPIELE:
  $(basename "$0")                          # installieren (webex muss im PATH sein)
  $(basename "$0") -i /opt/src/webexApi     # installieren via venv
  $(basename "$0") -i /opt/src/webexApi -v /opt/myvenv -p 8080
  $(basename "$0") -u deploy -i /opt/src/webexApi
  $(basename "$0") -r                       # deinstallieren
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

install_venv() {
    local repo_path="$1"
    local venv_path="$2"

    [[ -f "${repo_path}/pyproject.toml" ]] \
        || die "Kein gültiges Repo unter '${repo_path}' (pyproject.toml fehlt)."

    local python_bin
    python_bin=$(command -v python3) || die "python3 nicht gefunden."

    local python_version
    python_version=$("$python_bin" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    local required_major=3 required_minor=12
    local actual_major actual_minor
    actual_major=$(echo "$python_version" | cut -d. -f1)
    actual_minor=$(echo "$python_version" | cut -d. -f2)

    if (( actual_major < required_major || (actual_major == required_major && actual_minor < required_minor) )); then
        die "Python ${required_major}.${required_minor}+ erforderlich (gefunden: ${python_version})."
    fi

    log "Erstelle venv unter ${venv_path} (Python ${python_version})..."
    "$python_bin" -m venv "$venv_path"

    log "Installiere webexapi aus ${repo_path}..."
    "${venv_path}/bin/pip" install --quiet --upgrade pip
    "${venv_path}/bin/pip" install --quiet "${repo_path}"

    log "Installation abgeschlossen: ${venv_path}/bin/webex"
    echo "${venv_path}/bin/webex"
}

find_webex_binary() {
    local user="$1"
    local home_dir
    home_dir=$(getent passwd "$user" | cut -d: -f6)

    local candidates=(
        "${home_dir}/.local/bin/webex"
        "${DEFAULT_VENV}/bin/webex"
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
    local found
    found=$(su - "$user" -c "which webex 2>/dev/null" || true)
    if [[ -n "$found" ]]; then
        echo "$found"
        return 0
    fi

    return 1
}

write_service_file() {
    local webex_bin="$1"
    local run_user="$2"
    local port="$3"
    local home_dir
    home_dir=$(getent passwd "$run_user" | cut -d: -f6)

    local repo_dir
    repo_dir="$(cd "$(dirname "$0")" && pwd)"
    local git_url
    git_url=$(git -C "$repo_dir" remote get-url origin 2>/dev/null \
        | sed 's|.*github.com[:/]||;s|\.git$||' || echo "webexapi")

    log "Erstelle ${SERVICE_FILE}..."
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Webex Webhook Bridge
Documentation=https://github.com/${git_url}
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
}

install_service() {
    local port="$1"
    local run_user="$2"
    local repo_path="$3"
    local venv_path="$4"

    local webex_bin

    if [[ -n "$repo_path" ]]; then
        webex_bin=$(install_venv "$repo_path" "$venv_path")
    else
        log "Suche webex-Binary für Benutzer '${run_user}'..."
        if ! webex_bin=$(find_webex_binary "$run_user"); then
            die "'webex' nicht gefunden. Optionen:\n" \
                "  Mit venv:  sudo bash $(basename "$0") -i /pfad/zum/repo\n" \
                "  Mit uv:    uv tool install /pfad/zum/repo"
        fi
    fi
    log "Binary: ${webex_bin}"

    write_service_file "$webex_bin" "$run_user" "$port"

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
    systemctl stop    "${SERVICE_NAME}.service" || true
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
repo_path=""
venv_path="${DEFAULT_VENV}"
remove=false

while getopts ":p:u:i:v:rh" opt; do
    case "$opt" in
        p) port="$OPTARG" ;;
        u) run_user="$OPTARG" ;;
        i) repo_path="$OPTARG" ;;
        v) venv_path="$OPTARG" ;;
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
    if ! id "$run_user" &>/dev/null; then
        die "Benutzer '${run_user}' existiert nicht."
    fi

    if ! [[ "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
        die "Ungültiger Port: ${port}"
    fi

    if [[ -n "$repo_path" && ! -d "$repo_path" ]]; then
        die "Repo-Verzeichnis nicht gefunden: ${repo_path}"
    fi

    install_service "$port" "$run_user" "$repo_path" "$venv_path"
fi
