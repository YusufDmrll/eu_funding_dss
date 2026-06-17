# Gillis Client-Alignment Audit

Audit date: 15 June 2026

## Executive finding

The current system is a credible supervised funding-screening product, but it does not yet cover the full Gillis vision. It is strongest at identifying active Horizon Europe calls, producing a cautious shortlist, and giving an initial screening explanation. It is not yet a partner-building, proposal-development, or success-pattern platform.

The main release question is therefore not whether the full vision is complete. It is whether the current screening scope is useful and honest enough for a supervised Gillis feedback session. The answer is now yes. The product-upgrade sprint resolved the two release blockers identified during this audit: internal maintenance controls are gated behind an explicit internal mode, and the core port shore-power scenario now presents direct harbour relevance before adjacent ship-side topics.

## Post-sprint status

- Default client mode hides maintenance, reload, and raw-data controls.
- The first semantic run has a clear, non-technical progress state.
- Port-side display priority and ship-side caution are deterministic and tested.
- Result details now include review-status rationale, alignment strengths, missing information, and practical next steps.
- PDF summaries include the same clarifications and next-step guidance.
- Updated Gillis audit: 14/14 semantic mode, 13/14 top-1 pass, 35/42 relevant top-3 results, zero expired results, zero weak explanations, and zero over-optimistic statuses.

## Sources reviewed

- `AI driven EU fund strategy.pdf`
- `Pilot EU grants innovation - the EU grant process (2).docx`
- `AI-Driven EU Funding Match & Strategy System (3).pdf`
- `README.md`
- `docs/demo_project_inputs.md`
- `docs/gillis_feedback_questions.md`
- `docs/release_checklist.md`
- `data/evaluation_outputs/gillis_retrieval_quality_summary.md`
- `data/evaluation_outputs/gillis_retrieval_quality_report.json`
- `data/evaluation_outputs/dataset_audit_summary.json`
- `data/evaluation_outputs/eu_calls_promotion_enrichment_log.json`
- `data/evaluation_outputs/gillis_feedback_screening_summary.pdf`
- Current Streamlit application and core screening modules
- Live screening flow tested with the port shore-power example

## Gillis's real requirements

The client materials describe a staged vision rather than one single feature list.

### Immediate operational need

- Organise access to innovation financing for start-ups, scale-ups, and SMEs.
- Make funding identification quick, effective, and precise.
- Focus first on maritime innovation, security, critical materials, and green energy.
- Start with critical materials if a narrower initial focus is required.
- Match project ideas against relevant EU calls and reduce manual research time.
- Help users move from call identification into the next practical steps.

Evidence: `AI driven EU fund strategy.pdf`, pages 1-2.

### Screening information expected

- Call title and reference.
- Objectives and priorities.
- Budget and funding rate.
- Deadline.
- Evaluation criteria and expected impact.
- Eligibility conditions.
- Submission guidance and official documents.
- Consortium implications and partner readiness.

Evidence: `Pilot EU grants innovation - the EU grant process (2).docx`, sections "Stage 1: Identification of suitable calls", "Understanding the eligibility criteria", and "Process after identification of call for proposals".

### Wider process support expected later

- Partner search and consortium building.
- Proposal summary and project-definition support.
- Objectives, expected outcomes, work packages, milestones, risks, and budget planning.
- Analysis of past funded projects and successful proposal patterns.
- Automated alerts for new calls.
- Proposal weakness detection.
- Stakeholder mapping and policy intelligence.

Evidence: `AI driven EU fund strategy.pdf`, page 2; `Pilot EU grants innovation - the EU grant process (2).docx`, proposal-preparation sections.

### Agreed product phasing

The project concept document places matching, scoring, strategic outputs, dashboard use, and report download in the pilot. Partner matching, automated updates, proposal improvement, and success-probability modelling are explicitly described as later phases.

Evidence: `AI-Driven EU Funding Match & Strategy System (3).pdf`, pages 2-5.

## Current product evidence

- 100 curated Horizon Europe records.
- 85 active or upcoming records; 15 expired records retained but hidden by default.
- No invalid deadlines, duplicate call IDs, missing source URLs, or detected encoding artifacts.
- Semantic retrieval ran in 14/14 Gillis evaluation cases without lexical fallback.
- Current test suite: 72 tests passed.
- Input-quality, non-project-input, and theme-coherence guardrails are present.
- Client-facing statuses are `Strong match`, `Worth reviewing`, and `Needs more detail`.
- Results include active deadline status, programme/cluster, fit, relevance, explanation, eligibility view, TRL view, caution, next action, and official source.
- PDF output contains project context, method, shortlist, active calls, cautions, and source URLs.

Important data limitations:

- Eligible-country metadata is missing for 94 of 100 records.
- Eligible-organisation metadata is missing for 93 of 100 records.
- TRL minimum is missing for 39 records; TRL maximum is missing for 17.
- Consortium-required metadata is present for 58 records; minimum-partner data is present for 51.

## Requirement-fit matrix

| Requirement | Evidence from client documents | Current system support | Score | Gap or risk | Recommended action |
|---|---|---|---:|---|---|
| Fast and precise EU funding identification | Strategy document asks for access that is quick, effective, and precise; concept document prioritises reduced research time. | Semantic retrieval, active-call filtering, concise shortlist, official sources, a clear progress state, and a narrow client-display correction for explicit port-side inputs are implemented. | 8.0/10 | Broad and cross-sector tails still need supervised review. | Use feedback cases to guide only narrow, tested precision changes. |
| Target themes | Strategy document names maritime, security, critical materials, and green energy; start-up/scale-up/SME financing is central. | Critical materials and battery circularity are strong. Port energy and critical-infrastructure security are useful. Hydrogen and maritime-logistics tails drift. SME/start-up support is weak. | 7.0/10 | Coverage is uneven; SME support is not currently a dependable theme. | Position the strong themes explicitly. Treat SME support and hydrogen tails as supervised-review areas. |
| Call relevance and active deadline filtering | Grant-process document treats suitable-call identification and deadlines as foundational. | Expired calls are excluded by default; 85 actionable calls remain. No expired calls appeared in the 14-case evaluation. Top-3 precision is mixed in hydrogen, maritime logistics, and SME cases. | 8.0/10 | Deadline handling is strong; relevance tails remain the main risk. | Keep the current active filter. Prefer fewer results when theme coherence weakens. |
| Eligibility and TRL usefulness | Client process requires organisation/nationality eligibility, innovation level, and official-document checks. | Eligibility and TRL are evaluated and shown cautiously. TRL coverage is moderate. Country and organisation eligibility data are absent for almost the entire dataset. | 4.0/10 | The UI can identify uncertainty, but it cannot provide a strong eligibility opinion for most calls. | Do not market this as eligibility verification. Enrich the highest-priority active calls from official documents. |
| Consortium and partner-building support | Both client documents emphasise consortium building, partner roles, and partner search. | The form captures expected partners; guidance can flag consortium requirements where metadata exists. No partner discovery, organisation suggestions, or consortium composition support exists. | 3.0/10 | Current support is a reminder, not partner-building assistance. | Keep as an honest limitation. Build partner/consortium discovery only as a later module. |
| Proposal preparation support | Client process covers proposal summaries, objectives, work plans, budgets, risks, and building blocks. | The product provides short next actions and cautions, but no proposal structure, work-package, budget, or drafting support. | 2.0/10 | The current system stops after early screening. | Position the product as call screening and first-step guidance. Treat proposal preparation as future work. |
| Strategic insights and next steps | Concept document requires alignment insights, strengths/gaps, and improvement recommendations. | Cards and PDF now provide status rationale, alignment strengths, information gaps, cautions, and a short call-specific action checklist. | 8.0/10 | Useful for triage, but not a substitute for full grant-consulting analysis. | Validate action usefulness with Gillis and keep additions evidence-based. |
| PDF/report usefulness | Concept document includes downloadable evaluation reports; process document expects shareable call analysis. | The PDF is readable, active-call-only, source-linked, cautious, and useful for sharing a shortlist. It includes project context, scores, status, eligibility/TRL caveats, next action, and caution. | 8.0/10 | Long official URLs add visual weight; content still depends on incomplete metadata. | Suitable for feedback use. Consider cleaner linked labels later, without hiding source traceability. |
| Non-technical client usability | Client needs speed and practical use, not technical configuration. | The default flow is clear: description, optional context, shortlist, strategic details, and PDF. Internal controls are hidden unless explicitly enabled, and the first semantic run shows a calm progress state. | 8.5/10 | Streamlit cold-start time remains environment-dependent. | Pre-warm the environment before a meeting and observe Gillis's first-use behavior. |
| Transparency and limitations | Official documents must remain authoritative; eligibility mistakes can cause immediate rejection. | The app shows dataset status, official sources, deadline state, score caveat, cautious labels, and missing-metadata warnings. | 9.0/10 | Transparency is one of the strongest aspects, but it must remain concise. | Preserve the current cautions and official-source requirement. |
| Readiness for supervised Gillis feedback | Project concept defines the pilot as feasibility and user-value validation. | Installation, semantic health check, tests, sample inputs, feedback questions, release checklist, client mode, guarded status wording, and call-level strategy guidance are present. | 8.5/10 | Suitable for guided feedback, not autonomous funding decisions. | Package for supervised feedback and collect structured relevance judgments. |

## Gap classification

### MUST FIX before sending to Gillis

No open release blockers remain from this audit. Client-mode gating, first-run progress feedback, and the port shore-power presentation correction have been implemented and tested.

### QUICK WIN before sending

1. Keep the feedback session focused on critical materials, battery circularity, port/harbour energy, and critical-infrastructure security. Do not lead with SME support or broad innovation ecosystem examples.
2. Use the release checklist to pre-run the environment, open the app, and verify one PDF before the meeting.
3. Record Gillis's top-result and top-three judgments so future changes remain evidence-led.

### ACCEPTABLE LIMITATION for the feedback version

- The dataset is curated and selective rather than complete coverage of all EU programmes.
- The current release focuses on Horizon Europe rather than every funding instrument mentioned in the concept document.
- Eligibility and organisation-type screening is preliminary because official metadata is sparse.
- TRL and consortium advice is useful only where explicit metadata exists.
- Hydrogen and maritime-logistics results require closer review beyond the first result.
- SME/start-up support calls are not yet reliably distinguished from sector-technology calls.
- The tool supports supervised screening, not autonomous funding decisions.

### FUTURE MODULE

- Partner and consortium matching.
- Proposal summary, work-package, milestone, risk, and budget building blocks.
- Historical funded-project and success-pattern analysis.
- Automated call alerts and scheduled dataset updates.
- Evidence-based proposal weakness detection.
- Stakeholder and policy mapping.
- Success-probability modelling, only if defensible outcome data becomes available.

## Critical product positioning

Recommended positioning:

> A client-facing decision-support system for identifying active Horizon Europe calls worth reviewing, understanding the main reason for fit, and deciding the next screening action.

Do not position the current release as:

- a complete EU funding database;
- a final eligibility checker;
- a partner-matching service;
- a proposal-writing system;
- a funding-success predictor;
- an autonomous grant consultant.

## Audit conclusion

The product fits the first, most important part of Gillis's need: faster identification and early screening of relevant active calls in selected strategic themes. It only partially fits the broader ambition to organise the full journey from funding discovery through consortium formation and proposal preparation.

That is acceptable for a supervised feedback release if the scope is stated clearly. It is not acceptable to expose internal maintenance controls or to leave a misleading strong top result in one of the primary demonstration scenarios.
