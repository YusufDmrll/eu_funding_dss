def build_call_text(call):
    # Keep the retrieval text broad and balanced so strong matches are not lost
    # when relevant terminology appears outside short title/keyword fields.
    description = str(call.get("description", "") or "").strip()
    objectives = str(call.get("objectives", "") or "").strip()

    parts = [
        call.get("call_title", ""),
        call.get("topic_title", ""),
        call.get("keywords", ""),
        description,
        objectives,
        call.get("expected_impact", ""),
        description,
        objectives,
    ]

    return " ".join(str(part).strip() for part in parts if str(part or "").strip())
