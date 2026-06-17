# EU Funding Match

## What this app does

EU Funding Match is a client-facing Streamlit application for early-stage screening of project ideas against curated Horizon Europe funding calls. It identifies calls worth reviewing, explains the thematic connection, highlights strategic gaps, proposes practical next steps, and exports a concise PDF screening summary.

The application supports early-stage decision-making. Fit scores are review signals, not funding probabilities or final eligibility decisions.

## Install

Use Python 3.11 and create a local virtual environment. The project does not include a developer virtual environment.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## First semantic health check

Run this after installation and before the first feedback session:

```powershell
python scripts/check_semantic_stack.py
```

The check loads `all-MiniLM-L6-v2`, encodes sample text, and verifies cosine similarity. Semantic matching is the normal retrieval path; lexical matching remains available as a safe internal fallback if the local semantic stack cannot load.

## Run

```powershell
streamlit run app/streamlit_app.py
```

Recommended first session:

1. Open the local Streamlit URL.
2. Paste one of the examples from [`docs/demo_project_inputs.md`](docs/demo_project_inputs.md).
3. Review the shortlist, explanations, cautions, and next actions.
4. Open the official call source for promising results.
5. Export the PDF summary.

## Share as a web app

The preferred Gillis feedback path is a Streamlit Community Cloud link, with ZIP/local delivery kept as backup.

Deploy from GitHub with:

- Entry point: `app/streamlit_app.py`
- Dependencies: `requirements.txt`
- Runtime data included in the repository:
  - `data/eu_funding.sqlite`
  - `data/imports/calls_seed_clean.csv`
- Client mode: default, with no environment variable required

The first semantic matching run on Streamlit Cloud can be slower while the model initializes. See [`docs/streamlit_cloud_deployment.md`](docs/streamlit_cloud_deployment.md) for the deployment checklist and fallback plan.

## Client and internal modes

The application starts in client mode by default. Client mode hides raw dataset tables, reload controls, and maintenance tools.

For local dataset maintenance, start Streamlit with internal mode explicitly enabled:

```powershell
$env:EU_FUNDING_INTERNAL_MODE="1"
streamlit run app/streamlit_app.py
```

Unset the environment variable before a client session. Internal mode does not change retrieval, scoring, or dataset content; it only exposes maintenance controls.

## Dataset import and updates

The normal application uses:

- `data/imports/calls_seed_clean.csv`
- `data/eu_funding.sqlite`

Initialize and import the current working call library:

```powershell
python scripts/init_db.py
python scripts/import_calls.py
```

Audit the main CSV:

```powershell
python scripts/audit_dataset.py
```

To discover possible additions from the official EU Funding & Tenders Search API:

```powershell
python scripts/expand_dataset_from_eu_api.py --dry-run
python scripts/expand_dataset_from_eu_api.py --write-staging --write-recommended
```

The expansion script creates staging and review files. It does **not** automatically modify the curated CSV or SQLite database. New records must be reviewed, enriched only from official evidence, backed up, audited, and explicitly promoted before import.

## Current dataset status

As of June 15, 2026:

- 100 records in the working call library
- 85 active or upcoming calls shown by default
- 15 expired records retained as historical data and hidden by default
- Semantic matching verified in the current environment
- Theme and input-quality guardrails enabled
- Client-facing port/harbour display prioritisation enabled for explicit port-side projects

Call details should still be checked against official EU documents before proposal decisions.

## Known limitations

- Eligibility, consortium, and TRL details remain incomplete where official evidence was not explicit.
- Broad or under-specified descriptions can produce adjacent rather than project-specific opportunities.
- Strongest current coverage is in critical materials, battery circularity, port energy, maritime infrastructure, and critical-infrastructure security.
- SME/start-up support, broad innovation ecosystems, hydrogen shortlist tails, and cross-sector inputs need closer human review.
- A high fit or relevance score does not indicate funding probability or guaranteed eligibility.
- Client display ordering may promote a directly evidenced port/harbour call over an adjacent ship-side call; raw retrieval similarity and Strategic Fit Score remain unchanged.

## Tests and evaluation

```powershell
python -m unittest discover -s tests
python scripts/run_gillis_retrieval_quality_audit.py
```

## Giving feedback

Use [`docs/gillis_feedback_questions.md`](docs/gillis_feedback_questions.md) during testing. Capture the project input, useful and irrelevant results, missing opportunity areas, explanation quality, status clarity, and PDF usefulness. Specific examples are more valuable than general impressions.

For a repeatable delivery check, follow [`docs/release_checklist.md`](docs/release_checklist.md).
