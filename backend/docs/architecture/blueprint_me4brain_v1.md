Ecco il **Blueprint Architetturale Definitivo (v2.0)** per il sistema **Me4BrAIn Core**.

Questo documento è stato completamente riscritto per approfondire verticalmente ogni layer cognitivo, integrando le specifiche del framework *Texgravec* e le logiche di *Think-on-Graph 2.0 (ToG-2)*, *HippoRAG* e *Mem0*. Inoltre, l'architettura è stata elevata a **Piattaforma API-First Multi-Tenant**, progettata non come un singolo agente, ma come un "Sistema Operativo Cognitivo" centrale che serve molteplici applicazioni client esterne.

---

# **BLUEPRINT DI FONDAZIONE: ME4BRAIN CORE**

**Piattaforma Universale di Memoria Agentica "API-First"**

## **1\. Visione Architetturale: Il "Cervello as-a-Service"**

Il sistema non è un chatbot, ma un'infrastruttura di back-end intelligente che espone capacità cognitive via API. Applicazioni esterne (CRM, Dashboard Finanziarie, Strumenti Medici, IDE) si connettono a Me4BrAIn per delegare la gestione dello stato, il ragionamento complesso e la memoria a lungo termine.

L'architettura segue il principio della **Persistenza Poliglotta Cognitiva** (ispirata a *Texgravec*), che unisce tre rappresentazioni fondamentali del dato in un unico tessuto coerente:

1. **Testo (Narrativa):** Per la fedeltà episodica e il logging.  
2. **Vettori (Associazione):** Per il recupero semantico "fuzzy" e l'analogia.  
3. **Grafo (Struttura):** Per il ragionamento logico, causale e procedurale (ToG-2/HippoRAG).

Il sistema opera in regime di **Multi-Tenancy Stretta**: ogni applicazione client e ogni utente finale possiede uno spazio di memoria isolato (Namespace), protetto da policy di sicurezza granulari (Row-Level Security).

---

## **2\. Dettaglio Profondo dei Quattro Layer Cognitivi**

Basandoci sulla tassonomia *Texgravec* e sulle neuroscienze computazionali, il sistema è diviso in quattro livelli logici, ognuno con uno stack tecnologico dedicato e meccanismi di aggiornamento specifici.

### **Livello I: Working Memory (Memoria a Breve Termine & Contesto)**

*Il "Workbench" operativo. Gestisce il `now`.*

Non è un semplice buffer di testo. È una **struttura dati attiva** che mantiene lo stato corrente dell'esecuzione e le relazioni immediate tra le entità menzionate nella sessione.

* **Funzione:** Risoluzione coreferenze ("chi è *lui*?"), gestione dell'attenzione, mantenimento dello stato dei tool.  
* **Architettura Ibrida (Redis \+ NetworkX):**  
  * **Stream Lineare (Redis):** Utilizza *Redis Streams* o Liste per mantenere il log grezzo degli ultimi $N$ turni di conversazione con latenza \<1ms.  
  * **Grafo Effimero (NetworkX):** Per ogni sessione attiva, viene istanziato in RAM un piccolo grafo dinamico. Se l'utente menziona "Progetto X" e poi "Il budget", NetworkX crea un arco temporaneo `(Progetto X)-[:HAS_CONTEXT]->(Budget)`. Questo permette all'LLM di disambiguare termini generici senza dover interrogare il database a lungo termine.  
* **Gestione "Sliding Window" Intelligente:** Non tronca brutalmente i messaggi vecchi. Un processo di background riassume i messaggi in uscita dalla finestra e li inietta nel grafo effimero come nodi di contesto sintetico, prevenendo la perdita del filo logico.

### **Livello II: Memoria Episodica (Autobiografica & Temporale)**

*Il "Diario" del sistema. Gestisce il `then`.*

Registra la storia delle interazioni, ma non come lista piatta. È un **Grafo Temporale** che collega eventi, azioni ed esiti.

* **Metodologia A-MEM (Agentic Memory):**  
  * **Note Atomiche:** Ogni interazione significativa è salvata come un nodo "Evento".  
  * **Auto-Linking:** Quando un nuovo evento viene registrato, il sistema (guidato da un LLM in background) cerca eventi passati simili e crea archi espliciti `[:CORRELATO_A]` o `[:SEGUE_A]`. Questo crea cluster narrativi auto-organizzanti.  
* **Evoluzione della Memoria:** I ricordi non sono statici. Se un nuovo fatto contraddice un ricordo episodico passato, il sistema non sovrascrive, ma aggiunge un nodo di "Revisione" collegato temporalmente, preservando la storia delle modifiche (modello bitemporale: *Event Time* vs *Ingestion Time*).  
* **Tecnologia:** **Qdrant** (per la ricerca vettoriale degli episodi) \+ **Neo4j** (per le sequenze temporali degli eventi) con metadati di timestamp rigorosi per il decadimento (Time-Decay).

### **Livello III: Memoria Semantica (Conoscenza Cristallizzata & World Model)**

*L'Enciclopedia. Gestisce il `what` e il `why`.*

È la conoscenza decontestualizzata (fatti, regole, relazioni). Qui risiede l'intelligenza del sistema.

* **Architettura Duale (Fast & Slow):**  
  * **Hot Path (LightRAG):** Per i dati nuovi e in rapido cambiamento (es. news finanziarie), utilizziamo **LightRAG**. Inserimento incrementale rapido che linearizza il grafo in vettori per un recupero immediato senza ricostruire l'intero indice.  
  * **Cold Path (GraphRAG/HippoRAG):** Per la conoscenza consolidata, utilizziamo **HippoRAG**. Sfrutta l'algoritmo *Personalized PageRank (PPR)* per "accendere" nodi distanti nel grafo. Se la query è "effetti dell'inflazione", il PPR attiva "tassi di interesse" e "mutui" anche se non menzionati, simulando l'associazione di idee umana.  
* **Knowledge Graph (KG):** Implementato su **Neo4j**. Supporta ontologie rigide per domini critici (Finanza) e schemi flessibili (OpenIE) per domini esplorativi (Medicina).

### **Livello IV: Memoria Procedurale (Skill & Muscle Memory)**

*Il "Manuale Operativo". Gestisce l'`how`.*

Spesso trascurata, è fondamentale per l'uso dei tool. Non memorizza "fatti", ma "algoritmi di comportamento".

* **Grafo delle Competenze (Skill Graph):** Ogni API o Tool disponibile al sistema è un nodo nel grafo.  
  * **Archi `[:SOLVES]`:** Collegano un problema (es. "Calcolo Tax") allo strumento (es. "Python REPL").  
  * **Pesi di Rinforzo:** Se l'agente usa un tool con successo, il peso dell'arco aumenta. Se fallisce, diminuisce. Si crea una "memoria muscolare" digitale.  
* **Few-Shot Store:** Memorizza *esempi di utilizzo* (prompt e output corretti) nel Vector Store. Quando l'agente deve usare un'API complessa, recupera dinamicamente l'esempio migliore ("Show, don't tell") invece di rileggere l'intera documentazione.  
* **Logica ToG-2 (Think-on-Graph):** Memorizza i "percorsi di ragionamento" validati. Se l'agente risolve un problema complesso multi-step, la sequenza di passaggi viene salvata come macro-operazione riutilizzabile.

---

## **3\. Il Ciclo Cognitivo: Veglia e Sonno**

Il sistema non è passivo. Vive attraverso un ciclo circadiano simulato per garantire performance e apprendimento.

### **Fase di Veglia (Online \- Response Time)**

Quando l'API riceve una richiesta (`POST /v1/chat/completions`):

1. **Semantic Router:** Analizza l'intento. È una domanda fattuale? (Attiva Livello III). È personale? (Attiva Livello II). È un task? (Attiva Livello IV).  
2. **Hybrid Retrieval:** Esegue query parallele su Qdrant (Vettori) e Neo4j (Grafo).  
3. **Reasoning (ToG-2):** L'LLM naviga i risultati. Se trova conflitti (es. Grafo dice A, Vettore dice B), attiva una routine di *Truth Discovery* basata sulla fonte più recente o autorevole.  
4. **Generazione:** Produce la risposta e la invia al client.

### **Fase di Sonno (Offline \- Consolidamento)**

Processo asincrono schedulato o triggerato da inattività:

1. **Svuotamento STM:** Prende i log da Redis (Working Memory).  
2. **Estrazione & Mining:** Un LLM "operaio" (es. GPT-4o-mini o Gemini Flash) analizza i log.  
   * Estrae nuovi fatti \-\> Aggiorna Neo4j (Livello III).  
   * Identifica nuovi episodi \-\> Crea nodi in Qdrant (Livello II).  
   * Valuta successo dei tool \-\> Aggiorna pesi nel Skill Graph (Livello IV).  
3. **Garbage Collection:** Rimuove ricordi obsoleti o ridondanti per mantenere gli indici performanti (Dimenticanza Attiva).

---

## **4\. API Gateway e Interfaccia Esterna**

Il sistema espone un'interfaccia standardizzata per le applicazioni client.

### **Endpoint Principali**

* `POST /agent/invoke`: Punto di ingresso principale. Accetta testo, immagini e contesto. Restituisce la risposta dell'agente \+ metadati (fonti usate, ragionamento).  
* `POST /memory/add`: Permette alle app esterne di iniettare memorie esplicitamente (es. "L'utente ha caricato un nuovo PDF").  
* `GET /memory/query`: Permette alle app di interrogare la memoria senza invocare l'agente (es. "Dammi tutti i fatti che sai sul progetto X").  
* `DELETE /memory/forget`: Endpoint per la conformità GDPR/Privacy ("Dimentica tutto ciò che riguarda il cliente Y").

### **Gestione Multi-Tenant**

* Ogni richiesta API deve includere un `X-Tenant-ID` e un `X-User-ID`.  
* **Segregazione Dati:**  
  * **Qdrant:** Utilizza il meccanismo di *Payload Filtering* o *Collections separate* per garantire che l'Utente A non possa cercare nei vettori dell'Utente B.  
  * **Neo4j:** Utilizza etichette (Labels) prefissate (es. `:Tenant123_Person`) o database logici separati per isolare i grafi di conoscenza.

---

## **5\. Stack Tecnologico (Specifico per M1 Pro/16GB \+ Cloud Ibrido)**

Per rispettare i vincoli hardware locali mantenendo capacità SOTA:

* **Orchestratore:** **LangGraph**. Gestisce il flusso ciclico, la persistenza dello stato e la logica di retry.  
* **Embedding Model:** **`intfloat/e5-small-v2`** (Locale). Leggero (450MB), veloce su Metal (MPS), alta precisione.  
* **Vector Database:** **Qdrant** (Docker). Efficienza Rust, ottimo per la gestione di payload complessi e filtri tenant.  
* **Graph Database:**  
  * **LTM:** **Neo4j** (Docker). Per la persistenza strutturata.  
  * **STM:** **NetworkX** (Python In-Memory). Per i grafi effimeri di sessione.  
* **LLM (Cervello):** **API Cloud** (OpenAI GPT-4o / Gemini 1.5 Flash). Delega il ragionamento pesante al cloud per risparmiare la RAM locale (16GB) per i database. Gemini Flash è ideale per il processo di "Sonno" (Consolidamento) grazie al basso costo e alta velocità.  
* **API Framework:** **FastAPI**. Per esporre gli endpoint REST al mondo esterno.

Hai perfettamente ragione. Questa è una svista critica. L'**API Store Dinamico** non è un semplice accessorio, ma il motore attuativo del sistema, quello che trasforma Me4BrAIn da un "filosofo" (che sa le cose) a un "agente" (che fa le cose). Senza di esso, il Livello IV (Procedurale) rimane teorico.

Reintegro immediatamente questo componente fondamentale nel Blueprint, definendolo non come un "magazzino", ma come un **Cortex Procedurale Evolutivo**. Ecco l'addendum architetturale che completa il sistema, progettato per essere modulare e integrarsi con lo stack definito.

---

# **6\. IL CORTEX PROCEDURALE (Dynamic API Store)**

Questa sezione defionisce il **Livello VI**, trasformandolo da una semplice libreria di prompt in un ecosistema vivo di strumenti che apprende, si adatta e si auto-ottimizza.

### **1\. Visione Architetturale: L'API Store come Grafo Probabilistico**

Dimentichiamo il concetto di "lista di plugin". Il nostro API Store è un **Grafo di Conoscenza Procedurale** ospitato su Neo4j, parallelo ma distinto dal Grafo Semantico. In questo grafo, non mappiamo solo *cosa* fanno le API, ma *quanto bene* lo fanno per specifici intenti, basandoci sull'esperienza empirica maturata dall'agente.

#### **Ontologia del Grafo Procedurale**

* **Nodi `(:Intento)`:** Concetti astratti che rappresentano il bisogno dell'utente (es. "Analisi Trend Azionario", "Recupero Paper Clinico").  
* **Nodi `(:Tool)`:** Rappresentazione dell'API specifica (es. "AlphaVantage\_TimeSeries", "PubMed\_Search"). Contiene lo schema JSON, l'endpoint e le specifiche di autenticazione.  
* **Archi `[:RISOLVE]`:** La relazione critica. Questo arco possiede proprietà dinamiche:  
  * `weight` (float 0.0-1.0): Affidabilità storica dello strumento per quell'intento.  
  * `avg_latency` (int): Tempo medio di risposta.  
  * `last_success` (timestamp): Data dell'ultimo utilizzo riuscito.

---

### **2\. Meccanismi Evolutivi e Dinamici**

Il sistema non è statico; evolve attraverso tre processi guidati da **LangGraph**:

#### **A. Ingestione "Zero-Shot" (Expansion)**

Quando viene presentata una nuova specifica API (es. un file `openapi.json` o una documentazione Swagger):

1. Un **Ingestion Agent** dedicato (basato su LLM) analizza la documentazione.  
2. **Vettorizzazione:** Crea un embedding della descrizione ("Cosa fa") e lo inserisce in **Qdrant** (collezione `tool_discovery`).  
3. **Graficizzazione:** Crea il nodo `(:Tool)` in **Neo4j**, mappando i parametri obbligatori e opzionali.  
4. **Linking Iniziale:** L'agente ipotizza a quali `(:Intento)` esistenti questo nuovo tool potrebbe servire, creando archi `[:RISOLVE]` con un peso basso (0.1 \- "esplorativo").

#### **B. Rinforzo e Penalizzazione (Selection)**

Durante l'esecuzione (fase di Veglia):

* Se l'agente usa un tool e ottiene un errore (HTTP 500, timeout, allucinazione nei parametri), il **peso dell'arco** nel grafo viene penalizzato (`weight *= 0.8`).  
* Se il tool ha successo, il peso viene incrementato (`weight += (1.0 - weight) * 0.1`).  
* **Risultato:** Nel tempo, il sistema impara organicamente che per "Prezzi Crypto" l'API *Binance* è più affidabile di *CoinGecko*, senza che un umano debba codificarlo.

#### **C. Cristallizzazione della "Muscle Memory" (Optimization)**

Quando una sequenza di utilizzo di un tool risulta particolarmente efficace (es. una query SQL complessa o un JSON annidato per un'API bancaria):

1. Il sistema cattura la coppia `(Intento Utente, Chiamata API Esatta)`.  
2. Questa coppia viene salvata in **Qdrant** come un "Few-Shot Example" ad alta priorità.  
3. **Bypass del Ragionamento:** La prossima volta che un intento simile emerge, l'agente non "ragiona" su come costruire il JSON. Recupera l'esempio cristallizzato e lo adatta (template filling). Questo riduce la latenza e il consumo di token drasticamente, simulando la formazione di abitudini automatiche nel cervello umano.

---

### **3\. Integrazione nel Flusso Operativo (LangGraph)**

Nel grafo di orchestrazione principale, il nodo `ToolSelection` non è una semplice chiamata LLM, ma un sotto-grafo decisionale:

1. **Semantic Lookup:** L'input utente viene vettorizzato. Si interroga Qdrant per trovare i Tool semanticamente compatibili.  
2. **Graph Reasoning (ToG-2):**  
   * Si identificano i tool candidati nel Grafo Procedurale.  
   * Si filtrano quelli con `weight < soglia_affidabilità`.  
   * Si controllano le dipendenze (es. "Per usare il Tool B serve l'output del Tool A" \-\> Pathfinding nel grafo).  
3. **Execution & Feedback:**  
   * Esegue la chiamata.  
   * **Self-Correction:** Se l'API restituisce un errore di validazione, l'agente legge l'errore, corregge il JSON e riprova (max N tentativi).  
   * A fine esecuzione, aggiorna i pesi nel grafo (Feedback Loop).

---

### **4\. Stack Tecnologico Aggiornato per il Modulo**

Per sostenere questo modulo specifico su hardware limitato (M1 Pro), manteniamo la coerenza con le scelte precedenti:

| Componente | Tecnologia | Ruolo nel Dynamic API Store |
| ----- | ----- | ----- |
| **Discovery** | **Qdrant** | Ricerca semantica ("Trova un tool che faccia X"). |
| **Topology & State** | **Neo4j** | Grafo pesato Intento-Tool, gestione dipendenze e pesi. |
| **Automation** | **LangGraph** | Gestione del ciclo di vita: Ingestione \-\> Esecuzione \-\> Aggiornamento Pesi. |
| **Interfaces** | **FastAPI** | Endpoint per caricare nuovi file OpenAPI (`POST /tools/register`). |

### **Sintesi per il Documento Finale**

Nel documento Blueprint, questa sezione va inserita come **"Modulo Core: Dynamic Procedural Cortex"**, posizionata tra la Memoria Semantica e l'Orchestratore. È il ponte che trasforma la conoscenza in azione.

**Nota di Design:** Questo approccio risolve il problema della "Knowledge Cutoff" per le API. Se un'API cambia (es. deprecazione di un endpoint), l'agente se ne accorgerà perché le chiamate inizieranno a fallire, il peso crollerà, e il sistema smetterà autonomamente di usarla, favorendo alternative funzionanti o richiedendo intervento umano (tramite un segnale di "Tool Bankruptcy").

**APPROFONDIMENTI**

**1\. Visione e Filosofia Architetturale: Il Paradigma Me4BrAIn**

La filosofia alla base di Me4BrAIn Core si fonda sul superamento del paradigma "Stateless" verso un modello di **Cognizione Persistente e Attiva**. Attualmente, un LLM è una funzione pura $f(x) \\rightarrow y$: dato un input, produce un output senza modificare il proprio stato interno. Me4BrAIn trasforma l'agente in una macchina a stati finiti complessa $f(x, S\_t) \\rightarrow (y, S\_{t+1})$, dove $S$ rappresenta lo stato cognitivo globale che evolve irreversibilmente dopo ogni interazione.

Questa visione si articola in tre pilastri tecnici fondamentali:

### **A. Persistenza Poliglotta Cognitiva (The Polyglot Persistence Thesis)**

Rifiutiamo l'idea che un singolo tipo di database possa rappresentare la memoria. Ispirandoci al framework *Texgravec* e alle limitazioni dei sistemi RAG vettoriali puri (il "Muro della Memoria"), adottiamo una strategia di persistenza ibrida dove il dato esiste simultaneamente in tre forme, ognuna ottimizzata per una funzione cognitiva specifica:

1. **Forma Narrativa (Raw Text / Logs):** È la "verità fondamentale" (Ground Truth). Preserva le sfumature linguistiche, il tono e i dettagli grezzi che vengono persi durante la compressione. È gestita come stream immutabile (es. Redis Streams) per garantire auditabilità e riproducibilità (Time Travel).  
2. **Forma Associativa (Dense Vectors):** È il motore dell'intuizione. Utilizziamo embedding vettoriali (Qdrant) non per immagazzinare fatti, ma per calcolare la "distanza semantica" tra concetti. Questo permette il recupero "fuzzy" e l'analogia, superando la rigidità delle keyword.  
3. **Forma Strutturale (Knowledge Graph):** È lo scheletro logico. Utilizziamo un grafo (Neo4j) per modellare esplicitamente causalità, gerarchie e regole. Questo layer è indispensabile per il ragionamento multi-hop (ToG-2) e per evitare le allucinazioni, ancorando la generazione a fatti strutturati verificabili.

### **B. Biomimesi Funzionale: Il "Cervello Disaggregato"**

Non ci limitiamo a usare termini biologici come metafore, ma implementiamo i principi della *Hippocampal Indexing Theory* in componenti software distinti per risolvere problemi ingegneristici reali:

* **L'Ippocampo Digitale (Indice Dinamico):** Non memorizziamo l'intera esperienza nel grafo subito. Utilizziamo **HippoRAG** come meccanismo di indicizzazione rapida. Il grafo funge da indice di puntatori verso i ricordi grezzi, permettendo al sistema di "ricostruire" il ricordo completo attivando solo i nodi rilevanti tramite l'algoritmo *Personalized PageRank* (PPR). Questo riduce drasticamente la latenza rispetto alla scansione vettoriale bruta su miliardi di record.  
* **Consolidamento Attivo (Sleep Cycles):** La memoria non è un deposito statico. Introduciamo cicli di manutenzione asincrona ("Sleep Mode"). Durante i periodi di inattività, il sistema processa i log della *Working Memory* (Redis), estrae nuovi pattern e li sposta nella *Memoria Semantica* (Neo4j), "dimenticando" (eliminando) i vettori di rumore. Questo previene la saturazione dell'indice e mantiene il sistema performante nel lungo periodo, emulando il consolidamento sinaptico biologico.

### **C. Infrastruttura "Cervello-as-a-Service" (Multi-Tenancy & Security)**

Me4BrAIn non è un agente, è l'infrastruttura *per* gli agenti. Deve essere progettata come una piattaforma API-First agnostica rispetto al client.

* **Isolamento Cognitivo (Namespacing):** Ogni applicazione o utente che si connette a Me4BrAIn opera in un "Namespace" cognitivo isolato. Utilizziamo partizionamento logico nei Vector DB (Qdrant Collections) e Labeling nei Graph DB per garantire che le memorie di un tenant non contaminino quelle di un altro.  
* **API Stateless per un Backend Stateful:** L'interfaccia esterna è REST/gRPC standard (stateless), ma ogni chiamata manipola uno stato persistente interno gestito da **LangGraph**. Questo disaccoppiamento permette di scalare orizzontalmente i server API mentre lo stato cognitivo rimane coerente e centralizzato.

### **Sintesi per l'Implementazione**

Questa filosofia impone che ogni riga di codice scritta per Me4BrAIn debba rispondere a una domanda: *"Questo componente sta semplicemente salvando dati, o sta contribuendo alla costruzione attiva di un modello del mondo coerente per l'agente?"*. Se è solo storage passivo, non appartiene al Core. Me4BrAIn deve essere un sistema che *impara* dalla propria esistenza operativa.

Ecco un approfondimento tecnico verticale della sezione **"2. Dettaglio Profondo dei Quattro Layer Cognitivi"** del Blueprint Me4BrAIn Core.

# **2\. Dettaglio Profondo dei Quattro Layer Cognitivi**

Il sistema Me4BrAIn implementa un'architettura **stratificata e asincrona**. Ogni livello opera su una scala temporale diversa e serve una funzione cognitiva specifica, risolvendo il problema del "Muro della Memoria" tipico dei RAG piatti attraverso la specializzazione strutturale.

### **Livello I: Working Memory (STM \- Short Term Memory)**

**Ruolo:** Il "Workbench" Operativo e Contestuale. **Analogo Biologico:** Corteccia Prefrontale \+ Loop Fonologico. **Latenza Target:** \< 5ms (In-Memory).

Questo livello non è un semplice buffer di stringhe (Chat History). È una **Memoria Epistemica Transitoria** che modella lo stato *corrente* del ragionamento.

* **Architettura Ibrida (Redis \+ NetworkX):**  
  * **Stream Sequenziale (Redis):** Utilizziamo `Redis Streams` per mantenere il log immutabile degli ultimi $N$ turni (Human/AI/Tool), garantendo la serializzazione temporale assoluta e la persistenza in caso di crash.  
  * **Episodic Knowledge Graph (EKG) effimero (NetworkX):** Parallelamente al testo, manteniamo un grafo leggero in-memory (Python heap). Quando l'utente menziona "Il progetto", l'LLM estrae l'entità e la collega al nodo contestuale attivo nel grafo (es. `(User)-[:FOCUS_ON]->(Project_Alpha)`).  
* **Funzione Cognitiva:**  
  * **Disambiguazione Real-Time:** Se l'utente dice "Invialo", l'agente interroga il grafo NetworkX per trovare l'ultimo nodo di tipo `Document` o `Artifact` attivo, risolvendo la coreferenza senza dover rileggere 10k token di storia.  
  * **Sliding Window Semantica:** Invece di un taglio brutale (FIFO) dei messaggi vecchi, implementiamo una "Sintesi allo Scadere". Quando un blocco di messaggi esce dalla finestra, un LLM background lo comprime in un *Summary Node* che viene iniettato nel grafo, preservando il significato anche se il testo grezzo viene archiviato.

### **Livello II: Memoria Episodica (LTM Autobiografica)**

**Ruolo:** Il "Diario" dell'Agente e dell'Utente. **Analogo Biologico:** Ippocampo (Tracce mnestiche temporali). **Tecnologia:** Qdrant (Vettori) \+ Neo4j (Metadati Temporali).

Questo livello gestisce la continuità dell'identità nel tempo. Segue il paradigma **A-MEM (Agentic Memory)**, dove i ricordi sono entità attive che si auto-organizzano.

* **Struttura Dati (La "Nota Atomica"):** Ogni interazione significativa non è una riga di log, ma un oggetto strutturato (nodo `Episode`) contenente:  
  * **Contenuto:** Il testo grezzo e il riassunto generato.  
  * **Embedding:** Vettore denso per il recupero "fuzzy" (es. "Quella volta che abbiamo parlato di database").  
  * **Contesto Temporale:** Timestamp bitemporale (*Event Time* vs *Ingestion Time*) per gestire correzioni retroattive ("Ciò che credevo vero ieri, oggi so che è falso").  
* **Dinamica di Auto-Linking (Zettelkasten):** Quando un nuovo episodio viene scritto, il sistema interroga Qdrant per trovare i $k$ episodi passati più simili semanticamente. L'LLM genera poi esplicitamente archi di collegamento (`[:RELATES_TO]`) tra il nuovo episodio e quelli vecchi nel grafo Neo4j. Questo crea **cluster narrativi** (es. "Tutte le volte che l'utente è stato frustrato da un bug Python") che emergono organicamente senza uno schema predefinito.

### **Livello III: Memoria Semantica (Knowledge Graph & World Model)**

**Ruolo:** La Conoscenza Cristallizzata (Fatti, Regole, Relazioni). **Analogo Biologico:** Neocorteccia. **Tecnologia:** Neo4j (Graph Database) \+ HippoRAG / LightRAG.

Qui risiede la "verità" fattuale, disaccoppiata dall'episodio specifico in cui è stata appresa. Questo layer adotta un'architettura **"Fast & Slow"** per bilanciare aggiornamento e profondità.

* **Hot Path (LightRAG \- Memoria Agile):** Per l'ingestione rapida di nuovi documenti o knowledge base. Utilizza un'indicizzazione a doppio livello (Low-Level per dettagli specifici, High-Level per temi astratti) e linearizza le strutture grafo in vettori per un recupero immediato senza latenza di calcolo grafo complesso.  
* **Cold Path (HippoRAG \- Memoria Profonda):** Per il ragionamento complesso. Utilizza l'algoritmo **Personalized PageRank (PPR)** su Neo4j. Se la query è "Impatto del farmaco X", il PPR propaga l'attivazione nel grafo per "accendere" concetti correlati (es. "Proteina Y", "Effetto Collaterale Z") che non sono esplicitamente nella query ma sono strutturalmente collegati. Questo emula l'associazione di idee umana e risolve il problema del "Missing Link" dei vettori puri.  
* **Ontologia Ibrida:**  
  * *Schema Rigido:* Per domini critici (Finanza), usiamo nodi tipizzati (`:Company`, `:Stock`) con proprietà convalidate.  
  * *Schema Fluido (OpenIE):* Per domini esplorativi, permettiamo all'LLM di creare nuovi tipi di nodi al volo, che vengono poi consolidati (clustering) durante i cicli notturni.

### **Livello IV: Memoria Procedurale (Skill & Muscle Memory)**

**Ruolo:** Il "Manuale Operativo" Eseguibile. **Analogo Biologico:** Gangli della Base / Cervelletto. **Tecnologia:** Vector Store (Few-Shot Examples) \+ Skill Graph.

Questo livello è critico per l'agency: non memorizza *cosa* è successo, ma *come* risolvere i problemi. È un sistema di apprendimento per rinforzo implicito.

* **Il Grafo delle Competenze (Skill Graph):** Rappresentiamo le capacità dell'agente come un grafo `(:Problem)-[:SOLVED_BY]->(:Tool)`.  
  * **Pesi Adattivi:** Ogni arco ha un peso di confidenza ($0.0 \- 1.0$). Se l'agente usa il tool `Python_REPL` per risolvere un problema di matematica e ha successo, il peso aumenta. Se fallisce (eccezione, timeout), il peso diminuisce. Nel tempo, l'agente "impara" quali strumenti sono affidabili per quali task.  
* **Cristallizzazione dei Prompt (Muscle Memory):** Quando una sequenza di azioni complessa (Chain-of-Thought) porta a un successo confermato dall'utente, l'intera traccia (Prompt \+ Tool Calls \+ Output) viene salvata come un "Few-Shot Example" ottimizzato in Qdrant.  
  * **Retrieval:** Alla successiva richiesta simile, l'agente non ragiona da zero (lento/costoso), ma recupera questo esempio ("ricetta") e lo applica per analogia, riducendo drasticamente la latenza e il rischio di errore (Logic ToG-2).

---

**Sintesi dell'Integrazione:** Questi quattro livelli non operano in isolamento. Il **Router Semantico** (in ingresso) smista la query al livello appropriato, mentre il processo di **Consolidamento Notturno** (in background) sposta le informazioni mature dalla Working Memory (I) e Episodica (II) verso la Semantica (III) e Procedurale (IV), raffinando costantemente il modello mentale dell'agente.

Ecco l'approfondimento tecnico verticale della sezione **"3. Il Ciclo Cognitivo: Veglia e Sonno"** del Blueprint Me4BrAIn Core.

# **3\. Il Ciclo Cognitivo: Veglia e Sonno (The Circadian Compute Cycle)**

Il sistema Me4BrAIn non opera in uno stato costante. Emulando la biologia, alterna fasi di **alta reattività e basso carico cognitivo di scrittura** (Veglia) a fasi di **bassa reattività e alto carico di consolidamento** (Sonno). Questa dicotomia è essenziale per gestire i costi computazionali di *GraphRAG* e la complessità di mantenimento della coerenza in sistemi distribuiti.

### **A. Fase di Veglia (Online \- Inference & Interaction)**

*Stato: High Availability, Read-Heavy, Latency-Critical (\< 2s).*

Durante la fase di veglia, il sistema è ottimizzato per l'inferenza rapida. L'obiettivo è rispondere all'utente navigando le strutture di memoria esistenti senza tentare di ristrutturarle profondamente in tempo reale.

1. **Semantic Routing & Intent Classification:** Appena una richiesta (`POST /invoke`) arriva, non interroghiamo ciecamente tutto il database. Un "Router Semantico" leggero (basato su un LLM piccolo o un classificatore BERT) determina la natura della query:

   * *Factual/Specific:* Attiva il recupero puntuale via **LightRAG** (Low-Level) su Qdrant \+ Keyword Search.  
   * *Thematic/Complex:* Attiva il recupero globale via **GraphRAG** (High-Level summaries) su Neo4j.  
   * *Procedural:* Attiva la ricerca nello Skill Store per tool e workflow.  
2. **Hybrid Retrieval & "Fast Path" Reasoning:** Il sistema esegue una ricerca parallela.

   * **Vettoriale (Qdrant):** Recupera i chunk semanticamente simili.  
   * **Grafo (Neo4j/NetworkX):** Qui implementiamo la logica **Think-on-Graph 2.0 (ToG-2)** in modalità "Inference-Only". L'agente esplora i nodi vicini alle entità menzionate nella query per trovare connessioni, ma *non* aggiorna il grafo. Utilizza un meccanismo di **Pruning** (potatura) attivo per scartare i percorsi irrilevanti basandosi sulla lettura dei documenti associati ai nodi, riducendo le allucinazioni.  
3. **Gestione della Memoria di Lavoro (STM):** Ogni interazione viene immediatamente loggata nella *Working Memory* su **Redis**. Questo non è solo un log, ma uno "Stream di Eventi" immutabile che funge da buffer ad alta velocità per la fase successiva. L'uso di Redis garantisce che la scrittura non blocchi il thread di risposta.

---

### **B. Fase di Sonno (Offline \- Consolidation & Reflection)**

*Stato: Background Processing, Write-Heavy, High-Compute.*

Questa fase è il cuore dell'apprendimento a lungo termine. Viene triggerata da eventi di inattività (es. nessun messaggio per 10 minuti) o schedulata periodicamente (batch notturni). Qui avviene il passaggio dalla memoria a breve termine (STM) a quella a lungo termine (LTM), emulando il consolidamento ippocampale-corticale.

#### **1\. Il Processo di Digestione (Mem0 Pipeline)**

Un worker asincrono preleva i log dalla Working Memory (Redis) e avvia la pipeline di estrazione ispirata a **Mem0**:

* **Fact Extraction:** Un LLM "Operaio" (es. GPT-4o-mini o Gemini Flash) analizza la conversazione grezza ed estrae fatti atomici (es. "L'utente lavora in Python", "Il progetto X scade domani").  
* **Deduplicazione e Risoluzione:** Il sistema controlla se questi fatti esistono già nel Grafo (Neo4j).  
  * *Se Nuovo:* Crea nuovi nodi/archi.  
  * *Se Conflitto:* Se il fatto contraddice una conoscenza precedente (es. "L'utente usa Java"), il sistema applica una logica di risoluzione basata sul timestamp (il fatto più recente vince) o marca il vecchio fatto come "Archiviato" (bitemporalità), mantenendo la storia.

#### **2\. Ristrutturazione del Grafo (GraphRAG Maintenance)**

L'inserimento di nuovi nodi degrada la qualità degli indici globali di **GraphRAG**. Durante il sonno, il sistema esegue operazioni costose che non potremmo fare online:

* **Community Detection (Leiden):** Ricalcola le comunità di nodi su Neo4j per riflettere le nuove informazioni. Se abbiamo aggiunto molti dettagli su un nuovo argomento, potrebbe emergere una nuova "Comunità" tematica.  
* **Summarization Update:** Rigenera i riassunti delle comunità. Questo garantisce che quando l'agente dovrà rispondere a domande globali ("Come sta andando il progetto X?"), la risposta includerà gli ultimi sviluppi consolidati.

#### **3\. Garbage Collection Semantica ("Active Forgetting")**

Per evitare che il sistema diventi lento e rumoroso, implementiamo l'**Oblio Attivo**:

* **Pruning Vettoriale:** I vettori nella memoria episodica che non sono stati richiamati per un lungo periodo e hanno bassa rilevanza (score di decadimento temporale) vengono archiviati o eliminati.  
* **Consolidamento Episodico:** Sequenze di interazioni vecchie vengono compresse in un unico "riassunto episodico" nel grafo, e i log grezzi vengono rimossi da Qdrant per liberare spazio e mantenere l'indice performante.

---

### **C. Orchestrazione Tecnica: LangGraph Checkpointing**

Il passaggio tra Veglia e Sonno e la persistenza dello stato sono gestiti da **LangGraph**.

* **State Persistence:** Utilizziamo un checkpointer (su Postgres o Redis) per salvare lo stato dell'agente alla fine di ogni fase di veglia. Questo permette di riprendere la conversazione esattamente dove era stata lasciata, anche se il server viene riavviato.  
* **Gestione della Concorrenza:** Durante la fase di Sonno, se l'utente torna attivo ("sveglia" l'agente), il sistema deve gestire la concorrenza. Utilizziamo meccanismi di **Locking ottimistico** o code di priorità: l'agente risponde usando la memoria "vecchia" (snapshot precedente al sonno) mentre il processo di aggiornamento completa in background, garantendo che l'UX non venga mai bloccata.

### **Sintesi del Valore Architetturale**

Questa divisione risolve il "Paradosso della Coerenza":

1. **LightRAG/Redis (Veglia)** garantiscono che l'agente sappia cosa hai detto 5 secondi fa.  
2. **GraphRAG/Mem0 (Sonno)** garantiscono che l'agente capisca le implicazioni profonde di ciò che hai detto ieri, integrando quella conoscenza nel suo modello del mondo strutturato senza impattare la latenza della chat odierna.

Ecco un approfondimento tecnico verticale della sezione **"4. API Gateway e Interfaccia Esterna"** del Blueprint Me4BrAIn Core.

# **4\. API Gateway e Interfaccia Esterna: Il "Cortex Interface Layer"**

Il Gateway è progettato con un approccio **Async-First** basato su **FastAPI**, ottimizzato per gestire connessioni a lunga durata (necessarie per le chain di ragionamento complesso) e per esporre non solo le *risposte* dell'agente, ma anche il suo *processo di pensiero*.

### **4.1 Strategia di Interfaccia: Oltre il Request/Response**

Gli agenti cognitivi non funzionano come le API tradizionali (input \-\> calcolo \-\> output immediato). Hanno tempi di latenza variabili dovuti al ragionamento (ToG-2) e al recupero (GraphRAG). Pertanto, l'interfaccia implementa tre pattern di comunicazione:

1. **Streaming Sincrono (SSE \- Server-Sent Events):** Per l'interazione chat real-time. Permette di inviare token di risposta appena generati (TTFT \- Time To First Token basso) mentre in background il sistema sta ancora consolidando la memoria.  
2. **Asincrono (Job Queues):** Per operazioni di ingestione massiva (es. "Impara questo manuale PDF"). Il client riceve un `job_id` e fa polling o attende un webhook.  
3. **Introspezione (Debug):** Endpoint speciali che restituiscono non la risposta, ma il sottografo della memoria attivato, permettendo agli sviluppatori di capire *perché* l'agente ha risposto in un certo modo.

---

### **4.2 Specifica degli Endpoint Core (OpenAPI/Swagger)**

#### **A. Endpoint Cognitivi (Interazione Agente)**

* **`POST /v1/agent/invoke`**

  * **Descrizione:** Punto di ingresso primario per il ragionamento.

**Payload:**  
 {

  "query": "Analizza l'impatto del trend X",

  "session\_id": "sess\_123", // Per la Working Memory (Redis)

  "mode": "reasoning", // 'fast' (LightRAG) o 'deep' (ToG-2)

  "stream": true

}

*   
  * **Output (Stream):** Non invia solo testo. Invia eventi tipizzati:  
    * `event: retrieval_start` \-\> payload: `{ "sources": ["doc_A", "node_B"] }`  
    * `event: reasoning_step` \-\> payload: `{ "thought": "Analizzando la correlazione..." }`  
    * `event: answer_chunk` \-\> payload: `{ "text": "L'impatto è..." }`  
  * **Logica Architetturale:** Questo endpoint istanzia il grafo **LangGraph**. Il gateway non contiene logica di business, ma funge da *init* per l'esecuzione del grafo.  
* **`POST /v1/agent/feedback`**

  * **Descrizione:** Reinforcement Learning from Human Feedback (RLHF) "lite".  
  * **Funzione:** Se l'utente corregge l'agente, questo endpoint inietta un segnale di "errore" nella memoria procedurale. Il sistema riduce il peso dell'arco nel grafo `[:SOLVES]` che ha portato alla risposta errata.

#### **B. Endpoint Mnestici (Gestione Memoria)**

* **`POST /v1/memory/ingest`**

  * **Descrizione:** Inserimento esplicito di conoscenza (non episodica).  
  * **Handling:** I file caricati non vengono processati subito (per non bloccare il thread). Vengono messi in una coda **Redis** o **Celery**. Un worker background esegue la pipeline di estrazione (OpenIE/LightRAG) e notifica il completamento.  
* **`GET /v1/memory/inspect`**

  * **Descrizione:** "Cosa sai su X?".  
  * **Tecnologia:** Esegue una query ibrida.  
    1. **Qdrant:** Recupera i chunk vettoriali simili a X.  
    2. **Neo4j:** Esegue una query Cypher per trovare i vicini di X (1-hop).  
  * **Output:** Restituisce un JSON graph-like visualizzabile dai frontend delle applicazioni client per mostrare la "mappa mentale" dell'agente.  
* **`DELETE /v1/memory/forget`** (Compliance GDPR/Oblio)

  * **Logica:** Esegue una cancellazione "chirurgica".  
    1. Identifica tutti i nodi e vettori taggati con un metadato specifico (es. un argomento sensibile o un periodo temporale).  
    2. Esegue `DELETE` su Neo4j e `points.delete` su Qdrant.  
    3. Forza un re-indexing parziale se necessario.

---

### **4.3 Architettura di Sicurezza e Multi-Tenancy (Row-Level Security)**

Poiché Me4BrAIn serve più applicazioni, la segregazione dei dati è critica. Non possiamo permettere che la memoria finanziaria del "Cliente A" influenzi le risposte mediche del "Cliente B".

**Strategia di Isolamento (Tenant Context Injection):**

1. **Authentication Middleware:**

   * Ogni richiesta deve avere un JWT. Il Gateway decodifica il token ed estrae `tenant_id` e `user_id`.  
   * Questi ID vengono iniettati nel `ContextVar` di Python, rendendoli accessibili globalmente in tutto il thread di esecuzione.  
2. **Segregazione Storage (Data Layer):**

**Qdrant (Vettori):** Utilizziamo il **Payload Filtering** forzato. Ogni query verso Qdrant viene intercettata da un wrapper che appende automaticamente un filtro:  
 \# Esempio di filtro forzato dal sistema

filters \= Filter(

    must=\[FieldCondition(key="tenant\_id", match=MatchValue(value=ctx.tenant\_id))\]

)

*   
  * **Neo4j (Grafo):** Utilizziamo il **Labeling Dinamico**. Invece di database fisici separati (pesanti per la RAM su M1 Pro), usiamo etichette combinate.  
    * Nodo standard: `(:Person)`  
    * Nodo Multi-tenant: `(:Tenant_123_Person)`  
    * Il Gateway riscrive dinamicamente le query Cypher (o i prompt che generano Cypher) per includere il prefisso del tenant, garantendo l'invisibilità dei dati altrui.  
3. **Redis (Working Memory):**

   * Le chiavi di sessione sono prefissate: `tenant:{id}:user:{id}:session:{id}`.

---

### **4.4 Stack Tecnologico del Gateway (Ottimizzazione M1 Pro)**

Per massimizzare l'efficienza su hardware limitato (16GB RAM), evitiamo container Java pesanti o gateway enterprise complessi (come Kong).

* **Framework:** **FastAPI** (Python). Leggero, asincrono nativo, auto-genera documentazione Swagger.  
* **Server:** **Uvicorn** con loop `uvloop` (basato su libuv/C++), massimizza il throughput su core Apple Silicon.  
* **Middleware di Sicurezza:** **PyJWT** per validazione stateless dei token.  
* **Rate Limiting:** Implementato via **Redis** (usando lo stesso container della Working Memory) per prevenire abusi e proteggere la coda di inferenza LLM.

### **Sintesi del Valore**

Questo layer trasforma i concetti astratti di "memoria" e "ragionamento" in primitive software consumabili. Permette agli sviluppatori front-end di costruire interfacce che non sono solo chat, ma dashboard di conoscenza, dove l'utente può vedere, correggere e gestire ciò che l'IA ricorda, elevando il sistema da "Black Box" a "Glass Box".

# **5\. Stack Tecnologico: L'Ecosistema Me4BrAIn (Specifiche M1 Pro)**

Il sistema adotta un approccio **Ibrido Edge-Cloud**: la gestione dello stato e della memoria risiede localmente (sovranità dei dati), mentre il carico computazionale "pesante" (inferenza LLM) è delegato via API.

## **5.1 Livello di Orchestrazione: Il "Sistema Nervoso"**

Il cuore pulsante non è una semplice catena sequenziale, ma una macchina a stati finiti persistente.

* **Framework Core:** **LangGraph** (Python).  
  * *Perché:* A differenza di LangChain o AutoGen, LangGraph supporta nativamente i **grafi ciclici**. Questo è indispensabile per i loop di auto-correzione (es. "Il tool ha fallito \-\> Riprova con parametri diversi") e per il ciclo Veglia/Sonno.  
  * *State Schema:* Utilizziamo **Pydantic** per definire rigidamente lo `AgentState`. Questo garantisce che la struttura della memoria (messaggi, entità estratte, errori) sia tipizzata e validata a runtime, prevenendo corruzione dei dati durante i passaggi complessi.  
* **Persistence Layer (Checkpointer):** **SQLite** (Locale/Dev) o **PostgreSQL** (Prod).  
  * *Configurazione:* LangGraph salva lo stato a ogni "superstep". Su M1 Pro, utilizziamo `SqliteSaver` con scrittura asincrona (`WAL mode`) per minimizzare l'I/O blocking senza dover gestire un container Docker aggiuntivo pesante come Postgres in fase di sviluppo.

## **5.2 Livello Computazionale (Inference & Embeddings)**

Qui applichiamo la strategia di risparmio RAM più aggressiva.

* **Embedding Model (Locale):** **`intfloat/e5-small-v2`**.  
  * *Specifica Tecnica:* Modello da \~118M parametri.  
  * *Impronta RAM:* **\~450 MB**.  
  * *Accelerazione:* Eseguito su **MPS (Metal Performance Shaders)** tramite PyTorch/HuggingFace.  
  * *Motivazione:* È l'unico modello che garantisce qualità SOTA (State of the Art) per il retrieval semantico occupando meno di 500MB. Modelli più grandi (come `bge-m3` o `nomic`) saturerebbero la memoria unificata, togliendo spazio a Neo4j.  
* **LLM (Cervello Remoto):** **API Cloud** (OpenAI / Anthropic / Google).  
  * *Motivo Critico:* Caricare un modello locale quantizzato (es. Llama-3-8B a 4-bit) richiederebbe \~5-6 GB di RAM. Questo renderebbe impossibile eseguire Neo4j e Qdrant contemporaneamente. Delegare l'inferenza libera risorse per la memoria persistente.  
  * *Configurazione Veglia:* `GPT-4o` o `Claude 3.5 Sonnet` per il ragionamento complesso (ToG-2).  
  * *Configurazione Sonno:* `GPT-4o-mini` o `Gemini 1.5 Flash` per i task batch di consolidamento (costo irrisorio, alta velocità).

## **5.3 Livello di Persistenza Poliglotta (Storage Layer)**

Utilizziamo tre tecnologie di database specializzate, orchestrate tramite **Docker Compose** con limiti di memoria (`mem_limit`) rigorosi per evitare crash di sistema.

### **A. Working Memory (STM)**

* **Tecnologia:** **Redis Stack**.  
* *Configurazione Docker:* `redis:latest`. Limite RAM: **512 MB**.  
* *Ruolo:*  
  1. **Event Stream:** Log immutabile della conversazione (TTFT \< 1ms).  
  2. **Semantic Cache:** Caching delle risposte frequenti per risparmiare chiamate API.  
  3. **Graph Cache:** Serializzazione rapida dei grafi effimeri **NetworkX** che modellano le relazioni della sessione corrente (es. coreferenze immediate).

### **B. Memoria Episodica e Procedurale (LTM Vettoriale)**

* **Tecnologia:** **Qdrant**.  
* *Configurazione Docker:* `qdrant/qdrant:latest`. Limite RAM: **2 GB**.  
* *Perché Qdrant:* Scritto in **Rust**, ha un overhead di memoria minimo rispetto a Milvus (Java/Go) o Weaviate. Supporta nativamente il **Mmap** (Memory Mapping), permettendo di caricare in RAM solo i segmenti vettoriali "caldi" e lasciando il resto su disco SSD (che su M1 è velocissimo), ottimizzando l'uso dei 16GB.  
* *Organizzazione:*  
  * Collection `episodes`: Payload con `{timestamp, user_id, content}`.  
  * Collection `skills`: Payload con `{tool_name, success_rate, few_shot_prompt}`.

### **C. Memoria Semantica (Knowledge Graph)**

* **Tecnologia:** **Neo4j Community Edition**.  
* *Configurazione Docker:* `neo4j:5.x`. Limite RAM (Heap): **3 GB**.  
* *Ottimizzazione:*  
  * Disabilitare plugins pesanti non necessari (es. GDS Enterprise se non usato intensivamente).  
  * Usare **APOC Core** per utility leggere.  
  * *Ruolo:* Supporto per **HippoRAG**. Mantiene l'ontologia del dominio e i collegamenti inter-episodici generati da A-MEM.  
  * *Fallback:* Se Neo4j diventa troppo pesante per il carico (es. grafo \> 100k nodi), il sistema è progettato per fare fallback su **KùzuDB** (un graph DB embedded process-in, simile a SQLite per i grafi), che non richiede un server Docker separato.

## **5.4 Livello di Interfaccia (Gateway API)**

* **Framework:** **FastAPI** (Python).  
* **Server:** **Uvicorn** (con `uvloop`).  
* **Sicurezza:** Middleware `PyJWT` per la decodifica dei token e l'iniezione del `tenant_id` nel contesto di esecuzione.  
* **Async Pattern:** Sfrutta `asyncio` per gestire le chiamate parallele a Qdrant e Neo4j senza bloccare il thread principale, essenziale per mantenere l'interfaccia reattiva durante i ragionamenti complessi.

## **5.5 Allocazione Risorse (Budget RAM 16GB)**

Ecco la "distinta base" delle risorse per garantire stabilità su M1 Pro:

| Componente | Tecnologia | Allocazione RAM (Target) | Note Tecniche |
| ----- | ----- | ----- | ----- |
| **OS \+ System** | macOS | \~4.0 GB | Overhead incomprimibile. |
| **Vector DB** | **Qdrant** | 2.0 GB (Limit) | Usa Mmap per offload su SSD. |
| **Graph DB** | **Neo4j** | 3.0 GB (Heap) | Minimo vitale per Java VM. |
| **STM / Cache** | **Redis** | 0.5 GB | Sufficiente per code e log recenti. |
| **App Core** | **Python/LangGraph** | \~1.5 GB | Include caricamento librerie. |
| **Embeddings** | **e5-small-v2** | \~0.5 GB | Caricato in memoria PyTorch. |
| **Margine** | (Free) | \~4.5 GB | Buffer per picchi e browser/IDE. |
| **TOTALE** |  | **\~16.0 GB** | **Saturazione controllata.** |

### **Sintesi per il Documento Finale**

Questa configurazione dimostra che è possibile eseguire un'architettura cognitiva di classe Enterprise su hardware consumer di fascia alta, a patto di scegliere componenti efficienti (Rust/C++ based come Qdrant e Redis) e di delegare strategicamente l'inferenza generativa (LLM) al cloud, mantenendo però la struttura della conoscenza (Vettori e Grafi) rigorosamente locale e sotto il controllo dell'applicazione.

Ecco l'approfondimento tecnico verticale della sezione **"6. Il Cortex Procedurale (Dynamic API Store)"** del Blueprint Me4BrAIn Core.

# **6\. Il Cortex Procedurale: Dynamic API Store & Muscle Memory**

Il Cortex Procedurale è un sottosistema ibrido che gestisce il ciclo di vita degli strumenti (Tools/API): dalla scoperta, all'apprendimento, fino all'ottimizzazione e all'eventuale obsolescenza.

### **6.1 Architettura Logica: Il Grafo Probabilistico Strumento-Intento**

Non utilizziamo una lista piatta di definizioni OpenAPI. Modelliamo le capacità dell'agente come un **Grafo Bipartito Pesato** all'interno di **Neo4j**, arricchito da indici vettoriali in **Qdrant**.

#### **Ontologia del Grafo (Neo4j)**

1. **Nodi `(:Intento)`**: Rappresentano l'obiettivo astratto dell'utente o dell'agente.  
   * *Esempi:* "Recupero Prezzo Azionario", "Invio Email", "Analisi Chimica".  
   * *Proprietà:* Embedding vettoriale della descrizione dell'intento.  
2. **Nodi `(:Tool)`**: Rappresentano l'endpoint API o la funzione Python specifica.  
   * *Proprietà:* `endpoint`, `method`, `schema_json` (input/output), `version`.  
   * *Stato:* `ACTIVE`, `DEPRECATED`, `EXPERIMENTAL`.  
3. **Relazione `[:RISOLVE]`**: Collega un Intento a un Tool.  
   * *Proprietà Dinamiche:*  
     * `weight` (0.0 \- 1.0): Probabilità di successo storica.  
     * `avg_latency` (ms): Tempo medio di esecuzione.  
     * `cost` (float): Costo stimato (es. token o $ per chiamata API).  
4. **Relazione `[:REQUIRES]`**: Modella le dipendenze forti.  
   * Es: `(:Tool:BuyStock)-[:REQUIRES]->(:Tool:GetAuthToken)`. Questo permette a **LangGraph** di pianificare sequenze di chiamate (Chain) senza che l'LLM debba "indovinarle" ogni volta.

---

### **6.2 Pipeline di Ingestione Evolutiva ("Learning by Reading")**

Il sistema non nasce con tutte le API pre-codificate. Dispone di una pipeline di ingestione "Zero-Shot" gestita da un Worker asincrono.

1. **Input:** Un file `openapi.json` o una docstring Python viene fornita al sistema.  
2. **Parsing Semantico:** Un LLM (es. GPT-4o-mini per risparmiare risorse) analizza le specifiche.  
   * Estrae le funzionalità atomiche.  
   * Genera descrizioni sintetiche in linguaggio naturale ("Questo tool permette di...").  
3. **Cristallizzazione:**  
   * Crea i nodi `(:Tool)` in Neo4j.  
   * Genera embeddings delle descrizioni e li salva in **Qdrant** (Collection `procedural_memory`).  
4. **Linking Ipotetico:** L'LLM ipotizza quali `(:Intento)` esistenti potrebbero essere risolti da questo nuovo tool e crea archi `[:RISOLVE]` con un peso basso (`weight=0.1`, "Novizio"), pronto per essere testato.

---

### **6.3 Il Meccanismo di "Muscle Memory" (Cache Procedurale)**

Questa è l'ottimizzazione critica per l'hardware M1 Pro. Ragionare su come costruire un JSON complesso è costoso in termini di token e tempo. Vogliamo che l'agente "ricordi" come ha fatto l'ultima volta.

Utilizziamo **Qdrant** per implementare un **Few-Shot Store Dinamico**.

**Struttura del Ricordo Procedurale:**  
 {

  "intent\_vector": \[...\], // Embedding della richiesta utente

  "tool\_name": "stripe\_charge",

  "successful\_call": {

    "amount": 100,

    "currency": "usd",

    "customer": "{{customer\_id}}" // Template parametrico

  },

  "timestamp": 1715629...

}

*   
* **Workflow di Recupero (Fast Path):**  
  * Arriva una richiesta: "Addebita 50 euro a Mario".  
  * Query su Qdrant: Cerca ricordi procedurali simili.  
  * **Hit:** Trovato un esempio di successo per "stripe\_charge".  
  * **Bypass del Ragionamento:** L'agente non legge la documentazione API. Prende il JSON dell'esempio, sostituisce i valori (50, EUR, Mario) e esegue.  
  * *Risultato:* Latenza ridotta del 60-80%.

---

### **6.4 Feedback Loop e Rinforzo (RLHF Implicito)**

Il sistema apprende dall'uso. Ogni esecuzione di un tool è un segnale di addestramento per il grafo.

1. **Successo (HTTP 200 / Output Valido):**  
   * Incrementa il `weight` dell'arco `[:RISOLVE]` in Neo4j (formula di decadimento esponenziale: premia successi recenti).  
   * Se l'esecuzione era complessa, salva il "Trace" in Qdrant come nuovo esempio di Muscle Memory.  
2. **Fallimento (HTTP 4xx/5xx / Eccezione):**  
   * Decrementa il `weight`. Se scende sotto una soglia (es. 0.2), l'arco viene tagliato (il tool non è più considerato affidabile per quell'intento).  
   * **Self-Correction:** L'errore viene registrato nel nodo `(:Tool)` come "Vincolo Negativo" (es. "Non usare il parametro 'date' con la versione 2.0"). Alla prossima chiamata, questo vincolo viene iniettato nel prompt per evitare di ripetere l'errore.

---

### **6.5 Integrazione nello Stack Tecnologico (M1 Pro Optimization)**

| Componente | Tecnologia | Configurazione M1 Pro (16GB) | Ruolo |
| ----- | ----- | ----- | ----- |
| **Semantic Router** | **Qdrant** | Collection `tools` (Quantizzazione Int8) | Mappa "Linguaggio Naturale" \-\> "Tool ID" in \<10ms. |
| **Topology & State** | **Neo4j** | Heap 1GB (Grafo leggero) | Gestisce dipendenze, pesi di fiducia e stato (Active/Deprecated). |
| **Logic** | **LangGraph** | Nodo `ToolManager` | Esegue la logica di fallback: Muscle Memory \-\> Documentation \-\> Retry. |
| **Code Sandbox** | **Python `exec`** | Processo isolato | Esegue il codice generato per chiamare le API (leggero e locale). |

### **Sintesi Operativa**

Il Cortex Procedurale trasforma Me4BrAIn da un sistema che deve "leggere il manuale" ogni volta che deve agire, a un esperto che agisce "di riflesso" per i compiti noti, ma che sa ricorrere al manuale (e imparare da esso) quando affronta situazioni nuove o errori imprevisti. Questo garantisce che il sistema diventi **più veloce e affidabile** quanto più viene utilizzato.