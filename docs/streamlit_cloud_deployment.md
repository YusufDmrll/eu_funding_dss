# Streamlit Community Cloud Deployment

This guide prepares `EU Funding Match` for link-based client access through Streamlit Community Cloud.

## Deployment Readiness

Current repository status:

- App entry point: `app/streamlit_app.py`
- Python dependencies: `requirements.txt` at the repository root
- Streamlit config: `.streamlit/config.toml`
- Runtime data files:
  - `data/eu_funding.sqlite`
  - `data/imports/calls_seed_clean.csv`
- Current working library: 275 active/upcoming calls; the standard refresh target is up to 300.
- Client mode is the default. No environment variable is needed for the normal client experience.
- Internal maintenance controls appear only when `EU_FUNDING_INTERNAL_MODE=1`.
- Optional access-code protection is available through Streamlit secrets.

The app uses project-relative paths, so it should not depend on a local Windows file path.

## Prepare GitHub

1. Create a GitHub repository for the project.
2. Commit the source code, documentation, requirements, Streamlit config, and runtime data files.
3. Do not commit `.venv/`, temporary exports, cache folders, or local-only files.
4. Confirm these files are present in GitHub:
   - `app/streamlit_app.py`
   - `core/`
   - `data/eu_funding.sqlite`
   - `data/imports/calls_seed_clean.csv`
   - `.streamlit/config.toml`
   - `requirements.txt`
   - `README.md`

## Deploy on Streamlit Community Cloud

1. Open [Streamlit Community Cloud](https://share.streamlit.io/).
2. Connect the GitHub account that owns the repository.
3. Select the repository and branch.
4. Set the main file path to:

```text
app/streamlit_app.py
```

5. If the deployment dialog allows Python version selection, choose Python 3.11 to match the tested environment.
6. If you want a simple access gate, add one Streamlit secret:

```toml
EU_FUNDING_ACCESS_CODE = "choose-a-private-code"
```

You can also use `access_code = "choose-a-private-code"`. Do not commit the code to GitHub.
7. Deploy and watch the build logs.

## First Run Expectation

The first semantic matching run may be slower than local use because the environment must install `torch`, install `sentence-transformers`, and download the `all-MiniLM-L6-v2` model.

Expected behavior:

- The app page should open in client mode.
- If an access code was configured, the first screen asks for that code before the screening tool opens.
- The first screening run may take longer while the semantic model initializes.
- The user should see the app's normal loading message: `Reviewing active calls...`
- If the semantic stack cannot load on the cloud environment, the app should continue with baseline text matching and show a cautious fallback message.

## Test the Deployed Link

After deployment, test the link before sharing it:

1. Open the Streamlit URL in a clean browser session.
2. Confirm the first page is client-facing and does not show internal maintenance controls.
3. Use one strong sample from `docs/demo_project_inputs.md`.
4. Confirm results appear for:
   - critical raw materials / battery recovery
   - port shore power / green harbour
   - critical infrastructure security
5. Confirm expired calls do not appear in default results.
6. Open at least one official source link.
7. Export a PDF summary and check that it downloads correctly.
8. Confirm the PDF has a readable title, source links, review statuses, and no placeholder project title.

## Share With Gillis

Send Gillis:

- The deployed Streamlit link.
- A short note that this is an early-stage EU funding screening tool for active Horizon Europe calls.
- `docs/demo_project_inputs.md` or 2-3 suggested project descriptions to try.
- `docs/client_review_questions.md` for structured review notes.

Recommended message:

```text
Here is the EU Funding Match link. Please test it with realistic multi-sentence project ideas, especially around critical materials, port/harbour energy, maritime infrastructure, security, and SME/start-up innovation. The output is intended as an early screening shortlist and should be checked against official EU call documents before proposal decisions.
```

## If Cloud Resource Limits Fail

If Streamlit Community Cloud cannot install or load the semantic stack reliably:

1. Check the Streamlit build/runtime logs.
2. Reboot or redeploy the app once.
3. Confirm Python 3.11 was selected if the option is available.
4. Confirm `requirements.txt` includes `torch` and `sentence-transformers`.
5. If semantic loading still fails, use the ZIP/local delivery path as the backup for Gillis.
6. If Gillis needs always-on availability, stronger privacy controls, or heavier usage, consider a stronger hosted environment after the initial Streamlit Cloud deployment.

Do not remove semantic matching from the project just to fit a constrained cloud runtime. Semantic matching is the verified default path for the current product quality.

## Monthly Data Refresh

The repository includes a scheduled GitHub Actions workflow:

```text
.github/workflows/monthly-dataset-refresh.yml
```

It refreshes the active call library from the official EU Funding & Tenders Search API and opens a pull request when the dataset or SQLite file changes. Use **Actions → EU Call Library Refresh → Run workflow** for a manual one-click refresh. Review and merge that pull request only after checking the dataset audit and the Gillis retrieval quality audit.

## Official References

- [Deploy your app on Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app)
- [File organization for Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization)
- [App dependencies for Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
- [Upgrade Python on Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/upgrade-python)
