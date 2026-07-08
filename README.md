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

Run this after installation and before the first use on a new machine:

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

The preferred delivery path is a Streamlit Community Cloud link, with ZIP/local delivery kept as backup.

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

For link-based access, you can optionally protect the app with a simple access code. Set either `EU_FUNDING_ACCESS_CODE` or `access_code` in Streamlit secrets. If no access code is configured, the app opens normally; there is no hard-coded password in the repository.

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
python scripts/import_calls.py --replace
```

Audit the main CSV:

```powershell
python scripts/audit_dataset.py
```

For permanent dataset refreshes, use the GitHub Actions workflow:

- GitHub -> **Actions** -> **EU Call Library Refresh** -> **Run workflow**
- Keep `target_active` at `300` for the normal working library.
- Review and merge the pull request only after checking the dataset diff and QA result.

This is the preferred path for the hosted Streamlit app because the refreshed CSV and SQLite files are committed through GitHub. A local Streamlit runtime update may not persist after reboot.

For local admin maintenance, run the same refresh pipeline with one command:

```powershell
python scripts/refresh_call_library.py --target-active 300 --skip-live-api --apply --qa full
```

To preview the refresh without modifying the main CSV or SQLite:

```powershell
python scripts/refresh_call_library.py --target-active 300 --skip-live-api --qa none
```

The refresh pipeline fetches official EU records, creates staging and candidate files, enriches only explicitly supported metadata, removes expired calls from the active library, rebuilds SQLite, and writes backups before applying local changes. See [`docs/monthly_dataset_operations.md`](docs/monthly_dataset_operations.md).

After each refresh, the workflow also runs the saved Gillis watchlist in [`data/watchlist/gillis_watchlist.json`](data/watchlist/gillis_watchlist.json). The pull request includes a short report showing which tracked themes gained new reviewable calls.

To run that report locally:

```powershell
python scripts/run_watchlist_report.py --previous-csv data/evaluation_outputs/calls_seed_clean_before_refresh.csv
```

To enrich priority active calls already in the working library without changing the main dataset:

```powershell
python scripts/enrich_priority_call_metadata.py --limit 40
```

This writes `data/imports/calls_seed_priority_enriched_candidates.csv` and `data/evaluation_outputs/priority_call_metadata_enrichment_log.json`. It is intended for official-evidence review before any later promotion.

In internal mode, the app also includes dataset refresh and staging review panels. The refresh panel can preview or apply the local refresh pipeline, while the review panel lets a maintainer inspect staging or promotion-candidate files, mark records as `approve`, `hold`, or `reject`, and write:

- `data/imports/eu_calls_approved_promotion.csv`
- `data/evaluation_outputs/eu_calls_approval_log.json`

This approval export still does not update `calls_seed_clean.csv` or `data/eu_funding.sqlite` by itself. Permanent hosted updates should go through the GitHub Actions pull request flow.

## Practical screening support

Result details now include lightweight support layers for the first strategic steps after a match:

- Partner needs to check: suggested partner roles and outreach focus, based only on the project and call text.
- Optional curated partner-directory matching when `data/imports/partner_directory.csv` is configured.
- Concept note starter: a call-fit angle, proposal structure, missing information to clarify, and evidence to collect before proposal drafting.
- Proposal readiness memo: strongest starting points, gaps to close, and first preparation actions.

These are drafting aids, not eligibility confirmation. LLM-based proposal generation is intentionally not enabled until API-key handling, privacy expectations, and source-grounding rules are agreed.

For partner-directory setup, see [`docs/partner_directory.md`](docs/partner_directory.md).

## Current dataset status

As of July 6, 2026:

- 275 records in the working call library
- 275 active or upcoming calls available for default screening
- Standard refresh target: up to 300 active or upcoming calls, depending on official API availability and quality filters
- Expired records are removed from the active library and archived during promotion
- Semantic matching verified in the current environment
- Theme and input-quality guardrails enabled
- Client-facing port/harbour display prioritisation enabled for explicit port-side projects
- Deadline tracking highlights active calls closing within 90 days
- Monthly dataset refresh workflow available through GitHub Actions

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

## Operational review

Use [`docs/client_review_questions.md`](docs/client_review_questions.md) during review sessions. Capture the project input, useful and irrelevant results, missing opportunity areas, explanation quality, status clarity, and PDF usefulness. Specific examples are more valuable than general impressions.

For a repeatable delivery check, follow [`docs/release_checklist.md`](docs/release_checklist.md).

For the recommended long-term build order, see [`docs/product_evolution_plan.md`](docs/product_evolution_plan.md).
