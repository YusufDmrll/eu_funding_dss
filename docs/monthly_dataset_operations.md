# Monthly Dataset Operations

This workflow keeps the working call library broad, current, and safe without blindly importing every EU Portal record.

## Current operating target

- Working library target: 250-300 active/upcoming calls.
- Current configured refresh target: 300 active/upcoming calls.
- Expired calls are removed from the active library and archived locally during promotion.
- The app continues to use deadline-aware filtering, so expired calls should not appear as current opportunities.

## Recommended one-click process

For permanent hosted updates, use GitHub Actions:

1. Open the repository on GitHub.
2. Go to **Actions**.
3. Select **EU Call Library Refresh**.
4. Click **Run workflow**.
5. Keep `target_active` at `300` unless there is a specific reason to change it.
6. Leave QA at `full` for normal refreshes.
7. Review the pull request that the workflow opens.
8. Merge only if the CSV diff and QA summary look reasonable.

After the PR is merged, Streamlit Cloud redeploys from the updated dataset and SQLite files.

This is the safest "single-click" update path because changes are committed through GitHub rather than written only to a temporary Streamlit runtime.

## What the refresh pull request shows

Each refresh pull request includes an automatic change summary:

- rows before and after refresh;
- active/upcoming records after refresh;
- added, removed/archived, and modified records;
- added-record theme mix;
- metadata gaps in newly added records;
- automated quality flags;
- examples of added and removed/archived calls.

The pull request also includes a Gillis watchlist report. This checks the saved project themes in `data/watchlist/gillis_watchlist.json` against the refreshed active call library and highlights newly added calls that are worth reviewing.

Use the change summary first, then the watchlist report, then inspect the CSV diff if something looks off.

## Local maintenance command

For local admin maintenance, the same pipeline can be run with one command:

```powershell
python scripts/refresh_call_library.py --target-active 300 --skip-live-api --apply --qa full
```

To preview the update without touching the main CSV or SQLite:

```powershell
python scripts/refresh_call_library.py --target-active 300 --skip-live-api --qa none
```

Preview mode writes staging, recommendation, candidate, enrichment, and refresh logs only.

To run the watchlist report locally after a refresh preview or apply run:

```powershell
python scripts/run_watchlist_report.py --previous-csv data/evaluation_outputs/calls_seed_clean_before_refresh.csv
```

If no previous snapshot is available, omit `--previous-csv`; the report will still show the best current matches, but it will not flag newly added calls.

## Automated GitHub workflow

The repository includes `.github/workflows/monthly-dataset-refresh.yml`.

It runs on the first day of each month and can also be started manually from GitHub Actions. The workflow:

- fetches open/forthcoming Horizon Europe records from the official EU Funding & Tenders Search API;
- filters and reviews records against Gillis-relevant themes;
- enriches only explicitly supported metadata from retained official text;
- removes expired calls from the active library;
- rebuilds SQLite from the refreshed CSV;
- runs the configured QA checks;
- runs the Gillis watchlist report;
- opens a pull request if `data/imports/calls_seed_clean.csv` or `data/eu_funding.sqlite` changed.

The workflow does not auto-merge. That is intentional. A pull request should be reviewed before the live Streamlit app receives the refreshed dataset.

## Promotion quality rules

The monthly process should not add calls just to increase the count.

Records are held back when they are:

- expired or invalid-deadline records;
- missing required title, description, deadline, or official source URL;
- duplicates of existing call IDs;
- off-theme health, food, culture, biodiversity, or agriculture records unless clearly relevant to Gillis priorities;
- broad AI/digital/SME records without a clear industry, infrastructure, energy, security, transport, or materials link.

Uncertain metadata remains blank. Do not infer TRL, eligibility, consortium requirements, partner counts, budgets, or funding probability.

## After merging a monthly refresh PR

Before sharing the refreshed app:

```powershell
python -m unittest discover -s tests
python scripts/check_semantic_stack.py
python scripts/run_gillis_retrieval_quality_audit.py
```

Then test at least:

- critical raw materials / battery recovery;
- port shore power / green harbour;
- maritime logistics optimisation;
- critical infrastructure security;
- SME/start-up innovation support.

If retrieval quality worsens, do not tune blindly. Review the newly added records first.
