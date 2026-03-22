#!/usr/bin/env python3
"""Setup Test Data per Google Workspace E2E Tests.

Crea una cartella _me4brain_e2e_test su Google Drive con file fittizi
per testare i tool Google Workspace.
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import tempfile

# Token path - come definito in .env
SCRIPT_DIR = Path(__file__).parent.parent
TOKEN_PATH = SCRIPT_DIR / "data" / "google_token.json"


def get_credentials():
    """Carica credenziali Google."""
    if not os.path.exists(TOKEN_PATH):
        raise FileNotFoundError(f"Token non trovato: {TOKEN_PATH}")

    with open(TOKEN_PATH) as f:
        token_data = json.load(f)

    return Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
    )


def setup_test_data():
    """Crea cartella e file di test su Google Drive."""
    creds = get_credentials()

    # Build services
    drive = build("drive", "v3", credentials=creds)
    docs = build("docs", "v1", credentials=creds)
    sheets = build("sheets", "v4", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)

    print("🚀 Setup Test Data per Me4BrAIn E2E")
    print("=" * 50)

    # 1. Crea cartella test (o trova esistente)
    folder_name = "_me4brain_e2e_test"
    folder_query = (
        f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    )
    results = drive.files().list(q=folder_query, fields="files(id, name)").execute()

    if results.get("files"):
        folder_id = results["files"][0]["id"]
        print(f"📁 Cartella esistente trovata: {folder_id}")
    else:
        folder_metadata = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
        folder = drive.files().create(body=folder_metadata, fields="id").execute()
        folder_id = folder["id"]
        print(f"📁 Cartella creata: {folder_id}")

    # 2. Crea Google Doc: "Report Budget Q1 2026"
    doc_metadata = {
        "name": "Report Budget Q1 2026",
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id],
    }
    doc = drive.files().create(body=doc_metadata, fields="id").execute()
    doc_id = doc["id"]

    # Aggiungi contenuto al documento
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": """Report Budget Q1 2026

Riepilogo Finanziario
--------------------
Ricavi totali: €1,250,000
Costi operativi: €890,000
Utile netto: €360,000

Dettaglio per dipartimento:
- Engineering: €450,000
- Marketing: €200,000
- Operations: €240,000

Note: Budget approvato dal CDA in data 15 Gennaio 2026.
""",
                    }
                }
            ]
        },
    ).execute()
    print(f"📄 Doc creato: Report Budget Q1 2026 ({doc_id})")

    # 3. Crea Google Sheet: "Vendite 2026"
    sheet_metadata = {
        "name": "Vendite 2026",
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "parents": [folder_id],
    }
    sheet = drive.files().create(body=sheet_metadata, fields="id").execute()
    sheet_id = sheet["id"]

    # Aggiungi dati allo spreadsheet
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="A1:D5",
        valueInputOption="RAW",
        body={
            "values": [
                ["Mese", "Ricavi", "Costi", "Profitto"],
                ["Gennaio", "320000", "180000", "140000"],
                ["Febbraio", "350000", "190000", "160000"],
                ["Marzo", "380000", "200000", "180000"],
                ["Aprile", "400000", "210000", "190000"],
            ]
        },
    ).execute()
    print(f"📊 Sheet creato: Vendite 2026 ({sheet_id})")

    # 4. Crea documento: "Meeting Notes Team"
    notes_metadata = {
        "name": "Meeting Notes Team",
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id],
    }
    notes = drive.files().create(body=notes_metadata, fields="id").execute()
    notes_id = notes["id"]

    docs.documents().batchUpdate(
        documentId=notes_id,
        body={
            "requests": [
                {
                    "insertText": {
                        "location": {"index": 1},
                        "text": """Meeting Notes - Team Standup

Data: 31 Gennaio 2026
Partecipanti: Mario, Giulia, Alessandro

Agenda:
1. Review sprint corrente
2. Planning Q2
3. Discussione nuove funzionalità

Azioni:
- Mario: completare integrazione API entro venerdì
- Giulia: preparare mockup nuova dashboard
- Alessandro: review security code

Prossimo meeting: Lunedì 3 Febbraio ore 10:00
""",
                    }
                }
            ]
        },
    ).execute()
    print(f"📝 Doc creato: Meeting Notes Team ({notes_id})")

    # 5. Crea evento calendario per domani
    tomorrow = datetime.now() + timedelta(days=1)
    event = {
        "summary": "Riunione Test Me4BrAIn",
        "description": "Evento di test per E2E testing",
        "start": {
            "dateTime": tomorrow.replace(hour=15, minute=0).isoformat(),
            "timeZone": "Europe/Rome",
        },
        "end": {
            "dateTime": tomorrow.replace(hour=16, minute=0).isoformat(),
            "timeZone": "Europe/Rome",
        },
    }
    event_result = calendar.events().insert(calendarId="primary", body=event).execute()
    print(f"📅 Evento creato: Riunione Test Me4BrAIn ({event_result['id']})")

    print("\n" + "=" * 50)
    print("✅ Setup completato!")
    print(f"\n📁 Cartella test: {folder_name}")
    print("   Contenuto:")
    print("   - Report Budget Q1 2026 (Google Doc)")
    print("   - Vendite 2026 (Google Sheet)")
    print("   - Meeting Notes Team (Google Doc)")
    print("   - Riunione Test Me4BrAIn (Calendar Event)")

    return {
        "folder_id": folder_id,
        "doc_id": doc_id,
        "sheet_id": sheet_id,
        "notes_id": notes_id,
        "event_id": event_result["id"],
    }


if __name__ == "__main__":
    try:
        result = setup_test_data()
        print(f"\n🔑 IDs per riferimento:")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"❌ Errore: {e}")
        raise
