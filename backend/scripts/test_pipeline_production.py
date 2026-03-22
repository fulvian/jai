#!/usr/bin/env python3
"""
Test Pipeline Produzione Completa.

Testa l'intero ciclo cognitivo:
1. Query utente in linguaggio naturale
2. LLM Orchestrator (LangGraph) decide il routing
3. Retrieval (LightRAG + Qdrant + KuzuDB)
4. Tool Selection & Execution (se applicabile)
5. Response Generation (NanoGPT)

Requisiti:
- Server Me4BrAIn in esecuzione (http://localhost:8089)
- Configurazione JWT o API Key valida
- NanoGPT API key configurata in .env

Usage:
    # Con autenticazione API Key (dev mode)
    python scripts/test_pipeline_production.py "dimmi il prezzo del bitcoin"

    # Modalità debug
    python scripts/test_pipeline_production.py -v "che tempo fa a Milano?"
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import httpx


API_BASE = os.environ.get("ME4BRAIN_API_URL", "http://localhost:8089")


async def get_auth_headers() -> dict[str, str]:
    """Ottiene headers di autenticazione.

    In produzione useremo JWT. Per dev, usiamo API Key o bypass.
    """
    # Prova API Key se configurata
    api_key = os.environ.get("ME4BRAIN_API_KEY")
    if api_key:
        return {"X-API-Key": api_key}

    # Altrimenti, prova a ottenere un token JWT di test
    # Questo richiede Keycloak configurato
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Endpoint di health check per verificare configurazione
            response = await client.get(f"{API_BASE}/health")
            if response.status_code == 200:
                # In dev mode, potremmo bypassare auth
                return {"X-Tenant-ID": "me4brain_core", "X-User-ID": "test_user"}
    except Exception:
        pass

    return {"X-Tenant-ID": "me4brain_core", "X-User-ID": "test_user"}


async def run_cognitive_query(
    query: str,
    session_id: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Esegue una query attraverso il ciclo cognitivo completo.

    Args:
        query: Query in linguaggio naturale
        session_id: ID sessione per continuità (opzionale)
        verbose: Se True, stampa dettagli intermedi

    Returns:
        Risposta del sistema cognitivo
    """
    headers = await get_auth_headers()
    headers["Content-Type"] = "application/json"

    if verbose:
        print(f'\n🔍 Query: "{query}"')
        print("=" * 60)
        print(f"📡 Endpoint: {API_BASE}/v1/memory/query")
        print(f"🔐 Auth: {list(headers.keys())}")
        print()

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                f"{API_BASE}/v1/memory/query",
                headers=headers,
                json={
                    "query": query,
                    "session_id": session_id,
                    "max_iterations": 5,
                },
            )

            if response.status_code == 401:
                # Auth fallito - prova endpoint tools come fallback
                if verbose:
                    print("⚠️  Auth richiesta. Provo fallback su /v1/tools/search...")
                return await _fallback_tools_query(query, verbose)

            if response.status_code == 422:
                error_detail = response.json()
                return {"error": f"Validation error: {error_detail}"}

            response.raise_for_status()
            result = response.json()

            if verbose:
                print("✅ RISPOSTA COGNITIVA:")
                print("-" * 40)
                print(f"📝 {result.get('response', 'N/A')}")
                print()
                print(f"🎯 Confidence: {result.get('confidence', 0):.2f}")
                print(f"📚 Sources: {result.get('sources', [])}")
                print(f"🧵 Thread ID: {result.get('thread_id', 'N/A')[:8]}...")

            return result

        except httpx.HTTPStatusError as e:
            if verbose:
                print(f"❌ HTTP Error: {e.response.status_code}")
                print(f"   Detail: {e.response.text[:200]}")
            return {"error": str(e), "status_code": e.response.status_code}
        except Exception as e:
            if verbose:
                print(f"❌ Error: {e}")
            return {"error": str(e)}


async def _fallback_tools_query(query: str, verbose: bool = False) -> dict[str, Any]:
    """Fallback: usa direttamente l'API Tools senza auth.

    Questo bypassa il ciclo cognitivo ma permette di testare
    la ricerca e esecuzione dei tool.
    """
    if verbose:
        print("\n🔄 FALLBACK: Pipeline Tools Diretta")
        print("-" * 40)

    # Import handler dal nostro script E2E
    from test_tools_e2e import run_query

    result = await run_query(query, verbose=verbose)
    return {"fallback": True, **result}


async def interactive_mode():
    """Modalità interattiva REPL."""
    print("🧠 Me4BrAIn Cognitive Pipeline - Interactive Mode")
    print("=" * 60)
    print("Digita le tue query. Usa 'exit' per uscire.")
    print("Usa 'session <id>' per impostare una sessione.")
    print()

    session_id = None

    while True:
        try:
            user_input = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nArrivederci!")
            break

        if not user_input:
            continue

        if user_input.lower() == "exit":
            print("Arrivederci!")
            break

        if user_input.lower().startswith("session "):
            session_id = user_input.split(" ", 1)[1]
            print(f"📌 Session ID impostato: {session_id}")
            continue

        result = await run_cognitive_query(user_input, session_id, verbose=True)
        print()


async def main():
    parser = argparse.ArgumentParser(
        description="Test della Pipeline Cognitiva di Produzione",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  # Query singola
  python scripts/test_pipeline_production.py "dimmi il prezzo del bitcoin"
  
  # Query con dettagli
  python scripts/test_pipeline_production.py -v "che tempo fa a Roma?"
  
  # Modalità interattiva
  python scripts/test_pipeline_production.py -i
  
  # Output JSON
  python scripts/test_pipeline_production.py -q "bitcoin price"
        """,
    )
    parser.add_argument("query", nargs="?", help="Query in linguaggio naturale")
    parser.add_argument("-v", "--verbose", action="store_true", help="Output dettagliato")
    parser.add_argument("-q", "--quiet", action="store_true", help="Solo output JSON")
    parser.add_argument("-i", "--interactive", action="store_true", help="Modalità interattiva")
    parser.add_argument("-s", "--session", help="Session ID per continuità")

    args = parser.parse_args()

    if args.interactive:
        await interactive_mode()
        return

    if not args.query:
        parser.print_help()
        sys.exit(1)

    result = await run_cognitive_query(
        args.query,
        session_id=args.session,
        verbose=args.verbose and not args.quiet,
    )

    if args.quiet:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif not args.verbose:
        # Output semplice
        if "error" in result:
            print(f"❌ Error: {result['error']}")
        elif result.get("fallback"):
            print(f"📝 {result.get('result', result)}")
        else:
            print(f"📝 {result.get('response', 'No response')}")


if __name__ == "__main__":
    asyncio.run(main())
