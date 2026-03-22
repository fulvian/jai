#!/usr/bin/env python3
"""Script per generare token.json tramite flusso OAuth2.

Usage:
    uv run python scripts/google_oauth_setup.py

Questo script apre il browser per l'autenticazione Google e salva
il token.json per l'accesso a Drive, Gmail, Calendar, etc.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

# Workaround: Google può sostituire alcuni scopes (es. coursework.me → student-submissions.me)
# Questa variabile disabilita la verifica stricta degli scopes
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

# Scopes richiesti per tutti i servizi Google Workspace
# ALLINEATO A: src/me4brain/integrations/google_workspace.py
SCOPES = [
    # Drive - full access per read/write/export
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
    # Gmail - readonly + modify + send
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    # Calendar - full access per CRUD eventi
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    # Meet - read conference records, transcripts, recordings
    "https://www.googleapis.com/auth/meetings.space.readonly",
    "https://www.googleapis.com/auth/drive.meet.readonly",
    # Docs - full access per create/edit
    "https://www.googleapis.com/auth/documents",
    # Sheets - full access per create/edit
    "https://www.googleapis.com/auth/spreadsheets",
    # Slides - full access per create/edit
    "https://www.googleapis.com/auth/presentations",
    # Classroom - read courses and coursework
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
    # Forms - read forms and responses
    "https://www.googleapis.com/auth/forms.body.readonly",
    "https://www.googleapis.com/auth/forms.responses.readonly",
]


def main():
    """Esegue il flusso OAuth2 e salva il token."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("❌ GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET non configurati in .env")
        return

    # Crea configurazione client OAuth
    # NOTA: Per app desktop, Google richiede "urn:ietf:wg:oauth:2.0:oob" o localhost configurato
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    print("🔐 Avvio flusso OAuth2 Google...")
    print("   Il browser si aprirà per l'autenticazione.")
    print()

    # ISTRUZIONI CRITICHE PER EVITARE SCADENZA TOKEN
    print("=" * 60)
    print("⚠️  IMPORTANTE: EVITARE SCADENZA TOKEN OGNI 7 GIORNI")
    print("=" * 60)
    print()
    print("   Se il token scade ogni 7 giorni, l'app GCP è in 'Testing mode'.")
    print("   Per avere token che NON scadono, devi passare a 'Production':")
    print()
    print("   1. Vai su: https://console.cloud.google.com/apis/credentials/consent")
    print("   2. Clicca 'PUBLISH APP' / 'PUBBLICA APP'")
    print("   3. Conferma (non serve verifica Google per uso personale)")
    print()
    print("   Dopo la pubblicazione, i refresh_token NON scadranno più!")
    print("=" * 60)
    print()

    print("   Scopes richiesti:")
    for scope in SCOPES:
        print(f"   - {scope.split('/')[-1]}")
    print()

    # Esegue il flusso OAuth con access_type=offline per refresh token duratura
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    print("   ➡️  Quando il browser si apre:")
    print("   1. Seleziona 'Continua' anche se l'app non è verificata")
    print("   2. Concedi TUTTI i permessi richiesti")
    print()

    credentials = flow.run_local_server(
        port=8080,
        access_type="offline",  # Richiede refresh_token
        prompt="consent",  # Forza consent per nuovo refresh_token
    )

    # Valida che abbiamo ottenuto refresh_token
    if not credentials.refresh_token:
        print("❌ ERRORE: Google non ha restituito refresh_token!")
        print("   Possibili cause:")
        print("   1. Non hai dato il consenso completo")
        print("   2. L'app GCP non ha 'access_type=offline' configurato")
        print("   3. Il tuo account ha già un token attivo - revoca l'accesso e riprova:")
        print("      https://myaccount.google.com/permissions")
        return

    # Salva il token - USA IL PATH CORRETTO
    token_path = Path(os.getenv("GOOGLE_TOKEN_PATH", "data/google_token.json"))
    token_path.parent.mkdir(parents=True, exist_ok=True)  # Crea directory se non esiste

    token_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes) if credentials.scopes else SCOPES,  # list, non frozenset
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
    }

    with open(token_path, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\n✅ Token salvato in: {token_path}")
    print(f"   refresh_token: {credentials.refresh_token[:20]}...")
    print("   Ora puoi usare i servizi Google Workspace!")

    # Test connessione
    print("\n📋 Test connessione Google Drive...")
    try:
        from googleapiclient.discovery import build

        service = build("drive", "v3", credentials=credentials)
        results = service.files().list(pageSize=5, fields="files(name)").execute()
        files = results.get("files", [])
        print(f"   ✅ Connessione OK - {len(files)} file trovati")
        for f in files[:3]:
            print(f"      - {f['name']}")
    except Exception as e:
        print(f"   ⚠️  Test fallito: {e}")


if __name__ == "__main__":
    main()
