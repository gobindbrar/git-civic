"""Stable, non-AI Meeting Brief interface for a later model integration."""


def build_meeting_brief(metadata, agenda_items):
    """Accept official metadata and agenda items; do not fabricate a summary."""
    return {
        "status": "preparing",
        "summary": None,
        "key_topics": [],
        "why_residents_may_care": None,
        "participation_information": None,
        "citations": [
            {"label": label, "url": metadata[key]}
            for key, label in (
                ("agenda_url", "Official agenda"), ("source_url", "Official meeting details")
            )
            if metadata.get(key)
        ],
    }