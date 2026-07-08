# Gillis Release Checklist

Complete this checklist before sharing or updating the live application.

## Clean installation

- [ ] Confirm Python 3.11 is available.
- [ ] Create a fresh virtual environment: `python -m venv .venv`
- [ ] Activate it: `.\.venv\Scripts\Activate.ps1`
- [ ] Upgrade pip: `python -m pip install --upgrade pip`
- [ ] Install dependencies: `python -m pip install -r requirements.txt`
- [ ] If sharing a public link, decide whether to set `EU_FUNDING_ACCESS_CODE` in Streamlit secrets.

## System verification

- [ ] Run semantic health check: `python scripts/check_semantic_stack.py`
- [ ] Confirm the output ends with `Semantic stack check: OK`.
- [ ] Initialize the database if required: `python scripts/init_db.py`
- [ ] Import the working call library: `python scripts/import_calls.py --replace`
- [ ] Confirm the imported call count matches the working library, normally 250-300 active/upcoming calls.
- [ ] Run tests: `python -m unittest discover -s tests`
- [ ] Confirm all tests pass.
- [ ] Optional local preview only: `python scripts/refresh_call_library.py --target-active 300 --skip-live-api --qa none`
- [ ] Confirm preview mode did not modify the main CSV or SQLite database.
- [ ] For a monthly refresh, use **GitHub Actions -> EU Call Library Refresh -> Run workflow**.
- [ ] Confirm the refreshed active library remains between 250 and 300 active/upcoming calls.
- [ ] Review the generated Gillis watchlist report in the refresh pull request.
- [ ] Optional metadata enrichment candidate check: `python scripts/enrich_priority_call_metadata.py --limit 40 --skip-live-api`
- [ ] Confirm enrichment output is separate from the main call library.
- [ ] If reviewing new API records, use internal mode to create `eu_calls_approved_promotion.csv`; do not promote records during a client session.

## Application check

- [ ] Start the app: `streamlit run app/streamlit_app.py`
- [ ] Confirm the page opens without import or DLL errors.
- [ ] Run the semantic health check before the session. If you need an in-app method indicator, enable internal mode locally and confirm semantic matching is active.
- [ ] Confirm `Internal data and maintenance` is not visible in the client session.
- [ ] Test at least three strong examples from `docs/demo_project_inputs.md`.
- [ ] Test one weak example and confirm the output remains cautious.
- [ ] Confirm expired calls are hidden from default results.
- [ ] Open at least one official source link.
- [ ] Confirm the port shore-power example presents `Green, circular and resilient harbours` before adjacent ship-side topics.
- [ ] Open supporting details and review the fit strengths, clarification points, and call-specific next steps.
- [ ] Open supporting details and review partner needs plus the concept-note starter.
- [ ] Export a PDF summary.
- [ ] Open the PDF and check titles, wrapping, scores, cautions, source links, and page breaks.

## Client-use readiness

- [ ] Keep `docs/client_review_questions.md` available during review sessions.
- [ ] Record the exact project descriptions used.
- [ ] Record useful, irrelevant, and missing results.
- [ ] Note any status or explanation that feels too confident.
- [ ] Save one representative PDF for review.
- [ ] Do not modify the call library during a client session.
