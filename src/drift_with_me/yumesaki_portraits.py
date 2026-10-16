"""Approved counter busts; expression is derived, never persisted or used on the map."""

YUMESAKI_PORTRAITS = {
    mood: "yumesaki_bust_" + mood
    for mood in ("normal", "smile", "worried", "surprised", "thinking")
}
# Existing counter dialogue only. Other approved expressions remain registered for later lines.
YUMESAKI_EXPRESSIONS = {
    "げ、原因も、今は特定できていなくて……": "worried",
}


def yumesaki_office_portrait(text: str) -> str:
    return YUMESAKI_PORTRAITS[YUMESAKI_EXPRESSIONS.get(text, "normal")]
