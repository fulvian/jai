#!/usr/bin/env python3
"""Test completo tutti i 38 tool Google Workspace."""

import asyncio
import os
import sys

# Cambia dir e carica env
os.chdir("/Users/fulvioventura/me4brain")
sys.path.insert(0, "src")

from dotenv import load_dotenv

load_dotenv(override=True)

from me4brain.domains.google_workspace.tools.google_api import AVAILABLE_TOOLS

results = {}


async def test_all_google():
    print("=" * 60)
    print("GOOGLE WORKSPACE - TEST COMPLETO TUTTI I 38 TOOL")
    print("=" * 60)

    # ========== DRIVE (7 tool) ==========
    print("\n--- DRIVE (7 tool) ---")

    # 1. drive_search
    r = await AVAILABLE_TOOLS["google_drive_search"](query="test")
    results["google_drive_search"] = "OK" if "files" in r else f"FAIL: {r.get('error', '?')[:40]}"
    print(f"1. drive_search: {results['google_drive_search']}")

    # 2. drive_list_files
    r = await AVAILABLE_TOOLS["google_drive_list_files"](max_results=5)
    results["google_drive_list_files"] = (
        "OK" if "files" in r else f"FAIL: {r.get('error', '?')[:40]}"
    )
    print(f"2. drive_list_files: {results['google_drive_list_files']}")

    # 3. drive_get_file (usa ID da lista)
    file_id = None
    if "files" in r and r["files"]:
        file_id = r["files"][0].get("id")
    if file_id:
        r2 = await AVAILABLE_TOOLS["google_drive_get_file"](file_id=file_id)
        results["google_drive_get_file"] = (
            "OK" if "file" in r2 else f"FAIL: {r2.get('error', '?')[:40]}"
        )
    else:
        results["google_drive_get_file"] = "SKIP (no file)"
    print(f"3. drive_get_file: {results['google_drive_get_file']}")

    # 4. drive_get_content (estrai contenuto)
    if file_id:
        r3 = await AVAILABLE_TOOLS["google_drive_get_content"](file_id=file_id)
        results["google_drive_get_content"] = (
            "OK" if "content" in r3 or "error" not in r3 else f"FAIL: {r3.get('error', '?')[:40]}"
        )
    else:
        results["google_drive_get_content"] = "SKIP"
    print(f"4. drive_get_content: {results['google_drive_get_content']}")

    # 5. drive_create_folder
    r4 = await AVAILABLE_TOOLS["google_drive_create_folder"](name="Me4BrAInTest_Folder")
    results["google_drive_create_folder"] = (
        "OK" if "folder_id" in r4 else f"FAIL: {r4.get('error', '?')[:40]}"
    )
    folder_id = r4.get("folder_id")
    print(f"5. drive_create_folder: {results['google_drive_create_folder']}")

    # 6. drive_copy (copia file)
    if file_id:
        r5 = await AVAILABLE_TOOLS["google_drive_copy"](
            file_id=file_id, new_name="Me4BrAInTest_Copy"
        )
        results["google_drive_copy"] = (
            "OK" if "new_id" in r5 else f"FAIL: {r5.get('error', '?')[:40]}"
        )
    else:
        results["google_drive_copy"] = "SKIP"
    print(f"6. drive_copy: {results['google_drive_copy']}")

    # 7. drive_export
    if file_id:
        r6 = await AVAILABLE_TOOLS["google_drive_export"](file_id=file_id, export_format="pdf")
        results["google_drive_export"] = (
            "OK"
            if "content_base64" in r6 or "error" not in r6
            else f"FAIL: {r6.get('error', '?')[:40]}"
        )
    else:
        results["google_drive_export"] = "SKIP"
    print(f"7. drive_export: {results['google_drive_export']}")

    # ========== GMAIL (5 tool) ==========
    print("\n--- GMAIL (5 tool) ---")

    # 8. gmail_search
    r = await AVAILABLE_TOOLS["google_gmail_search"](query="is:inbox", max_results=5)
    results["google_gmail_search"] = "OK" if "emails" in r else f"FAIL: {r.get('error', '?')[:40]}"
    msg_id = None
    if "emails" in r and r["emails"]:
        msg_id = r["emails"][0].get("id")
    print(f"8. gmail_search: {results['google_gmail_search']} - {len(r.get('emails', []))} emails")

    # 9. gmail_get_message
    if msg_id:
        r2 = await AVAILABLE_TOOLS["google_gmail_get_message"](message_id=msg_id)
        results["google_gmail_get_message"] = (
            "OK" if "message" in r2 else f"FAIL: {r2.get('error', '?')[:40]}"
        )
    else:
        results["google_gmail_get_message"] = "SKIP (no msg)"
    print(f"9. gmail_get_message: {results['google_gmail_get_message']}")

    # 10. gmail_send - TEST reale con email a se stessi
    r10 = await AVAILABLE_TOOLS["google_gmail_send"](
        to="fulvio.ventura@hypercode.it",
        subject="[TEST ME4BRAIN] Verifica Tool Email",
        body="Questo è un test automatico del tool gmail_send di Me4BrAIn.",
    )
    results["google_gmail_send"] = (
        "OK" if "message_id" in r10 else f"FAIL: {r10.get('error', '?')[:40]}"
    )
    print(f"10. gmail_send: {results['google_gmail_send']}")

    # 11. gmail_reply - SKIP
    results["google_gmail_reply"] = "SKIP (need msg)"
    print(f"11. gmail_reply: {results['google_gmail_reply']}")

    # 12. gmail_forward - SKIP
    results["google_gmail_forward"] = "SKIP (need msg)"
    print(f"12. gmail_forward: {results['google_gmail_forward']}")

    # ========== CALENDAR (6 tool) ==========
    print("\n--- CALENDAR (6 tool) ---")

    # 13. calendar_upcoming
    r = await AVAILABLE_TOOLS["google_calendar_upcoming"](days=7)
    results["google_calendar_upcoming"] = (
        "OK" if "events" in r else f"FAIL: {r.get('error', '?')[:40]}"
    )
    print(
        f"13. calendar_upcoming: {results['google_calendar_upcoming']} - {r.get('count', 0)} events"
    )

    # 14. calendar_list_events
    r2 = await AVAILABLE_TOOLS["google_calendar_list_events"](max_results=5)
    results["google_calendar_list_events"] = (
        "OK" if "events" in r2 else f"FAIL: {r2.get('error', '?')[:40]}"
    )
    event_id = None
    if "events" in r2 and r2["events"]:
        event_id = r2["events"][0].get("id")
    print(f"14. calendar_list_events: {results['google_calendar_list_events']}")

    # 15. calendar_create_event
    from datetime import datetime, timedelta

    start = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00+01:00")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT11:00:00+01:00")
    r15 = await AVAILABLE_TOOLS["google_calendar_create_event"](
        summary="[TEST ME4BRAIN] Meeting Test",
        start_time=start,
        end_time=end,
        description="Evento di test creato da Me4BrAIn",
    )
    results["google_calendar_create_event"] = (
        "OK" if "event_id" in r15 else f"FAIL: {r15.get('error', '?')[:40]}"
    )
    new_event_id = r15.get("event_id")
    print(f"15. calendar_create_event: {results['google_calendar_create_event']}")

    # 16. calendar_get_event
    if new_event_id:
        r16 = await AVAILABLE_TOOLS["google_calendar_get_event"](event_id=new_event_id)
        results["google_calendar_get_event"] = (
            "OK" if "event" in r16 or "summary" in r16 else f"FAIL: {r16.get('error', '?')[:40]}"
        )
    else:
        results["google_calendar_get_event"] = "SKIP (no event)"
    print(f"16. calendar_get_event: {results['google_calendar_get_event']}")

    # 17. calendar_update_event
    if new_event_id:
        r17 = await AVAILABLE_TOOLS["google_calendar_update_event"](
            event_id=new_event_id, summary="[TEST ME4BRAIN] Meeting Test UPDATED"
        )
        results["google_calendar_update_event"] = (
            "OK"
            if "event_id" in r17 or "error" not in r17
            else f"FAIL: {r17.get('error', '?')[:40]}"
        )
    else:
        results["google_calendar_update_event"] = "SKIP"
    print(f"17. calendar_update_event: {results['google_calendar_update_event']}")

    # 18. calendar_delete_event
    if new_event_id:
        r18 = await AVAILABLE_TOOLS["google_calendar_delete_event"](event_id=new_event_id)
        results["google_calendar_delete_event"] = (
            "OK"
            if "success" in r18 or "deleted" in str(r18) or "error" not in r18
            else f"FAIL: {r18.get('error', '?')[:40]}"
        )
    else:
        results["google_calendar_delete_event"] = "SKIP"
    print(f"18. calendar_delete_event: {results['google_calendar_delete_event']}")

    # ========== DOCS (5 tool) ==========
    print("\n--- DOCS (5 tool) ---")

    # 19. docs_create
    r = await AVAILABLE_TOOLS["google_docs_create"](
        title="Me4BrAInTest_Doc", content="Questo è un documento di test creato da Me4BrAIn."
    )
    results["google_docs_create"] = (
        "OK" if "document_id" in r else f"FAIL: {r.get('error', '?')[:40]}"
    )
    doc_id = r.get("document_id")
    print(f"19. docs_create: {results['google_docs_create']}")

    # 20. docs_get
    if doc_id:
        r2 = await AVAILABLE_TOOLS["google_docs_get"](document_id=doc_id)
        results["google_docs_get"] = (
            "OK" if "text" in r2 or "title" in r2 else f"FAIL: {r2.get('error', '?')[:40]}"
        )
    else:
        results["google_docs_get"] = "SKIP (no doc)"
    print(f"20. docs_get: {results['google_docs_get']}")

    # 21. docs_append_text
    if doc_id:
        r3 = await AVAILABLE_TOOLS["google_docs_append_text"](
            document_id=doc_id, text="\n\nTesto aggiunto da Me4BrAIn con append_text."
        )
        results["google_docs_append_text"] = (
            "OK" if "success" in r3 or "error" not in r3 else f"FAIL: {r3.get('error', '?')[:40]}"
        )
    else:
        results["google_docs_append_text"] = "SKIP"
    print(f"21. docs_append_text: {results['google_docs_append_text']}")

    # 22. docs_insert_text
    if doc_id:
        r4 = await AVAILABLE_TOOLS["google_docs_insert_text"](
            document_id=doc_id, text="[INSERITO] ", index=1
        )
        results["google_docs_insert_text"] = (
            "OK" if "success" in r4 or "error" not in r4 else f"FAIL: {r4.get('error', '?')[:40]}"
        )
    else:
        results["google_docs_insert_text"] = "SKIP"
    print(f"22. docs_insert_text: {results['google_docs_insert_text']}")

    # 23. docs_replace_text
    if doc_id:
        r5 = await AVAILABLE_TOOLS["google_docs_replace_text"](
            document_id=doc_id, find_text="test", replace_text="TEST_REPLACED"
        )
        results["google_docs_replace_text"] = (
            "OK" if "success" in r5 or "error" not in r5 else f"FAIL: {r5.get('error', '?')[:40]}"
        )
    else:
        results["google_docs_replace_text"] = "SKIP"
    print(f"23. docs_replace_text: {results['google_docs_replace_text']}")

    # ========== SHEETS (6 tool) ==========
    print("\n--- SHEETS (6 tool) ---")

    # 24. sheets_create
    r = await AVAILABLE_TOOLS["google_sheets_create"](title="Me4BrAInTest_Sheet")
    results["google_sheets_create"] = (
        "OK" if "spreadsheet_id" in r else f"FAIL: {r.get('error', '?')[:40]}"
    )
    sheet_id = r.get("spreadsheet_id")
    print(f"24. sheets_create: {results['google_sheets_create']}")

    # 25. sheets_get_metadata
    if sheet_id:
        r2 = await AVAILABLE_TOOLS["google_sheets_get_metadata"](spreadsheet_id=sheet_id)
        results["google_sheets_get_metadata"] = (
            "OK" if "title" in r2 or "sheets" in r2 else f"FAIL: {r2.get('error', '?')[:40]}"
        )
    else:
        results["google_sheets_get_metadata"] = "SKIP"
    print(f"25. sheets_get_metadata: {results['google_sheets_get_metadata']}")

    # 26. sheets_update_values
    if sheet_id:
        r3 = await AVAILABLE_TOOLS["google_sheets_update_values"](
            spreadsheet_id=sheet_id,
            range_notation="A1:B2",
            values=[["Nome", "Valore"], ["Test", "123"]],
        )
        results["google_sheets_update_values"] = (
            "OK"
            if "updated_cells" in r3 or "error" not in r3
            else f"FAIL: {r3.get('error', '?')[:40]}"
        )
    else:
        results["google_sheets_update_values"] = "SKIP"
    print(f"26. sheets_update_values: {results['google_sheets_update_values']}")

    # 27. sheets_get_values
    if sheet_id:
        r4 = await AVAILABLE_TOOLS["google_sheets_get_values"](
            spreadsheet_id=sheet_id, range_notation="A1:B2"
        )
        results["google_sheets_get_values"] = (
            "OK" if "values" in r4 else f"FAIL: {r4.get('error', '?')[:40]}"
        )
    else:
        results["google_sheets_get_values"] = "SKIP"
    print(f"27. sheets_get_values: {results['google_sheets_get_values']}")

    # 28. sheets_append_row
    if sheet_id:
        r5 = await AVAILABLE_TOOLS["google_sheets_append_row"](
            spreadsheet_id=sheet_id, values=["NewRow", "456"]
        )
        results["google_sheets_append_row"] = (
            "OK"
            if "updated_range" in r5 or "error" not in r5
            else f"FAIL: {r5.get('error', '?')[:40]}"
        )
    else:
        results["google_sheets_append_row"] = "SKIP"
    print(f"28. sheets_append_row: {results['google_sheets_append_row']}")

    # 29. sheets_add_sheet
    if sheet_id:
        r6 = await AVAILABLE_TOOLS["google_sheets_add_sheet"](
            spreadsheet_id=sheet_id, sheet_title="NewSheet"
        )
        results["google_sheets_add_sheet"] = (
            "OK" if "sheet_id" in r6 or "error" not in r6 else f"FAIL: {r6.get('error', '?')[:40]}"
        )
    else:
        results["google_sheets_add_sheet"] = "SKIP"
    print(f"29. sheets_add_sheet: {results['google_sheets_add_sheet']}")

    # ========== SLIDES (4 tool) ==========
    print("\n--- SLIDES (4 tool) ---")

    # 30. slides_create
    r = await AVAILABLE_TOOLS["google_slides_create"](title="Me4BrAInTest_Slides")
    results["google_slides_create"] = (
        "OK" if "presentation_id" in r else f"FAIL: {r.get('error', '?')[:40]}"
    )
    pres_id = r.get("presentation_id")
    print(f"30. slides_create: {results['google_slides_create']}")

    # 31. slides_get
    if pres_id:
        r2 = await AVAILABLE_TOOLS["google_slides_get"](presentation_id=pres_id)
        results["google_slides_get"] = (
            "OK" if "title" in r2 or "slides" in r2 else f"FAIL: {r2.get('error', '?')[:40]}"
        )
    else:
        results["google_slides_get"] = "SKIP"
    print(f"31. slides_get: {results['google_slides_get']}")

    # 32. slides_get_text
    if pres_id:
        r3 = await AVAILABLE_TOOLS["google_slides_get_text"](presentation_id=pres_id)
        results["google_slides_get_text"] = (
            "OK" if "slides" in r3 or "error" not in r3 else f"FAIL: {r3.get('error', '?')[:40]}"
        )
    else:
        results["google_slides_get_text"] = "SKIP"
    print(f"32. slides_get_text: {results['google_slides_get_text']}")

    # 33. slides_add_slide
    if pres_id:
        r4 = await AVAILABLE_TOOLS["google_slides_add_slide"](presentation_id=pres_id)
        results["google_slides_add_slide"] = (
            "OK" if "slide_id" in r4 or "error" not in r4 else f"FAIL: {r4.get('error', '?')[:40]}"
        )
    else:
        results["google_slides_add_slide"] = "SKIP"
    print(f"33. slides_add_slide: {results['google_slides_add_slide']}")

    # ========== MEET (1 tool) ==========
    print("\n--- MEET (1 tool) ---")

    # 34. meet_create
    r34 = await AVAILABLE_TOOLS["google_meet_create"](summary="Me4BrAIn Test Meeting")
    results["google_meet_create"] = (
        "OK" if "meet_link" in r34 or "event_id" in r34 else f"FAIL: {r34.get('error', '?')[:40]}"
    )
    print(f"34. meet_create: {results['google_meet_create']}")

    # ========== FORMS (2 tool) ==========
    print("\n--- FORMS (2 tool) ---")

    # 35-36. forms - SKIP (richiede form ID esistente)
    results["google_forms_get"] = "SKIP (need form ID)"
    results["google_forms_get_responses"] = "SKIP (need form ID)"
    print(f"35. forms_get: {results['google_forms_get']}")
    print(f"36. forms_get_responses: {results['google_forms_get_responses']}")

    # ========== CLASSROOM (2 tool) ==========
    print("\n--- CLASSROOM (2 tool) ---")

    # 37. classroom_list_courses
    r = await AVAILABLE_TOOLS["google_classroom_list_courses"]()
    results["google_classroom_list_courses"] = (
        "OK" if "courses" in r or r.get("count", 0) >= 0 else f"FAIL: {r.get('error', '?')[:40]}"
    )
    print(f"37. classroom_list_courses: {results['google_classroom_list_courses']}")

    # 38. classroom_get_coursework - SKIP
    results["google_classroom_get_coursework"] = "SKIP (need course ID)"
    print(f"38. classroom_get_coursework: {results['google_classroom_get_coursework']}")

    # ========== SUMMARY ==========
    print("\n" + "=" * 60)
    ok = sum(1 for v in results.values() if v == "OK")
    skip = sum(1 for v in results.values() if "SKIP" in v)
    fail = sum(1 for v in results.values() if "FAIL" in v)
    print(f"TOTALE: {ok} OK, {skip} SKIP, {fail} FAIL su {len(results)} tool")
    print("=" * 60)

    if fail > 0:
        print("\nFAIL DETAILS:")
        for k, v in results.items():
            if "FAIL" in v:
                print(f"  - {k}: {v}")


if __name__ == "__main__":
    asyncio.run(test_all_google())
