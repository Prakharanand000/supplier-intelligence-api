# Supplier Intelligence API

An AI-native third party risk investigation layer. It turns fragmented public
information into an evidence-backed intelligence object that an enterprise AI
agent can consume before onboarding, procurement, or investment decisions.

**Live demo:** <https://supplier-intelligence-api-1062146216736.us-central1.run.app>
(interactive UI, or `POST /api/v1/supplier/investigate`)

```
investigate_supplier("ABC Manufacturing Ltd")

  OFAC  SEC EDGAR  GLEIF  GDELT  CourtListener     (live, concurrent)
                     |
              Entity Resolution                    (who is this, really?)
                     |
                Evidence Layer                     (every claim is citable)
                     |
               Risk Signal Engine                  (explainable rules)
                     |
                Claude reasoning                   (summarize, never invent)
                     |
          Structured JSON  ->  AI agent decision
```

---

## Quick start

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -r requirements.txt
cp .env.example .env                                 # then set ANTHROPIC_API_KEY
docker compose up -d                                 # PostgreSQL (optional, see below)
uvicorn app.main:app --reload
```

Open <http://localhost:8000> for the demo UI, or <http://localhost:8000/docs>
for the OpenAPI console.

Run the three demo investigations end to end against live sources:

```bash
python -m scripts.demo
```

Run the offline test suite (no network, no database):

```bash
python -m pytest tests -q
```

### It runs without PostgreSQL

PostgreSQL is the intended datastore. If `DATABASE_URL` is unreachable at
startup, the app logs a warning and falls back to a local SQLite file at
`data/supplier_intel.db` with an identical schema, so the demo works on a
machine with nothing installed. Set `ALLOW_SQLITE_FALLBACK=false` to hard-fail
instead. `GET /api/v1/health` reports which backend is live.

### It runs without any paid API key

| Missing key | Effect |
| --- | --- |
| `ANTHROPIC_API_KEY` | Report is composed deterministically from the same evidence instead of by Claude. Everything else is unchanged. |
| `OPENAI_API_KEY` | Embeddings fall back to `sentence-transformers` if installed, else a pure-python hashed char-ngram vectorizer. Entity resolution never requires a paid API. |
| `COURTLISTENER_API_TOKEN` | Litigation is reported as a **coverage gap**, not as "no litigation". |

---

## The API

```
POST /api/v1/supplier/investigate
```

```json
{ "name": "ABC Manufacturing Ltd", "country": "United States", "website": "https://example.com" }
```

Returns `supplier`, `entity_resolution`, `ownership`, `sanctions`,
`adverse_media`, `litigation`, `risk`, `evidence`, `agent_summary`,
`sources_consulted`, and `duration_seconds`.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/v1/supplier/investigate` | Run an investigation |
| `GET /api/v1/investigations` | Recent investigations |
| `GET /api/v1/investigations/{id}` | Replay a stored intelligence object |
| `POST /api/v1/admin/ofac/refresh` | Force a re-download of the SDN list |
| `GET /api/v1/health` | Backend, embedding mode, SDN size |

---

## Data sources

All five are live. Nothing is mocked.

| Source | Used for | Notes |
| --- | --- | --- |
| **OFAC** | Sanctions screening | Full SDN list (~39,500 primary names + AKAs) downloaded, flattened into the database, and indexed in memory. Screening is local. |
| **SEC EDGAR** | US identity, filings, officers | Officers are the reporting owners parsed out of recent **Form 4** filings, with their stated officer title or director flag. Throttled under SEC's 10 req/s limit; every request carries the contact User-Agent SEC requires. |
| **GLEIF** | Legal identity, ownership | LEI, official legal name, jurisdiction, registered address, plus direct and ultimate parent relationships. |
| **GDELT** | Adverse media | Company name AND risk vocabulary, last 24 months, headline-scored for severity. |
| **CourtListener** | Litigation | Federal RECAP dockets. Degrades to an explicit coverage gap without a token. |

`OpenCorporates` and `VirusTotal` are **mocked** pending paid access. They are
flagged `"mocked": true` in the response, excluded from scoring, and the agent
prompt forbids citing them.

Every upstream response is cached in the database, so repeat investigations are
near-instant. Observed cold run: ~35s. Warm run: **under 7s**, against a 60s
target.

---

## Entity resolution

The highest-priority component, and the part that is not commodity data.

```
Raw entity -> Normalization -> Feature extraction -> Similarity -> Confidence -> Match
```

**Normalization** strips the noise registries disagree on: accents, punctuation,
dotted initialisms (`S.A.` -> `sa`), ~60 legal-form suffixes across
jurisdictions (`LLC`, `Ltd`, `GmbH`, `Sdn Bhd`, ...), and stopwords. So
`ABC Manufacturing LLC`, `ABC Manufacturing Ltd.` and `ABC Manufacturing GmbH`
all collapse to `abc manufacturing`.

**Five features**, each contributing only when both sides supply data:

| Feature | How it is computed |
| --- | --- |
| Name | Blend of Levenshtein ratio, Jaro-Winkler, and Jaccard token overlap. Both implemented in pure Python, not hidden behind a dependency. Scored against the legal name *and* every alias; best wins. |
| Embedding | Cosine over name + aliases + description. OpenAI, local MiniLM, or hashed char-ngram. |
| Address | Country match, refined by street-token overlap. |
| Website | Registrable domain, with partial credit for subdomains. |
| Ownership | Shared executives — **cross-source only**. |

**Confidence is never hardcoded.** Weights are renormalized over the features
that actually fired, so a match backed by name + website + ownership is scored
on those three rather than diluted by fields nobody published. Every response
carries the full breakdown and the weights used:

```json
"selected": {
  "name": "Apple Inc.", "confidence": 0.88,
  "confidence_breakdown": { "name": 1.0, "embedding": 0.56, "address": 1.0 },
  "weights_used": { "name": 0.533, "embedding": 0.267, "address": 0.2 },
  "explanation": "SEC record 'Apple Inc.' scored on: name 1.00 (w=0.53), ..."
}
```

Rejected alternatives are returned too, so an agent can see *why* one entity was
chosen over the similar ones.

One subtlety worth calling out: ownership overlap is only counted when the
corroborating officers come from a **different source** than the record being
scored. Scoring a record against its own officer list hands every candidate a
free 1.0 and inflates every confidence equally — which is exactly what it did
before it was fixed.

---

## Risk engine

Explainable rules, no ML model. Weights are flat and match the documented table
exactly:

| Signal | Points |
| --- | --- |
| OFAC sanctions match | 100 (scaled by match strength) |
| Litigation found | 30 |
| Adverse media | 20 (scaled by worst-allegation severity) |
| Identity unverified | 25 (scaled by confidence shortfall) |
| Ownership complexity | 15 |

Bands: `low` <30, `medium` 30-54, `high` 55-79, `critical` 80+.

Two deliberate modelling choices:

- **Litigation does not scale with docket count.** Docket volume tracks company
  size far more than company risk — Badger Meter, a mid-cap water-meter maker,
  has 166 federal dockets. Counting volume would put every large supplier in the
  top band. The count stays visible in the description and evidence for a human
  to weigh.
- **A source that failed is a coverage gap, not a clean bill of health.** If
  CourtListener cannot be reached, the response says so and adds risk, rather
  than reporting zero litigation.

`raw_score` is preserved alongside the capped `score` so the arithmetic stays
auditable.

---

## The evidence layer

Every investigation returns a flat, citable `evidence` array (`E1`, `E2`, ...)
carrying source, URL, and description. The agent prompt requires every
conclusion to cite evidence IDs and to write "No evidence available" rather than
infer. Claude receives only the evidence payload — it never fetches anything and
is explicitly told not to introduce outside facts. The response is constrained
by a JSON schema via structured outputs, so the shape is guaranteed.

---

## Demo companies

```bash
python -m scripts.demo
```

| | Company | Demonstrates |
| --- | --- | --- |
| 1 | Kesko Oyj (Finland) | Clean: verified via LEI, no sanctions, no litigation, no adverse media, risk 0 / low |
| 2 | Wells Fargo & Company | Risk positive: real federal dockets and negative coverage found |
| 3 | ABC Manufacturing | Entity resolution: no exact registrant exists, so the system returns `probable`/`unverified` with the scored alternatives it rejected, instead of guessing |

Demo 1 is deliberately not a US public company. Every large US registrant is
party to federal litigation, so "clean" can only be demonstrated on an entity
that genuinely has none — which is itself a finding about what this data can and
cannot tell you.

---

## Layout

```
app/
  main.py            FastAPI app, lifespan, OFAC warm-up
  pipeline.py        investigation engine (fan-out -> resolve -> risk -> report)
  config.py          settings, per-host rate limits
  db.py models.py    async SQLAlchemy, Postgres with SQLite fallback
  http_client.py     rate limiting, retries, DB-backed response cache
  sources/           ofac, sec, gleif, gdelt, courtlistener, optional_sources
  resolution/        normalize, similarity, embeddings, engine
  risk/engine.py     explainable rule scoring
  agent/             prompts + Claude investigator
  api/v1.py          routes
static/index.html    demo UI
scripts/demo.py      end-to-end demo runner
tests/               offline tests for resolution and risk
```

---

## The interface

Three stages, following the workflow an analyst actually uses.

**1 &middot; Subject intake.** Organization or individual. Name, aliases, date of
birth, address, city, country, registration number, website. Only the name is
required; everything else sharpens entity resolution and suppresses false
positives.

**2 &middot; Risk dashboard.** KPI tiles, then adverse media tagged against an
11-category risk taxonomy (Financial Crime, Bribery & Corruption, Sanctions,
Criminal Proceedings, Litigation, Regulatory, Cyber, Environmental, Labor &
Human Rights, Product Safety, Governance). Each category is a clickable filter
chip with its own count, alongside a high-severity toggle and a monthly volume
timeline. Sanctions, litigation, ownership and the agent report sit below.

**3 &middot; Network drill-down.** Three force-directed graphs:

| Graph | What it shows |
| --- | --- |
| Entity resolution | Query at the centre, every candidate scored around it. Click a node for its per-feature breakdown and the weights used - this is the "why this one and not that one" view. |
| Ownership network | Officers, directors and corporate parents of the resolved entity. |
| Transaction network | Insiders trading against the issuer, sized by filing count and coloured by net direction. |

The layout is ~30 lines of force-directed simulation rather than a charting
library, so the page stays dependency-free and works offline.

### On the transaction graph

**These are real filed transactions, not simulated payment flows.** We have no
payments data and do not invent any. The transaction network is built from
**SEC Form 4** filings - reported securities transactions by named insiders,
carrying date, transaction code (open-market purchase, sale, grant, option
exercise, tax withholding, gift), share count and price - parsed from the XML
documents already fetched for officer names. Non-US entities have no Section 16
filing obligation, so the graph is empty for them and says so.

### Screening an individual

Supplying a date of birth changes the outcome rather than decorating it. A name
hit whose DOB corroborates stays at 100/critical; a hit whose listed DOB
conflicts is demoted to 70/high and labelled a likely namesake for manual
review. It is not cleared outright, because aliases and incomplete records
exist.

Name matching compares token-sorted forms as well as the given order, because
sanctions lists write people surname-first (`NASRALLAH, Hasan`) while users type
them forename-first. Without that, an exact match scored 0.67 and was missed
entirely.

---

## Deployment

### Google Cloud Run (what the live demo runs on)

```bash
gcloud run deploy supplier-intelligence-api \
  --source . --region us-central1 --allow-unauthenticated \
  --memory 1Gi --timeout 300 \
  --set-env-vars "DATABASE_URL=sqlite+aiosqlite:////tmp/supplier_intel.db,USER_AGENT=YourApp/0.1 (you@example.com)"
```

**Expect ~40s per request on this setup, against ~1-6s locally.** Cloud Run's
`/tmp` is per-instance and in-memory, so an instance that has just started has
an empty database and re-downloads the 5.6 MB SDN list before it can screen.
The architecture assumes a shared PostgreSQL instance; without one, the OFAC
cache cannot outlive a container. Two ways to fix it:

- Point `DATABASE_URL` at any managed PostgreSQL (Neon, Supabase and Render all
  have free tiers). The OFAC list and the HTTP cache then persist across
  instances and requests drop back to a few seconds.
- Or `--min-instances 1` to keep one warm instance, which trades a small
  ongoing cost for latency.

### Render (provisions PostgreSQL for you)

`render.yaml` is a complete blueprint. In the Render dashboard: **New ->
Blueprint -> select this repo**. It creates the web service and a free
PostgreSQL instance and wires `DATABASE_URL` automatically; you supply
`ANTHROPIC_API_KEY` at deploy time so it never enters the repository.

### Docker

```bash
docker build -t supplier-intel .
docker run -p 8000:8000 --env-file .env supplier-intel
```

> The live demo has no `ANTHROPIC_API_KEY` set, so it serves the deterministic
> report. Add one with
> `gcloud run services update supplier-intelligence-api --update-env-vars ANTHROPIC_API_KEY=sk-ant-...`
> and Claude takes over with no other change.

---

## Known limits

- **Adverse media precision** is the weakest link. The filter requires every
  token of the company name in the headline and drops automated market-wire
  copy (analyst ratings, price targets, stake changes), but a single-token name
  like "Apple" still admits articles where the company is mentioned rather than
  accused. Headline-only tagging is a blunt instrument — article-body scoring
  would be the next improvement.
- **The transaction graph is US-only**, since Form 4 is a Section 16
  obligation. There is no payments or invoice data in this system and none is
  simulated.
- **GDELT rate-limits aggressively** (one request per ~5s per IP) and will
  intermittently return no articles under load.
- **Officer extraction is US-only**, since it depends on SEC Form 4. Non-US
  suppliers resolve identity and ownership via GLEIF but return no executives.
- **OpenCorporates and VirusTotal are mocked** and excluded from scoring.
