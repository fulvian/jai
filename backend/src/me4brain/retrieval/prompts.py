"""Prompts per LightRAG.

Contiene i template per:
1. Estrazione di entità e relazioni (Triplettes)
2. Generazione di risposte Local/Global/Hybrid
"""

ENTITY_EXTRACTION_PROMPT = """
Sei un esperto di analisi linguistica e grafi di conoscenza.
Il tuo compito è estrarre ENTITÀ e RELAZIONI dal testo fornito per costruire un grafo strutturato.

ISTRUZIONI:
1. Identifica le entità chiave (Persone, Luoghi, Organizzazioni, Concetti, Eventi, Tool, etc.).
2. Identifica le relazioni tra queste entità.
3. Restituisci il risultato STRETTAMENTE in formato JSON con la seguente struttura:
{{
  "entities": [
    {{"id": "ID_UNICO", "name": "Nome", "type": "Tipo", "description": "Breve descrizione"}},
    ...
  ],
  "relations": [
    {{"source": "ID_UNICO_SORGENTE", "target": "ID_UNICO_TARGET", "type": "TIPO_RELAZIONE", "description": "Perché sono collegate", "weight": 0.1-1.0}},
    ...
  ]
}}

REGOLE:
- Gli ID devono essere in snake_case e basati sul nome dell'entità.
- Se un'entità è già nota (es. Me4BrAIn), usa lo stesso ID.
- Sii conciso nelle descrizioni.

TESTO DA ANALIZZARE:
{text}
"""

LOCAL_QUERY_PROMPT = """
Sei un assistente intelligente che risponde a domande basandosi su un contesto specifico estratto da una memoria episodica.
Rispondi alla DOMANDA dell'utente usando SOLO le INFORMAZIONI fornite nel CONTESTO LOCAL.

DOMANDA: {query}

CONTESTO LOCAL (Fatti specifici ed episodi):
{context}

Se le informazioni non sono sufficienti, indicalo chiaramente.
"""

GLOBAL_QUERY_PROMPT = """
Sei un assistente intelligente che risponde a domande basandosi su una visione globale e strutturata della conoscenza.
Il contesto fornito rappresenta "cluster" di conoscenza e relazioni consolidate.

DOMANDA: {query}

CONTESTO GLOBAL (Knowledge Graph & Temi):
{context}

Sintetizza una risposta che spieghi le relazioni generali e i temi principali emersi.
"""

HYBRID_QUERY_PROMPT = """
Sei un assistente intelligente avanzato. Devi unire fatti specifici (Local) con la visione d'insieme del grafo (Global).

DOMANDA: {query}

CONTESTO UNIFICATO (Local + Global):
{context}

Fornisci una risposta completa che parta dai dettagli specifici per arrivare alle conclusioni generali.
"""
