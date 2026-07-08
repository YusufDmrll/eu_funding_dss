# Product Evolution Plan

This plan is for turning EU Funding Match from a strong working screening application into a longer-running company tool. The priority is not more features for their own sake. The priority is better coverage, safer updates, stronger client value, and repeatable operational reliability.

## Product direction

EU Funding Match should remain a focused decision-support tool:

1. Enter a project idea.
2. Review the strongest active funding matches.
3. Understand why they matter and what needs checking.
4. Move into partner, proposal, and official-source review with less manual work.

It should not become a broad grant-management platform until the screening, dataset, and reporting layers are consistently strong.

## Recommended build order

### 1. Dataset operations and approval workflow

Highest impact. The product becomes more valuable when the active call library is broader, fresher, and easier to maintain without corrupting the main dataset.

Build next:

- Scheduled or one-command EU API fetch into staging.
- Internal review table for new/changed/expired calls. Current status: an internal Streamlit review panel can inspect staging/candidate files and create an approved promotion CSV.
- Approval step before promotion into the main CSV and SQLite database. Current status: approval export is separate from promotion; main dataset changes still require explicit backup, audit, and import.
- Change log showing added calls, removed/archived calls, deadline changes, and source changes.
- Dataset QA gate before import: duplicates, invalid deadlines, missing source URLs, encoding issues, and weak descriptions.

Do not auto-promote API records into the client-facing dataset without review.

### 2. Official metadata enrichment for priority themes

The biggest trust gap is still incomplete eligibility, TRL, consortium, and partner metadata. Enrich the calls most likely to be used first rather than trying to perfect every record.

Current support:

- `scripts/enrich_priority_call_metadata.py` selects active priority-theme records with missing metadata.
- It writes a separate enrichment candidate CSV and evidence log.
- It does not modify `calls_seed_clean.csv` or SQLite.
- Enriched candidates can be inspected in the internal dataset staging review panel before any later promotion.

Priority themes:

- Critical raw materials, batteries, recycling, circularity.
- Port energy, shore power, green harbour infrastructure.
- Hydrogen infrastructure where the call scope is direct.
- Maritime logistics and supply-chain resilience.
- Security, resilience, critical infrastructure.
- SME/start-up support only where the call is genuinely about company support, not just sector technology.

Enrich only from official EU source evidence. Leave uncertain fields blank.

### 3. Call lifecycle and deadline intelligence

The app already hides expired calls and counts calls closing within 90 days. The next step is to make lifecycle changes operationally useful.

Build next:

- "Closing soon" grouping for active calls.
- "New since last update" and "Changed since last update" flags.
- Deadline-change detection in update logs.
- Internal reminder/export for calls needing near-term review.
- Clear archive behavior for expired calls.

This should stay deterministic and source-based.

### 4. Partner matching support

Partner matching is valuable, but it should start as role-based and evidence-based before becoming a full discovery engine.

Build next:

- Partner role taxonomy by theme: port authority, terminal operator, energy provider, materials processor, manufacturer, research partner, security operator, logistics operator, SME/scale-up.
- Optional manually curated partner directory with organisation name, country, sector, role, themes, and notes.
- Match project + call to partner roles first, then to known organisations if available.
- Export partner needs in the PDF and concept-note starter.

Avoid blind web scraping of organisations until privacy, source quality, and maintenance rules are clear.

### 5. Proposal preparation assistant

The safest useful version is template-based, not open-ended LLM generation.

Build next:

- Call-specific concept note outline.
- Problem, solution, users, EU relevance, expected impact, TRL, partner roles, and evidence checklist.
- Gap analysis: what is missing from the project description before proposal work.
- Call-fit memo export for internal review.
- Optional "proposal readiness checklist" per call.

LLM proposal generation should wait until API keys, data privacy, source-grounding, and review rules are agreed.

### 6. Retrieval quality monitoring

As the dataset grows, quality can regress. Keep a standing QA harness.

Build next:

- Expand Gillis-focused evaluation cases from 14 to 30-40.
- Keep adversarial tests: vague input, logs, unrelated sectors, generic AI, broad green innovation.
- Track top-1 quality, top-3 defensibility, expired results, over-optimistic statuses, weak explanations, and off-theme drift.
- Add a small internal "mark result as irrelevant/useful" capture mechanism for real usage notes.

Do not tune thresholds blindly without before/after audit outputs.

### 7. Cloud and access hardening

The current access-code gate is enough for controlled use. More security should be added only when usage grows.

Build next if needed:

- Streamlit secrets-based access code for the live app.
- Simple operational runbook for reboot, logs, dependency failures, and semantic model cold start.
- Backup and restore instructions for CSV and SQLite.
- Optional lightweight usage log that does not store sensitive project descriptions unless explicitly approved.

Full user accounts and multi-user dashboards should wait until there are multiple recurring users with different access needs.

## What not to build yet

- Full grant-management dashboard.
- Success-probability prediction.
- Automated final eligibility decisions.
- Blind partner scraping.
- Unreviewed mass import into the main dataset.
- LLM proposal generation without privacy and source-grounding rules.
- Multi-user workspace unless Gillis needs it operationally.

## Next recommended sprint

Build the internal dataset operations workflow:

1. Run the official EU API expansion script.
2. Show staged records in an internal Streamlit review page.
3. Allow approve/hold/reject decisions.
4. Produce an approved promotion CSV.
5. Run audit, backup, import, and retrieval QA before the main dataset changes.

This is the strongest next step because it improves long-term usefulness without weakening the current screening experience.
