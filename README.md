# webexApi

CLI-Tool zum Senden von Nachrichten, Adaptive Cards und Dateien an Webex-Räume.

## Setup

```bash
uv sync
```

## Authentifizierung

### Option 1: Bot-Token (empfohlen für Automatisierung)
Bot-Token aus `us-tik-nfl-notibot.txt` als Umgebungsvariable setzen.
Der Bot muss in den Zielraum eingeladen sein (`us-tik-nfl-notibot@webex.bot`).

```bash
export WEBEX_TOKEN="<bot-token>"
```

### Option 2: OAuth (Personal Token mit Auto-Refresh)
Integration auf [developer.webex.com](https://developer.webex.com/my-apps/new/integration) anlegen:
- Redirect URI: `http://localhost:8080/callback`
- Scopes: `spark:messages_write spark:messages_read spark:rooms_read`

```bash
export WEBEX_CLIENT_ID="<client-id>"
export WEBEX_CLIENT_SECRET="<client-secret>"
uv run python send_message.py login
```

Token wird in `.webex_tokens.json` gespeichert und automatisch erneuert.

**Token-Priorität:** `--token` > OAuth (`.webex_tokens.json`) > `WEBEX_TOKEN` Env-Var

---

## Befehle

### `send` — Textnachricht senden

```bash
uv run python send_message.py send "Raumname" "Nachricht"
uv run python send_message.py send "Raumname" "**Fett** und _kursiv_" --markdown
uv run python send_message.py send "Raumname" "Siehe Anhang" --file /pfad/zur/datei.log
```

### `dm` — Direkt-Nachricht an Person

```bash
uv run python send_message.py dm "user@example.com" "Hallo!"
uv run python send_message.py dm "user@example.com" "Report" --file report.pdf
```

### `card` — Adaptive Card senden

```bash
uv run python send_message.py card "Raumname" \
  --title "Server-Alert" \
  --text "nflpuppet15 ist offline" \
  --color attention \
  --fact Host=nflpuppet15 \
  --fact Status=offline \
  --url "https://monitoring.example.com" \
  --url-label "Details"
```

Farben: `default` | `good` (grün) | `warning` (gelb) | `attention` (rot)

### `read` — Nachrichten lesen

```bash
uv run python send_message.py read "Raumname"
uv run python send_message.py read "Raumname" -n 20
```

Benötigt Scope `spark:messages_read`.

### `serve` — Webhook-Bridge

Empfängt `POST /notify` und leitet als Adaptive Card nach Webex weiter.
Für Dienste ohne Apprise-Unterstützung (Grafana, Alertmanager etc.).

```bash
uv run python send_message.py serve "Raumname" --port 9000
```

Erwartetes JSON:

```json
{
  "title": "Deployment",
  "text": "Version 2.4.1 ist live",
  "color": "good",
  "facts": { "Host": "server1", "Dauer": "3m" },
  "url": "https://monitoring.example.com",
  "url_label": "Details"
}
```

Felder `title` und `text` sind Pflicht, der Rest optional.
Health-Check: `GET /health`

### `apprise-url` — Apprise-URL generieren

Für Dienste mit Apprise-Unterstützung (Bot muss im Raum sein):

```bash
export WEBEX_TOKEN="<bot-token>"
uv run python send_message.py apprise-url "Raumname"
# → wxteams://<token>/<room-id>/
```

### `rooms-update` — Raumliste aktualisieren

Zieht alle Räume live von der Webex-API und speichert sie in `roomlist.json`.

```bash
uv run python send_message.py rooms-update
```

Benötigt Scope `spark:rooms_read`.

### `list` — Räume anzeigen

```bash
uv run python send_message.py list
uv run python send_message.py list --search "Test"
```

### `login` / `logout` — OAuth verwalten

```bash
uv run python send_message.py login
uv run python send_message.py logout
```

---

## Raumauswahl

Alle Befehle akzeptieren den Raumnamen als **Teilstring** (case-insensitive) oder die vollständige Room-ID aus `roomlist.json`.

```bash
# Alle gleich gültig:
send_message.py send "BotTestBereich" "..."
send_message.py send "bottest" "..."
send_message.py send "Y2lzY29zcGFyaz..." "..."
```

Bei mehreren Treffern wird eine Liste ausgegeben.

---

## Dateien

| Datei | Beschreibung |
|-------|-------------|
| `send_message.py` | CLI-Script |
| `roomlist.json` | Gecachte Raumliste (via `rooms-update` aktualisieren) |
| `.webex_tokens.json` | OAuth-Tokens (auto-generiert, nicht committen) |
| `us-tik-nfl-notibot.txt` | Bot-Credentials |
| `.env.example` | Vorlage für Umgebungsvariablen |
