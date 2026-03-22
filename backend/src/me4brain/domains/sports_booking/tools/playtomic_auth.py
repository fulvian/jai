"""Playtomic Authentication - Google OAuth con Token Persistente.

Gestisce l'autenticazione con Playtomic tramite Google OAuth.
I token vengono salvati localmente e rinnovati automaticamente.

Flusso:
1. Login one-time: apre browser → Google consent → id_token
2. Scambio: id_token → Playtomic access_token + refresh_token
3. Uso: Bearer token per API calls
4. Refresh: automatico quando token sta per scadere

Usage:
    auth = PlaytomicAuth()
    token = await auth.get_valid_token()  # Automaticamente refresha se necessario
"""

import os
import json
import time
import base64
import hashlib
import asyncio
from pathlib import Path
from typing import Any
from datetime import datetime, timedelta

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Playtomic OAuth config (identificato da analisi browser)
PLAYTOMIC_GOOGLE_CLIENT_ID = (
    "218496144327-dd1r8ui5rmnh2ecj5rh7885o4sqok4at.apps.googleusercontent.com"
)
PLAYTOMIC_AUTH_API = "https://playtomic.com/api/v1/auth"
TOKEN_FILE = Path.home() / ".me4brain" / "playtomic_tokens.json"
TIMEOUT = 30.0


class PlaytomicAuth:
    """Gestione autenticazione Playtomic con Google OAuth."""

    def __init__(self, token_file: Path | None = None):
        """Inizializza l'auth manager.

        Args:
            token_file: Path al file tokens (default: ~/.me4brain/playtomic_tokens.json)
        """
        self.token_file = token_file or TOKEN_FILE
        self._tokens: dict[str, Any] | None = None
        self._encryption_key = self._derive_key()

    def _derive_key(self) -> bytes:
        """Deriva chiave di encryption da machine ID."""
        # Usa combinazione di fattori machine-specific
        machine_id = ""

        # macOS: usa hardware UUID
        try:
            import subprocess

            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
            )
            import re

            match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', result.stdout)
            if match:
                machine_id = match.group(1)
        except Exception:
            pass

        # Fallback: usa home directory + username
        if not machine_id:
            machine_id = f"{os.path.expanduser('~')}:{os.getenv('USER', 'default')}"

        # Deriva chiave da SHA256
        return hashlib.sha256(machine_id.encode()).digest()

    def _encrypt(self, data: str) -> str:
        """Encrypta dati con XOR semplice (per uso locale)."""
        # Nota: per produzione usare cryptography.fernet
        key = self._encryption_key
        encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data.encode()))
        return base64.b64encode(encrypted).decode()

    def _decrypt(self, data: str) -> str:
        """Decrypta dati."""
        key = self._encryption_key
        encrypted = base64.b64decode(data.encode())
        decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(encrypted))
        return decrypted.decode()

    def _load_tokens(self) -> dict[str, Any] | None:
        """Carica tokens dal file."""
        if self._tokens:
            return self._tokens

        if not self.token_file.exists():
            return None

        try:
            with open(self.token_file) as f:
                encrypted = json.load(f)

            # Decrypta i token sensibili
            tokens = {
                "access_token": self._decrypt(encrypted["access_token"]),
                "refresh_token": self._decrypt(encrypted["refresh_token"]),
                "expires_at": encrypted["expires_at"],
                "user_id": encrypted.get("user_id"),
                "email": encrypted.get("email"),
            }
            self._tokens = tokens
            return tokens
        except Exception as e:
            logger.error("playtomic_load_tokens_error", error=str(e))
            return None

    def _save_tokens(self, tokens: dict[str, Any]) -> None:
        """Salva tokens su file (encrypted)."""
        # Crea directory se non esiste
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

        # Encrypta token sensibili
        encrypted = {
            "access_token": self._encrypt(tokens["access_token"]),
            "refresh_token": self._encrypt(tokens["refresh_token"]),
            "expires_at": tokens["expires_at"],
            "user_id": tokens.get("user_id"),
            "email": tokens.get("email"),
            "created_at": datetime.now().isoformat(),
        }

        with open(self.token_file, "w") as f:
            json.dump(encrypted, f, indent=2)

        # Imposta permessi restrittivi
        os.chmod(self.token_file, 0o600)

        self._tokens = tokens
        logger.info("playtomic_tokens_saved", email=tokens.get("email"))

    def _is_expired(self, tokens: dict[str, Any]) -> bool:
        """Controlla se il token è scaduto o sta per scadere."""
        expires_at = tokens.get("expires_at", 0)
        # Considera scaduto se mancano meno di 5 minuti
        return time.time() > (expires_at - 300)

    async def get_valid_token(self) -> str | None:
        """Ottiene un token valido, refreshando se necessario.

        Returns:
            Access token valido, o None se autenticazione necessaria
        """
        tokens = self._load_tokens()

        if not tokens:
            logger.warning("playtomic_no_tokens", hint="Run setup_auth to login")
            return None

        if self._is_expired(tokens):
            logger.info("playtomic_token_expired", refreshing=True)
            try:
                tokens = await self._refresh_token(tokens["refresh_token"])
                self._save_tokens(tokens)
            except Exception as e:
                logger.error("playtomic_refresh_failed", error=str(e))
                return None

        return tokens["access_token"]

    async def _refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Rinnova l'access token usando il refresh token.

        Args:
            refresh_token: Token di refresh

        Returns:
            Nuovi tokens

        Raises:
            Exception: Se il refresh fallisce
        """
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{PLAYTOMIC_AUTH_API}/refresh",
                json={"refresh_token": refresh_token},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", refresh_token),
                "expires_at": time.time() + data.get("expires_in", 3600),
                "user_id": data.get("user_id"),
                "email": data.get("email"),
            }

    async def login_with_google(self, id_token: str) -> dict[str, Any]:
        """Completa il login scambiando l'id_token Google con Playtomic.

        Args:
            id_token: JWT id_token da Google OAuth

        Returns:
            dict con tokens e info utente
        """
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{PLAYTOMIC_AUTH_API}/google",
                json={"id_token": id_token},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

            tokens = {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_at": time.time() + data.get("expires_in", 3600),
                "user_id": data.get("user_id"),
                "email": data.get("email"),
            }

            self._save_tokens(tokens)

            return {
                "success": True,
                "email": tokens["email"],
                "user_id": tokens["user_id"],
                "message": "Login completato! Token salvato per uso futuro.",
            }

    async def logout(self) -> dict[str, Any]:
        """Rimuove i token salvati (logout locale)."""
        if self.token_file.exists():
            self.token_file.unlink()
            self._tokens = None
            return {"success": True, "message": "Logout completato"}
        return {"success": True, "message": "Nessun token da rimuovere"}

    def is_authenticated(self) -> bool:
        """Controlla se l'utente è autenticato."""
        tokens = self._load_tokens()
        return tokens is not None

    def get_user_info(self) -> dict[str, Any] | None:
        """Ottiene info utente dai token salvati."""
        tokens = self._load_tokens()
        if not tokens:
            return None
        return {
            "email": tokens.get("email"),
            "user_id": tokens.get("user_id"),
            "authenticated": True,
        }


# =============================================================================
# CLI Setup Helper
# =============================================================================


async def interactive_login():
    """Avvia il flusso di login interattivo via browser.

    Questo metodo:
    1. Avvia un server HTTP locale per ricevere il callback
    2. Apre il browser sulla pagina di login Google di Playtomic
    3. Riceve l'id_token dal redirect
    4. Scambia con Playtomic per ottenere access/refresh tokens
    """
    import webbrowser
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse

    print("\n🎾 Playtomic Authentication Setup")
    print("=" * 40)

    # Server locale per ricevere il callback
    received_token = {"token": None}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)

            if "id_token" in params:
                received_token["token"] = params["id_token"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"""
                    <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>&#x2705; Login completato!</h1>
                    <p>Puoi chiudere questa finestra.</p>
                    </body></html>
                """)
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Silenzia log

    # Avvia server su porta random
    server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    # URL di login Google (usando client_id di Playtomic)
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={PLAYTOMIC_GOOGLE_CLIENT_ID}&"
        f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
        "response_type=id_token&"
        "scope=openid%20email%20profile&"
        "nonce=" + str(int(time.time()))
    )

    print(f"\n📱 Aprendo browser per login Google...")
    print(f"   Se non si apre automaticamente, vai a:\n   {auth_url[:80]}...")

    webbrowser.open(auth_url)

    print("\n⏳ In attesa del login...")

    # Attendi callback (timeout 5 min)
    server.timeout = 300
    while not received_token["token"]:
        server.handle_request()
        if not received_token["token"]:
            break

    server.server_close()

    if not received_token["token"]:
        print("\n❌ Timeout: login non completato")
        return False

    # Scambia token con Playtomic
    print("\n🔄 Scambio token con Playtomic...")

    auth = PlaytomicAuth()
    try:
        result = await auth.login_with_google(received_token["token"])
        print(f"\n✅ {result['message']}")
        print(f"   Email: {result['email']}")
        return True
    except Exception as e:
        print(f"\n❌ Errore: {e}")
        return False


def main():
    """Entry point per CLI setup."""
    asyncio.run(interactive_login())


if __name__ == "__main__":
    main()
