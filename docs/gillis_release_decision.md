# Gillis Feedback Release Decision

Decision date: 15 June 2026

## Decision

**Recommendation: ready to package for supervised Gillis feedback.**

**Overall release readiness: 9.0/10 for supervised feedback.**

The focused product-upgrade and polish sprints resolved the release blockers identified in the client-alignment audit. The application now presents a clean client flow, gives practical call-level strengths, gaps, and next steps, uses more natural client-facing wording, and handles the priority shore-power scenario more defensibly without changing the semantic model, raw similarity, Strategic Fit Score formula, call library, or deadline filtering.

## Release blockers resolved

- Internal maintenance controls and the raw dataset view are hidden in the default client experience. They remain available only when `EU_FUNDING_INTERNAL_MODE=1` is set deliberately.
- The first screening run now shows the calm progress message `Reviewing active calls...`.
- For explicitly port-side projects, a directly relevant harbour/port-infrastructure call is presented ahead of adjacent ship-side topics. Ship-side-only calls are capped and clearly described as adjacent.
- Each result now explains why its review status was assigned.
- Supporting details now separate alignment strengths, information gaps, cautions, and practical next steps.
- The PDF carries the same status rationale, clarifications, and next-step checklist.
- The Gillis retrieval audit narrative and outputs now reflect the current client-display guardrails.
- Prototype-style wording such as `pilot dataset`, `screening signals`, `priority review`, and empty `Project Title: N/A` output has been removed from the client-facing experience and PDF.
- Official EU links are shown as readable topic-page links instead of long search URLs.

## Validated release state

- 100 records in the working call library: 85 active/upcoming and 15 archived/expired.
- Expired calls remain hidden from normal screening.
- Semantic retrieval completed all 14 Gillis audit cases without fallback.
- Semantic audit: 13/14 top-1 cases passed; 35/42 top-3 results were judged relevant.
- No expired calls, weak explanations, or over-optimistic displayed statuses were found in the updated audit.
- The shore-power case received one deliberate client-display adjustment, while raw retrieval scores and ordering remain available internally and unchanged.
- Semantic health check passed with `all-MiniLM-L6-v2`.
- Full automated test suite passed.

## Limitations to state honestly

- This release screens a curated Horizon Europe dataset; it is not complete coverage of every EU funding instrument.
- Eligibility remains preliminary because country and organisation details are missing for many calls. Official documents are authoritative.
- TRL, consortium, partner, and budget details are used only where explicitly available.
- SME/start-up support and broad cross-sector inputs remain less precise than critical materials, port infrastructure, and security scenarios.
- Hydrogen and maritime-logistics result tails can include adjacent calls that need careful review.
- The product does not identify partners, build consortia, write proposals, or estimate funding success probability.

## Recommended feedback-session positioning

Present the product as:

> An early-stage EU funding screening tool that identifies active Horizon Europe calls worth reviewing, explains the main fit and caution, and guides the next screening action.

Lead with realistic multi-sentence examples in this order:

1. Critical raw materials recovery and recycling.
2. Green harbour, shore-power, or port infrastructure.
3. Critical-infrastructure security.
4. Maritime logistics as a supervised edge case.

Ask Gillis to judge whether the shortlist saves research time, whether call differences are clear, whether the cautions are useful, and whether the next steps support a real go/no-go review.

## Next phase after feedback

1. Review Gillis's recorded relevance judgments and repeated false-positive patterns.
2. Enrich official eligibility and consortium details for the calls Gillis uses most.
3. Improve SME/start-up support-call precision if Gillis confirms it as a priority.
4. Consider consultant notes and shortlist collaboration before larger modules.
5. Treat partner discovery and proposal preparation as separate future modules.
