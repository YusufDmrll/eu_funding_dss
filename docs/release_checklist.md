# Gillis Feedback Release Checklist

Complete this checklist on the machine used for the feedback session.

## Clean installation

- [ ] Confirm Python 3.11 is available.
- [ ] Create a fresh virtual environment: `python -m venv .venv`
- [ ] Activate it: `.\.venv\Scripts\Activate.ps1`
- [ ] Upgrade pip: `python -m pip install --upgrade pip`
- [ ] Install dependencies: `python -m pip install -r requirements.txt`

## System verification

- [ ] Run semantic health check: `python scripts/check_semantic_stack.py`
- [ ] Confirm the output ends with `Semantic stack check: OK`.
- [ ] Initialize the database if required: `python scripts/init_db.py`
- [ ] Import the working call library: `python scripts/import_calls.py`
- [ ] Confirm 100 calls are upserted.
- [ ] Run tests: `python -m unittest discover -s tests`
- [ ] Confirm all tests pass.

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
- [ ] Export a PDF summary.
- [ ] Open the PDF and check titles, wrapping, scores, cautions, source links, and page breaks.

## Feedback-session readiness

- [ ] Keep `docs/gillis_feedback_questions.md` available during the session.
- [ ] Record the exact project descriptions used.
- [ ] Record useful, irrelevant, and missing results.
- [ ] Note any status or explanation that feels too confident.
- [ ] Save one representative PDF for review.
- [ ] Do not modify the call library during the feedback session.
