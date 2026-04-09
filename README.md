# webexApi

CLI-Tool zum Senden von Nachrichten, Adaptive Cards und Dateien an Webex-Räume.

## Installation

```bash
# Entwicklung
uv sync

# Global als `webex`-Befehl installieren
uv tool install .
```

Nach globaler Installation ersetzt `webex` das `uv run python send_message.py`.

---

## Erstkonfiguration

```bash
webex setup
```

Interaktiver Wizard der fragt:
- **Bot-Token** — wird in `~/.config/webexapi/config.json` gespeichert
- **Standard-Raum** — Auswahl per Nummer oder Teilstring; danach ist `RAUM` bei `send`, `card`, `read`, `serve` optional
- **OAuth-Credentials** — Client ID + Secret für persönlichen Login

Gespeicherte Config: `~/.config/webexapi/config.json` (chmod 600)

---

## Authentifizierung

**Token-Priorität:** `--token` > OAuth (`.webex_tokens.json`) > `config.json bot_token` > `WEBEX_TOKEN` Env-Var

### Option A: Bot-Token via setup (empfohlen)

```bash
webex setup   # Bot-Token eingeben, wird dauerhaft gespeichert
```

Der Bot muss in den Zielraum eingeladen sein:
```
/invite us-tik-nfl-notibot@webex.bot
```

### Option B: Bot-Token als Umgebungsvariable

```bash
export WEBEX_TOKEN="<bot-token>"
```

### Option C: OAuth (Personal Token mit Auto-Refresh)

Integration anlegen auf [developer.webex.com](https://developer.webex.com/my-apps/new/integration):
- Redirect URI: `http://localhost:8080/callback`
- Scopes: `spark:messages_write spark:messages_read spark:rooms_read`

Credentials einmalig hinterlegen (via `setup` oder Env-Var), dann einloggen:

```bash
webex setup          # OAuth-Credentials eingeben
webex login          # Browser öffnet sich, Token wird gespeichert
```

Token wird automatisch erneuert. Mit OAuth sind Räume auch ohne Bot-Mitgliedschaft erreichbar.

---

## Befehle

### `setup` — Konfiguration einrichten

```bash
webex setup
```

```
Bot-Token (aktuell: nicht gesetzt): ********
Standard-Raum (aktuell: keiner)
   1. BotTestBereich
   2. Monitoring
   3. Alerts
  Nummer oder Raumname (Enter = beibehalten): 1
OAuth-Credentials einrichten? [n]: n
Config gespeichert in /Users/user/.config/webexapi/config.json
```

---

### `send` — Textnachricht senden

```bash
# Mit Standard-Raum aus config.json (kein RAUM-Argument nötig)
webex send "Deployment abgeschlossen"

# Expliziter Raum (Teilstring oder Room-ID)
webex send monitoring "Disk usage 95%"

# Markdown
webex send monitoring "**WARNUNG** Disk usage `95%`" --markdown

# Mit Dateianhang (Bild, PDF, Log, ...)
webex send monitoring "Siehe Anhang" --file /var/log/app.log
webex send monitoring "Screenshot" --file /tmp/screen.png

# Einmaliger Token-Override
webex send monitoring "Test" --token <token>
```

---

### `dm` — Direkt-Nachricht an Person

```bash
webex dm user@example.com "Hallo!"
webex dm user@example.com "**Wichtig**: bitte prüfen" --markdown
webex dm user@example.com "Bericht" --file report.pdf
```

---

### `card` — Adaptive Card senden

Minimales Beispiel:

```bash
webex card monitoring --title "Alert" --text "Server down"
```

Alle Optionen:

```bash
webex card monitoring \
  --title "Deploy fertig" \
  --subtitle "Produktionsumgebung" \
  --text "Version 2.3.1 erfolgreich deployed" \
  --color good \
  --separator \
  --fact "Host=server1" \
  --fact "Duration=42s" \
  --fact "Commit=abc1234" \
  --image "https://example.com/badge.png" \
  --url "https://grafana.example.com" --url-label "Grafana" \
  --url "https://logs.example.com"    --url-label "Logs"
```

**Farben:** `default` | `good` (grün) | `warning` (gelb) | `attention` (rot)

| Option | Beschreibung |
|--------|-------------|
| `--title` | Titel (fett, groß) — Pflicht |
| `--text` | Nachrichtentext — Pflicht |
| `--subtitle` | Untertitel unterhalb des Titels |
| `--color` | Titelfarbe |
| `--separator` | Trennlinie vor dem Text |
| `--fact KEY=VALUE` | Key-Value Zeile (wiederholbar) |
| `--image URL` | Bild (wiederholbar) |
| `--url URL` | Button-URL (wiederholbar) |
| `--url-label TEXT` | Button-Beschriftung, je `--url` eine (Standard: "Details") |

---

### `read` — Nachrichten lesen

```bash
webex read                      # Standard-Raum, letzte 10 Nachrichten
webex read monitoring           # expliziter Raum
webex read monitoring -n 25    # mehr Nachrichten
```

Benötigt Scope `spark:messages_read` (OAuth) oder Bot-Token mit Raummitgliedschaft.

---

### `rooms-update` — Raumliste aktualisieren

Zieht alle zugänglichen Räume von der API und speichert sie in `~/.config/webexapi/roomlist.json`.

```bash
webex rooms-update
```

- Mit **Bot-Token**: gibt Räume zurück, in denen der Bot Mitglied ist
- Mit **OAuth-Token** (`spark:rooms_read`): alle persönlichen Räume

---

### `list` — Räume anzeigen

```bash
webex list                        # alle Räume aus roomlist.json
webex list --search "monitoring"  # gefiltert
```

---

### `serve` — Webhook-Bridge

Startet einen HTTP-Server der `POST /notify` empfängt und als Adaptive Card nach Webex weiterleitet. Für Dienste ohne natives Apprise-Support (Grafana, Alertmanager, eigene Skripte).

```bash
webex serve monitoring --port 9000
webex serve monitoring --port 9000 --host 127.0.0.1
```

Erwartetes JSON-Payload:

```json
{
  "title": "Deployment",
  "text": "Version 2.4.1 ist live",
  "color": "good",
  "facts": {
    "Host": "server1",
    "Dauer": "3m"
  },
  "url": "https://monitoring.example.com",
  "url_label": "Details"
}
```

Felder `title` und `text` sind Pflicht, alles andere optional.

```bash
# Testen:
curl -X POST http://localhost:9000/notify \
  -H "Content-Type: application/json" \
  -d '{"title":"Test","text":"Webhook funktioniert","color":"good"}'

# Health-Check:
curl http://localhost:9000/health
```

---

### `apprise-url` — URL für Apprise generieren

Für Dienste mit nativer Apprise-Unterstützung (Uptime Kuma, Gotify, etc.):

```bash
webex apprise-url monitoring
# → wxteams://<bot-token>/<room-id>/
```

Gibt die URL direkt aus — in Apprise als Notification-URL eintragen.
Erfordert Bot-Token (`WEBEX_TOKEN` oder `--token`).

---

### `login` / `logout` — OAuth verwalten

```bash
webex login    # Browser öffnet sich, Token wird gespeichert
webex logout   # gespeichertes Token löschen
```

---

## Raumauswahl

Alle Befehle mit `RAUM`-Argument akzeptieren:

```bash
webex send "BotTestBereich" "..."   # exakter Name
webex send "bottest" "..."          # Teilstring (case-insensitive)
webex send "Y2lzY29zcGFyaz..." "..." # Room-ID direkt
```

Bei mehreren Treffern wird eine Auswahlliste ausgegeben.
Wenn ein Standard-Raum konfiguriert ist, kann das Argument weggelassen werden.

---

## Dateien

| Pfad | Beschreibung |
|------|-------------|
| `send_message.py` | CLI-Hauptskript |
| `~/.config/webexapi/config.json` | Bot-Token, Standard-Raum, OAuth-Credentials (chmod 600) |
| `~/.config/webexapi/roomlist.json` | Gecachte Raumliste (via `rooms-update` befüllen) |
| `~/.config/webexapi/.webex_tokens.json` | OAuth-Tokens (auto-generiert, chmod 600) |
