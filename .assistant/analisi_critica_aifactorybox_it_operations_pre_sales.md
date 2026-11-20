# Analisi Critica di Progetto: IT, Operations e Pre-Sales

Questo documento raccoglie una valutazione tecnica, operativa e commerciale dell'architettura attuale di **AIFactoryBox** (profilo ibrido con Control Plane self-hosted su VPS Linux e inferenza delegata a provider SaaS tramite LiteLLM Proxy).

---

## 1. Punto di Vista IT & Architettura Software

### Punti di forza
* **Delega al Control Plane LiteLLM:** aver affidato a LiteLLM Proxy il routing dei modelli, le virtual key, i budget per tenant e gli hook pre-call di Presidio evita di mantenere codice Python custom per autenticazione, accounting e retry verso i provider.
* **Persistenza consolidata (`pgvector`):** l'unificazione di `litellm_db` e `knowledge_db` sulla stessa istanza PostgreSQL (`pgvector/pgvector:pg15`) con auto-inizializzazione elimina la necessità di un database vettoriale dedicato, semplificando transazioni e filtri JSONB.
* **Client-side Flows (`flows/`):** la scelta di un SDK asincrono leggero (`httpx`) al posto di un orchestratore workflow containerizzato (es. n8n o Node-RED) riduce l'impronta di RAM e garantisce che ogni pipeline attraversi sempre l'ingress autenticato.

### Criticità e rischi tecnici da colmare
* **Contratti dei backend "retained" da verificare end-to-end:** gli adattatori verso **Docling** (`/process` su porta 5000) e **Piper TTS** (`/api/tts` su porta 5500) richiedono verifica contro le versioni correnti delle rispettive immagini Docker (es. `/v1/convert/file` nelle build recenti di `docling-serve` e disponibilità effettiva dell'endpoint HTTP JSON di Piper).
* **Perimetro e limiti del mascheramento PII (Presidio):**
  * Il guardrail `pre_call` analizza il testo delle richieste chat, ma non ispeziona automaticamente file binari, immagini o payload JSON arbitrari.
  * I modelli spaCy `it_core_news_sm` ed `en_core_web_sm` offrono buona velocità su CPU ma hanno recall limitata su entità italiane complesse (es. codici fiscali, indirizzi italiani, nominativi non standard).
  * Con `output_parse_pii: false` non è attiva la de-anonimizzazione reversibile nella risposta del modello: il modello riceve e restituisce i segnaposto (es. `<PERSON>`).
* **Affidabilità degli endpoint Hugging Face Inference API:** modelli come `huggingface/BAAI/bge-m3` e `huggingface/BAAI/bge-reranker-v2-m3` su endpoint serverless condivisi possono presentare *cold start* (HTTP 503) o richiedere un *Dedicated Inference Endpoint* URL esplicito per garantire latenze stabili in produzione.
* **Protezione dell'interfaccia `/console/`:** l'HTML della Operations Console è servito pubblicamente mentre le chiamate API sottostanti sono protette da Bearer key. In ambienti enterprise conviene proteggere anche la shell statica `/console/` tramite Basic Auth o SSO/OAuth2 Proxy.

---

## 2. Punto di Vista Operations & Sicurezza (Day-2)

### Punti di forza
* **Perimetro di rete chiuso:** nessun servizio interno (`orchestrator`, `litellm-proxy`, `postgres-audit`, `presidio`) pubblica porte sull'host; tutto il traffico transita da Nginx (e opzionalmente Caddy TLS su porta 443).
* **Osservabilità aggregata:** l'endpoint `/specialized/status` integrato nella Operations Console fornisce una verifica reale della raggiungibilità e latenza dei singoli motori, superando il limite di `/health` (che verifica solo la liveness di LiteLLM).
* **Sostenibilità infrastrutturale:** disabilitando i container locali pesanti (`tei-embeddings`, `tei-rerank`, `faster-whisper`) tramite il profilo `docker-compose.cloud.yml`, l'intero stack gira comodamente su una VPS CPU standard da 8 GB di RAM a costo fisso.

### Criticità e rischi operativi
* **Backup automatizzato del database:** il volume PostgreSQL contiene sia lo stato/chiavi di LiteLLM (`litellm_db`) sia tutti i vettori e i chunk della Knowledge Base (`knowledge_db`), ma manca ancora un job schedulato di `pg_dump` verso uno storage esterno (es. S3/Object Storage).
* **Indicizzazione vettoriale su larga scala (`pgvector`):** la tabella `kb_chunks` utilizza indici B-tree/GIN su `collection_name`, `document_id` e `metadata`, ma non ha ancora un indice vettoriale HNSW o IVFFlat (poiché la colonna `embedding vector` è polimorfica). Oltre i ~30.000–50.000 chunk per collection sarà necessario creare indici HNSW parziali con cast dimensionale esplicito (`embedding::vector(1024)`).
* **Controllo dimensione upload e timeout:** solo `/v1/vision/ocr` applica un limite esplicito a 20 MiB, mentre Nginx consente fino a `100M`. L'invio di documenti molto pesanti a `/v1/knowledge/ingest` potrebbe saturare la RAM del container `docling-service` su una VPS da 8 GB.
* **Single Point of Failure (SPOF) e log retention:** su singola VPS gli aggiornamenti con ricostruzione container comportano alcuni secondi di indisponibilità. Inoltre va configurata la rotazione dei log Docker (`max-size` / `max-file`) e una policy di retention per evitare saturazione del disco NVMe e persistenza non necessaria di payload nei log.

---

## 3. Punto di Vista Pre-Sales & Posizionamento Commerciale

### Punti di forza
* **Proposta di valore chiara ("Sovranità + Zero GPU"):** per PMI ed enti italiani, la combinazione tra server europeo con fatturazione italiana, sanificazione PII locale prima dell'invio ai modelli esterni, assenza di costi hardware GPU e indipendenza dai singoli vendor AI rappresenta un vantaggio competitivo immediato.
* **Multi-tenancy e controllo spesa nativi:** il rilascio di Virtual Key per reparto/cliente con budget mensile e isolamento dei documenti per `tenant` su PostgreSQL risponde direttamente alle esigenze di IT Manager e CFO.
* **Percorso evolutivo flessibile (SaaS oggi, On-Premise domani):** la stessa architettura può essere proposta in cloud gestito (VPS europea + Groq/Hugging Face) per partenze rapide a basso costo, oppure migrata su infrastruttura on-premise (sostituendo gli alias in `litellm-config` con Ollama/vLLM) per clienti con vincoli stringenti di non-esfiltrazione.

### Criticità e obiezioni tipiche in trattativa
* **Differenziazione rispetto a Open WebUI + LiteLLM standard:** davanti a interlocutori tecnici occorre evidenziare i tre elementi distintivi del progetto:
  1. **Knowledge Base API-first (`pgvector` + reranking + metadata tenant)** consumabile da qualsiasi applicazione aziendale, non vincolata alla sola UI di chat.
  2. **Pipeline deterministica di sanificazione (`ingest-safe`)** che rimuove i PII *prima* della vettorizzazione e dell'archiviazione.
  3. **Gateway unificato per agenti e automazioni** (OCR, trascrizione, anonimizzazione e RAG dietro un'unica Bearer key e un unico registro di audit).
* **Copertura funzionale della Console amministrativa:** la Operations Console (`/console/`) rende immediata la dimostrazione live (readiness dei servizi, upload documenti con mascheramento PII, test RAG), ma la creazione e gestione delle Virtual Key rimane separata su `/admin/` (LiteLLM UI).
* **Compliance GDPR sui sub-responsabili esterni:** in fase di qualifica con DPO o uffici legali, il mascheramento locale con Presidio va accompagnato dai *Data Processing Agreement* (DPA) dei provider SaaS configurati (Groq, Hugging Face) con policy di *Zero Data Retention* attive.

---

## 4. Roadmap delle Priorità

| Priorità | Area | Azione concreta |
| :--- | :--- | :--- |
| **1. Alta** | **IT / Integrazione** | Validare su VPS reale i contratti HTTP di **Docling**, **Piper TTS** e degli endpoint **Hugging Face** (`BAAI/bge-m3` e `bge-reranker-v2-m3`) nel profilo `litellm-config.cloud.yaml`. |
| **2. Alta** | **Operations** | Implementare uno script/container di backup automatico (`pg_dump`) per `litellm_db` e `knowledge_db` e configurare la rotazione dei log Docker (`json-file` `max-size`). |
| **3. Media** | **IT / Performance** | Aggiungere un limite esplicito di dimensione file su `/v1/knowledge/ingest` e predisporre la creazione di indici vettoriali HNSW parziali su `pgvector` per collection oltre i 50.000 chunk. |
| **4. Media** | **Pre-Sales** | Strutturare una demo guidata di 5 minuti tramite Operations Console (`/console/`): verifica readiness $\rightarrow$ ingestione contratto con dati sensibili $\rightarrow$ verifica mascheramento Presidio $\rightarrow$ interrogazione RAG multi-tenant $\rightarrow$ verifica costi su `/admin/`. |