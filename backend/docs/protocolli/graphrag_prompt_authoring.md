# Protocollo Ufficiale GraphRAG: Authoring Prompt Hints & Few-Shots (SOTA 2026)

Questo documento definisce gli standard tecnici e qualitativi per il popolamento dei metadati del sistema GraphRAG di PersAn / me4brain. Seguire rigorosamente queste linee guida per garantire la massima precisione degli LLM e ridurre le allucinazioni nel loop iterativo.

---

## 1. Architettura dei Metadati a 3 Layer

Il sistema opera su tre livelli di iniezione dinamica del contesto:

| Layer       | Nome                  | Scopo                                                                                   | Destinazione Neo4j                        |
| ----------- | --------------------- | --------------------------------------------------------------------------------------- | ----------------------------------------- |
| **Layer 1** | **Domain Hints**      | Regole comportamentali e contesto globale per un intero dominio (es. Google Workspace). | `DomainTemplate.content`                  |
| **Layer 2** | **Tool Constraints**  | Regole ferree, schemi di input (JSON Schema) e vincoli operativi per singolo tool.      | `ToolTemplate.constraints` + `hard_rules` |
| **Layer 3** | **Few-Shot Examples** | Esempi concreti `INPUT -> CALL -> OUTPUT` recuperati via similarità vettoriale.         | `FewShotExample` nodes                    |

---

## 2. Organizzazione e Naming Convention

Tutti i file sorgente devono essere salvati in:
`config/prompt_hints/domains/{domain_id}.yaml`

- **Nomi file**: Solo minuscole e underscore (es. `finance_crypto.yaml`).
- **Override Manuale**: I file in `domains/` hanno la precedenza sui file generati automaticamente in `auto_generated/`. **Non modificare mai** i file in `auto_generated/`.

---

## 3. Standard Strutturale YAML (SOTA 2026)

Ogni file dominio deve seguire questo schema:

```yaml
version: "2.0"                      # Versione protocollare SOTA 2026
domain: "nome_dominio"              # Deve coincidere col nome del file
last_updated: "YYYY-MM-DD"
author: "nome_autore"

description: |
  Breve spiegazione (50-100 caratteri) di cosa fa il dominio e per chi è pensato.

content: |
  ## REGOLE CRITICHE LLM
  - Istruzioni imperative (es: "Usa sempre RFC3339 per le date").
  - Strategie di sequenziamento tool (es: "Prima cerca, poi leggi i dettagli").
  - Identificazione di anti-pattern ("NON allucinare mai email_id").

tools:
  nome_tool_identificativo:
    description: "Cosa fa il tool in questo specifico contesto di dominio."
    constraints:
      max_results: 50
      input_schema:
        type: object
        required: ["param"]
        properties:
          param: { type: "string", description: "Dettaglio..." }
    hard_rules: |
      RULE 1: Se il parametro X è > 100, rifiuta la chiamata.
      RULE 2: Le date devono essere future.
    few_shot_examples:
      - description: "Caso d'uso comune A"
        content: |
          USER: ...
          THOUGHT: ...
          CALL: ...
          RESULT: ...
```

---

## 4. Regole d'Oro per l'Authoring

### 4.1 Step Zero: Analisi della Codebase (MANDATORY)

Prima di scrivere una sola riga di YAML, l'autore (umano o AI) **DEVE** analizzare la codebase reale del dominio:

- **Tools**: Elencare tutti i file in `src/me4brain/domains/{domain_id}/tools/`.
- **Skills**: Verificare le logiche implementate in `src/me4brain/skills/` correlate.
- **Mapping**: Ogni tool mappato nello YAML deve corrispondere a una funzione reale esistente, con parametri e tipi (Pydantic/Type Hints) verificati.

### 4.2 Hard Rules (Layer 2)

- Devono essere scritte come **REGOLE NUMERATE** (es. `RULE 1`).
- Devono essere **TESTABILI**: non usare aggettivi vaghi come "chiaro" o "semplice".
- Devono essere specifiche del dominio (es. nel dominio medico: *"RULE 1: Non diagnosticare, suggerisci solo consulto professionale"*).

### 4.3 Few-Shot Examples (Layer 3)

- **Minimo 2 esempi** per ogni tool complesso.
- Formato richiesto: `INPUT` (Query utente) -> `CALL` (JSON della funzione) -> `RESULT` (Esempio di output atteso).
- Gli esempi servono a istruire il modello sulla *struttura* dei parametri, specialmente per date, filtri e ID complessi.

### 4.4 Versionamento e Deprecazione

- Usare `version` (semver) per ogni tool.
- Se un tool diventa obsoleto, impostare `deprecated: true` e fornire un `migration_hint` ("Usa il tool X v2").

---

## 5. Checklist di Validazione Finale

Prima di effettuare il commit di un file YAML:
- [ ] È stata eseguita l'analisi preliminare della codebase reale (Step Zero).
- [ ] Il file passa la validazione sintattica (`yaml.safe_load`).
- [ ] Tutti i tool citati esistono effettivamente nella codebase e i parametri sono mappati correttamente.
- [ ] Le `hard_rules` non sono in contraddizione tra loro.
- [ ] Gli esempi few-shot mostrano chiamate JSON valide nel formato Pydantic.
- [ ] La data `last_updated` è quella odierna.
