#!/usr/bin/env python3
"""CLI zum Senden von Nachrichten an Webex-Räume."""

import json
import mimetypes
import os
import secrets
import time
import webbrowser
from enum import Enum
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import typer

app = typer.Typer(help="Webex-Nachrichten senden und Räume verwalten.")

WEBEX_API = "https://webexapis.com/v1"
WEBEX_AUTH_URL = "https://webexapis.com/v1/authorize"
WEBEX_TOKEN_URL = "https://webexapis.com/v1/access_token"
OAUTH_SCOPES = "spark:messages_write spark:messages_read spark:rooms_read"
REDIRECT_URI = "http://localhost:8080/callback"

ROOMLIST_PATH = Path(__file__).parent / "roomlist.json"
TOKENS_PATH = Path(__file__).parent / ".webex_tokens.json"


# ---------------------------------------------------------------------------
# Token-Speicherung
# ---------------------------------------------------------------------------

def _load_tokens() -> dict | None:
    if TOKENS_PATH.exists():
        return json.loads(TOKENS_PATH.read_text())
    return None


def _save_tokens(data: dict) -> None:
    TOKENS_PATH.write_text(json.dumps(data, indent=2))
    TOKENS_PATH.chmod(0o600)


def _refresh_access_token(tokens: dict) -> dict:
    client_id = os.environ.get("WEBEX_CLIENT_ID", "")
    client_secret = os.environ.get("WEBEX_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("WEBEX_CLIENT_ID / WEBEX_CLIENT_SECRET nicht gesetzt.")

    response = httpx.post(
        WEBEX_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": tokens["refresh_token"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    response.raise_for_status()
    new = response.json()
    new["expires_at"] = time.time() + new["expires_in"] - 60
    return new


def _get_valid_oauth_token() -> str | None:
    tokens = _load_tokens()
    if not tokens:
        return None

    if time.time() < tokens.get("expires_at", 0):
        return tokens["access_token"]

    try:
        typer.echo("Access Token abgelaufen, erneuere...", err=True)
        new_tokens = _refresh_access_token(tokens)
        _save_tokens(new_tokens)
        typer.echo("Token erneuert.", err=True)
        return new_tokens["access_token"]
    except Exception as e:
        typer.echo(f"Token-Erneuerung fehlgeschlagen: {e}", err=True)
        typer.echo("Bitte erneut einloggen: uv run python send_message.py login", err=True)
        return None


# ---------------------------------------------------------------------------
# Räume
# ---------------------------------------------------------------------------

def _load_rooms() -> list[dict]:
    if not ROOMLIST_PATH.exists():
        return []
    return json.loads(ROOMLIST_PATH.read_text())["items"]


def _resolve_room(room_arg: str) -> str:
    rooms = _load_rooms()

    for room in rooms:
        if room["id"] == room_arg:
            return room["id"]

    matches = [r for r in rooms if room_arg.lower() in r["title"].lower()]

    if len(matches) == 1:
        return matches[0]["id"]
    elif len(matches) > 1:
        typer.echo("Mehrere Räume gefunden:", err=True)
        for m in matches:
            typer.echo(f"  {m['title']!r:40s}  {m['id']}", err=True)
        typer.echo("Bitte genaueren Namen oder die Room-ID angeben.", err=True)
        raise typer.Exit(1)

    return room_arg


# ---------------------------------------------------------------------------
# Token-Auflösung
# ---------------------------------------------------------------------------

def _get_token(token: Optional[str]) -> str:
    if token:
        return token

    oauth = _get_valid_oauth_token()
    if oauth:
        return oauth

    env_token = os.environ.get("WEBEX_TOKEN")
    if env_token:
        return env_token

    typer.echo(
        "Kein Token gefunden. Optionen:\n"
        "  1. uv run python send_message.py login  (OAuth)\n"
        "  2. export WEBEX_TOKEN=<token>            (Bot- oder Personal Token)\n"
        "  3. --token <token>                       (einmalig)",
        err=True,
    )
    raise typer.Exit(1)


# ---------------------------------------------------------------------------
# HTTP senden
# ---------------------------------------------------------------------------

def _send_payload(auth_token: str, payload: dict) -> str:
    try:
        response = httpx.post(
            f"{WEBEX_API}/messages",
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        typer.echo(f"Fehler {e.response.status_code}: {e.response.text}", err=True)
        raise typer.Exit(1)
    except httpx.RequestError as e:
        typer.echo(f"Verbindungsfehler: {e}", err=True)
        raise typer.Exit(1)
    msg_id = response.json()["id"]
    typer.echo(f"Gesendet: {msg_id}")
    return msg_id


def _send_multipart(auth_token: str, fields: dict, file_path: Path) -> str:
    """Nachricht mit Dateianhang über multipart/form-data senden."""
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    files = {"files": (file_path.name, file_path.read_bytes(), mime)}
    try:
        response = httpx.post(
            f"{WEBEX_API}/messages",
            headers={"Authorization": f"Bearer {auth_token}"},
            data=fields,
            files=files,
            timeout=30,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        typer.echo(f"Fehler {e.response.status_code}: {e.response.text}", err=True)
        raise typer.Exit(1)
    except httpx.RequestError as e:
        typer.echo(f"Verbindungsfehler: {e}", err=True)
        raise typer.Exit(1)
    msg_id = response.json()["id"]
    typer.echo(f"Gesendet: {msg_id}")
    return msg_id


# ---------------------------------------------------------------------------
# OAuth Login
# ---------------------------------------------------------------------------

@app.command()
def login() -> None:
    """OAuth-Login: Browser öffnen, Token speichern. Einmalig nötig."""
    client_id = os.environ.get("WEBEX_CLIENT_ID")
    client_secret = os.environ.get("WEBEX_CLIENT_SECRET")

    if not client_id or not client_secret:
        typer.echo(
            "Fehlende Umgebungsvariablen:\n"
            "  export WEBEX_CLIENT_ID=<client-id>\n"
            "  export WEBEX_CLIENT_SECRET=<client-secret>\n\n"
            "Integration anlegen unter: https://developer.webex.com/my-apps/new/integration\n"
            f"  Redirect URI: {REDIRECT_URI}\n"
            f"  Scopes: {OAUTH_SCOPES}",
            err=True,
        )
        raise typer.Exit(1)

    state = secrets.token_urlsafe(16)
    auth_params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": OAUTH_SCOPES,
        "state": state,
    }
    auth_url = f"{WEBEX_AUTH_URL}?{urlencode(auth_params)}"

    received: dict = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            params = parse_qs(urlparse(self.path).query)
            received["code"] = params.get("code", [None])[0]
            received["state"] = params.get("state", [None])[0]
            received["error"] = params.get("error", [None])[0]

            if received.get("error"):
                body = f"Login fehlgeschlagen: {received['error']}".encode()
            else:
                body = b"Login erfolgreich! Du kannst dieses Fenster schliessen."

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    typer.echo("Browser wird geöffnet...")
    webbrowser.open(auth_url)
    typer.echo("Warte auf Callback (Port 8080)...")
    server.handle_request()
    server.server_close()

    if received.get("error"):
        typer.echo(f"Fehler vom Authorization Server: {received['error']}", err=True)
        raise typer.Exit(1)

    if received.get("state") != state:
        typer.echo("State-Parameter stimmt nicht überein (möglicher CSRF-Angriff).", err=True)
        raise typer.Exit(1)

    code = received.get("code")
    if not code:
        typer.echo("Kein Code erhalten.", err=True)
        raise typer.Exit(1)

    try:
        response = httpx.post(
            WEBEX_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        typer.echo(f"Token-Austausch fehlgeschlagen: {e.response.text}", err=True)
        raise typer.Exit(1)

    tokens = response.json()
    tokens["expires_at"] = time.time() + tokens["expires_in"] - 60
    _save_tokens(tokens)

    typer.echo(f"Eingeloggt. Token gespeichert in {TOKENS_PATH}")
    typer.echo(f"Gültig bis: {time.strftime('%Y-%m-%d %H:%M', time.localtime(tokens['expires_at']))}")
    typer.echo(f"Refresh Token läuft ab in {tokens.get('refresh_token_expires_in', '?') // 86400} Tagen.")


@app.command()
def logout() -> None:
    """Gespeicherte OAuth-Tokens löschen."""
    if TOKENS_PATH.exists():
        TOKENS_PATH.unlink()
        typer.echo("Tokens gelöscht.")
    else:
        typer.echo("Keine gespeicherten Tokens gefunden.")


# ---------------------------------------------------------------------------
# Befehle
# ---------------------------------------------------------------------------

@app.command()
def send(
    room: str = typer.Argument(..., help="Raumname (Teilstring) oder Room-ID"),
    text: str = typer.Argument(..., help="Zu sendende Nachricht"),
    markdown: bool = typer.Option(False, "--markdown/--no-markdown", help="Text als Markdown senden"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Dateianhang (lokal)"),
    token: Optional[str] = typer.Option(None, "--token", help="Webex-Token (überschreibt alles)"),
) -> None:
    """Nachricht an einen Webex-Raum senden, optional mit Dateianhang."""
    auth_token = _get_token(token)
    room_id = _resolve_room(room)

    if file:
        if not file.exists():
            typer.echo(f"Datei nicht gefunden: {file}", err=True)
            raise typer.Exit(1)
        fields: dict = {"roomId": room_id}
        if markdown:
            fields["markdown"] = text
        else:
            fields["text"] = text
        _send_multipart(auth_token, fields, file)
    else:
        payload: dict = {"roomId": room_id}
        if markdown:
            payload["markdown"] = text
        else:
            payload["text"] = text
        _send_payload(auth_token, payload)


@app.command()
def dm(
    email: str = typer.Argument(..., help="E-Mail-Adresse der Person"),
    text: str = typer.Argument(..., help="Zu sendende Nachricht"),
    markdown: bool = typer.Option(False, "--markdown/--no-markdown", help="Text als Markdown senden"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Dateianhang (lokal)"),
    token: Optional[str] = typer.Option(None, "--token", help="Webex-Token (überschreibt alles)"),
) -> None:
    """Direkt-Nachricht an eine Person per E-Mail senden."""
    auth_token = _get_token(token)

    if file:
        if not file.exists():
            typer.echo(f"Datei nicht gefunden: {file}", err=True)
            raise typer.Exit(1)
        fields = {"toPersonEmail": email}
        if markdown:
            fields["markdown"] = text
        else:
            fields["text"] = text
        _send_multipart(auth_token, fields, file)
    else:
        payload: dict = {"toPersonEmail": email}
        if markdown:
            payload["markdown"] = text
        else:
            payload["text"] = text
        _send_payload(auth_token, payload)


class CardColor(str, Enum):
    default = "default"
    good = "good"
    warning = "warning"
    attention = "attention"


@app.command()
def card(
    room: str = typer.Argument(..., help="Raumname (Teilstring) oder Room-ID"),
    title: str = typer.Option(..., "--title", "-t", help="Titel der Karte"),
    text: str = typer.Option(..., "--text", "-m", help="Nachrichtentext"),
    color: CardColor = typer.Option(CardColor.default, "--color", "-c", help="Titelfarbe: default, good, warning, attention"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="URL für einen Button"),
    url_label: str = typer.Option("Details", "--url-label", help="Beschriftung des URL-Buttons"),
    facts: Optional[list[str]] = typer.Option(None, "--fact", help="Key=Value (wiederholbar, z.B. --fact Host=server1 --fact Status=offline)"),
    token: Optional[str] = typer.Option(None, "--token", help="Webex-Token (überschreibt alles)"),
) -> None:
    """Adaptive Card mit Titel, Text, optionalen Facts und Button senden."""
    auth_token = _get_token(token)
    room_id = _resolve_room(room)

    color_map = {
        CardColor.default: "Default",
        CardColor.good: "Good",
        CardColor.warning: "Warning",
        CardColor.attention: "Attention",
    }

    body: list[dict] = [
        {
            "type": "TextBlock",
            "text": title,
            "weight": "Bolder",
            "size": "Large",
            "color": color_map[color],
        },
        {
            "type": "TextBlock",
            "text": text,
            "wrap": True,
        },
    ]

    if facts:
        parsed = []
        for fact in facts:
            if "=" in fact:
                key, _, value = fact.partition("=")
                parsed.append({"title": key.strip(), "value": value.strip()})
        if parsed:
            body.append({"type": "FactSet", "facts": parsed})

    actions: list[dict] = []
    if url:
        actions.append({"type": "Action.OpenUrl", "title": url_label, "url": url})

    card_content: dict = {
        "type": "AdaptiveCard",
        "version": "1.1",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "body": body,
    }
    if actions:
        card_content["actions"] = actions

    _send_payload(auth_token, {
        "roomId": room_id,
        "text": title,
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card_content,
            }
        ],
    })


@app.command(name="read")
def read_messages(
    room: str = typer.Argument(..., help="Raumname (Teilstring) oder Room-ID"),
    count: int = typer.Option(10, "--count", "-n", help="Anzahl Nachrichten"),
    token: Optional[str] = typer.Option(None, "--token", help="Webex-Token (überschreibt alles)"),
) -> None:
    """Letzte Nachrichten aus einem Raum anzeigen."""
    auth_token = _get_token(token)
    room_id = _resolve_room(room)

    try:
        response = httpx.get(
            f"{WEBEX_API}/messages",
            params={"roomId": room_id, "max": count},
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        typer.echo(f"Fehler {e.response.status_code}: {e.response.text}", err=True)
        raise typer.Exit(1)
    except httpx.RequestError as e:
        typer.echo(f"Verbindungsfehler: {e}", err=True)
        raise typer.Exit(1)

    messages = response.json().get("items", [])
    if not messages:
        typer.echo("Keine Nachrichten gefunden.")
        return

    for msg in reversed(messages):
        ts = msg.get("created", "")[:16].replace("T", " ")
        sender = msg.get("personEmail", "?")
        text = msg.get("text") or "(Karte / Datei)"
        if len(text) > 200:
            text = text[:200] + "..."
        typer.echo(f"[{ts}] {sender}")
        typer.echo(f"  {text}")
        typer.echo()


@app.command(name="rooms-update")
def rooms_update(
    token: Optional[str] = typer.Option(None, "--token", help="Webex-Token (überschreibt alles)"),
) -> None:
    """roomlist.json live von der Webex-API aktualisieren."""
    auth_token = _get_token(token)

    all_rooms: list[dict] = []
    url: Optional[str] = f"{WEBEX_API}/rooms?max=1000"

    while url:
        try:
            response = httpx.get(
                url,
                headers={"Authorization": f"Bearer {auth_token}"},
                timeout=15,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            typer.echo(f"Fehler {e.response.status_code}: {e.response.text}", err=True)
            raise typer.Exit(1)
        except httpx.RequestError as e:
            typer.echo(f"Verbindungsfehler: {e}", err=True)
            raise typer.Exit(1)

        data = response.json()
        all_rooms.extend(data.get("items", []))

        # Paginierung via Link-Header
        link_header = response.headers.get("Link", "")
        url = None
        for part in link_header.split(","):
            part = part.strip()
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break

    ROOMLIST_PATH.write_text(json.dumps({"items": all_rooms}, indent=4))
    typer.echo(f"{len(all_rooms)} Räume gespeichert in {ROOMLIST_PATH}")


@app.command(name="serve")
def serve(
    room: str = typer.Argument(..., help="Ziel-Raumname (Teilstring) oder Room-ID"),
    port: int = typer.Option(9000, "--port", "-p", help="Port des Webhook-Servers"),
    host: str = typer.Option("0.0.0.0", "--host", help="Bind-Adresse"),
    token: Optional[str] = typer.Option(None, "--token", help="Webex-Token (überschreibt alles)"),
) -> None:
    """Webhook-Bridge starten: empfängt POST /notify und leitet nach Webex weiter.

    Erwartet JSON: {"title": "...", "text": "...", "color": "good|warning|attention"}
    Felder 'title' und 'text' sind Pflicht, der Rest optional.
    """
    from flask import Flask, Response, request as flask_request

    auth_token = _get_token(token)
    room_id = _resolve_room(room)

    flask_app = Flask(__name__)

    color_map = {
        "good": "Good",
        "warning": "Warning",
        "attention": "Attention",
        "default": "Default",
    }

    @flask_app.post("/notify")
    def notify() -> Response:
        data = flask_request.get_json(silent=True) or {}
        title = data.get("title", "Notification")
        text = data.get("text", "")
        color = color_map.get(data.get("color", "default"), "Default")
        url = data.get("url")
        url_label = data.get("url_label", "Details")
        facts_raw: dict = data.get("facts", {})

        body: list[dict] = [
            {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Large", "color": color},
            {"type": "TextBlock", "text": text, "wrap": True},
        ]

        if facts_raw:
            body.append({
                "type": "FactSet",
                "facts": [{"title": k, "value": str(v)} for k, v in facts_raw.items()],
            })

        card_content: dict = {
            "type": "AdaptiveCard",
            "version": "1.1",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "body": body,
        }
        if url:
            card_content["actions"] = [{"type": "Action.OpenUrl", "title": url_label, "url": url}]

        try:
            httpx.post(
                f"{WEBEX_API}/messages",
                headers={"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"},
                json={
                    "roomId": room_id,
                    "text": title,
                    "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card_content}],
                },
                timeout=10,
            ).raise_for_status()
        except Exception as e:
            return Response(json.dumps({"error": str(e)}), status=500, mimetype="application/json")

        return Response(json.dumps({"ok": True}), status=200, mimetype="application/json")

    @flask_app.get("/health")
    def health() -> Response:
        return Response(json.dumps({"ok": True}), mimetype="application/json")

    typer.echo(f"Webhook-Bridge läuft auf http://{host}:{port}/notify")
    typer.echo(f"Zielraum: {room_id}")
    flask_app.run(host=host, port=port)


@app.command(name="apprise-url")
def apprise_url(
    room: str = typer.Argument(..., help="Raumname (Teilstring) oder Room-ID"),
    token: Optional[str] = typer.Option(None, "--token", help="Bot-Token (überschreibt WEBEX_TOKEN)"),
) -> None:
    """Apprise-URL für einen Raum ausgeben (wxteams://<token>/<room-id>/)."""
    bot_token = token or os.environ.get("WEBEX_TOKEN")
    if not bot_token:
        typer.echo("Kein Bot-Token. Setze WEBEX_TOKEN oder benutze --token.", err=True)
        raise typer.Exit(1)

    room_id = _resolve_room(room)
    typer.echo(f"wxteams://{bot_token}/{room_id}/")


@app.command(name="list")
def list_rooms(
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Nach Raumname filtern"),
) -> None:
    """Verfügbare Räume aus roomlist.json anzeigen."""
    rooms = _load_rooms()

    if not rooms:
        typer.echo("roomlist.json nicht gefunden oder leer.")
        raise typer.Exit(1)

    if search:
        rooms = [r for r in rooms if search.lower() in r["title"].lower()]

    if not rooms:
        typer.echo("Keine Räume gefunden.")
        raise typer.Exit(1)

    col_w = max(len(r["title"]) for r in rooms) + 2
    typer.echo(f"{'Titel':<{col_w}}  ID")
    typer.echo("-" * (col_w + 60))
    for room in rooms:
        typer.echo(f"{room['title']:<{col_w}}  {room['id']}")


if __name__ == "__main__":
    app()
