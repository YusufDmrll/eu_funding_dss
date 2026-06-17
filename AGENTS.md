# AGENTS.md

## Project
AI-Driven EU Funding Match & Strategy System

## Product Goal
Build a highly usable, reliable, and professional client-facing decision-support application for identifying relevant Horizon Europe funding opportunities from project descriptions.

This system is intended for repeated real-world use by a company, not as a toy demo or a throwaway mockup.

## Product Standard
All changes should aim to improve:
- reliability
- usability
- clarity
- professional presentation
- robustness of outputs
- trustworthiness of screening results

The system must avoid:
- toy-like behavior
- fragile UI flows
- fake confidence
- weak matches presented as strong results
- unfinished feature integrations
- technical options exposed to end users unless truly necessary
- unnecessary complexity that reduces maintainability

## Current stack
- Python
- Streamlit
- SQLite
- CSV import

## Current core capabilities
- project-to-call matching
- lexical and semantic retrieval experimentation
- rule-based eligibility screening
- strategic fit scoring
- PDF decision-support summary
- input-quality validation
- result confidence labeling

## Non-negotiable engineering principles
- Keep the application professional and client-facing
- Prioritize reliability over flashy features
- Prefer fewer, stronger results over many weak results
- Fail safely when confidence is low
- If a feature is uncertain, surface that uncertainty clearly
- Do not make the system sound more authoritative than the data supports
- Every user-facing feature should feel intentional and production-minded
- No placeholder wording, student-project wording, or prototype-style language in the UI or PDF
- No broken integrations, missing fields, or UI crashes
- No user-facing technical jargon unless necessary

## End-user UX principle
The end user should not need to make technical choices such as retrieval-engine selection unless explicitly required for internal evaluation.
The final user flow should remain simple:
1. enter project idea
2. review best matches
3. inspect screening details
4. download a concise decision-support summary

## Constraints
- Do not replace Streamlit or SQLite
- Do not introduce vector databases, LangChain, Pinecone, FAISS, or multi-agent architectures
- Keep all changes compatible with the existing schema unless explicitly approved
- Treat eligibility metadata as preliminary where appropriate
- Prefer modular, low-risk changes
- Do not add features that expand the product into a full grant-management platform

## Development priorities
1. Improve retrieval quality
2. Improve result trustworthiness
3. Improve explainability
4. Improve client-facing usability
5. Improve PDF/report quality
6. Improve tests and regression safety
7. Improve data validation and screening robustness

## Quality bar for changes
Before implementing a change, prefer to ask:
- Does this make the system more reliable?
- Does this make the user output more defensible?
- Does this reduce the chance of misleading results?
- Does this improve real repeated use by a company?
- Does this preserve a clean and maintainable codebase?

If not, do not implement it.

## Communication style
When describing the system, avoid minimizing language such as:
- just a prototype
- toy
- demo-only
- simple student project

Prefer wording such as:
- professional pilot application
- current production-minded version
- client-facing decision-support system
- robust working version

## Useful commands
- streamlit run app/streamlit_app.py
- python scripts/import_calls.py
- python scripts/init_db.py
- python -m unittest discover -s tests