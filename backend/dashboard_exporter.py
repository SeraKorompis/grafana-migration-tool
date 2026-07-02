from typing import Any, Optional

MIGRATED_STATUSES = {"approved", "edited"}


def build_migrated_dashboard(
    dashboard: dict[str, Any],
    decisions: dict[tuple[int, str], dict[str, Optional[str]]],
    target_language: str,
) -> dict[str, Any]:
    """Apply reviewed decisions on top of a freshly-loaded dashboard dict.

    For each query target: approved/edited decisions replace the query text with the
    reviewed version. Rejected or undecided (pending) queries keep their original,
    still-working query untouched — we deliberately do NOT inject a comment into
    `expr` itself, since these queries haven't been migrated and are still meant to
    run as-is against their original datasource; a syntax comment could break them
    depending on the query language. Instead we attach a sibling `migrationNote`
    field, which Grafana ignores on import but makes the unmigrated queries easy to
    find by search.
    """
    for panel in dashboard.get("panels", []):
        panel_id = panel.get("id")
        for target in panel.get("targets", []):
            if "expr" not in target:
                continue
            ref_id = target.get("refId")
            decision = decisions.get((panel_id, ref_id))

            if decision and decision["status"] in MIGRATED_STATUSES and decision.get("translated_query"):
                target["expr"] = decision["translated_query"]
                target.pop("migrationNote", None)
                continue

            status = decision["status"] if decision else "pending"
            reason = "rejected during review" if status == "rejected" else "not yet reviewed"
            target["migrationNote"] = (
                f"NOT MIGRATED ({reason}) — original query preserved as-is. "
                f"Needs manual migration to {target_language}."
            )

    original_uid = dashboard.get("uid")
    if original_uid:
        dashboard["uid"] = f"{original_uid}-migrated"[:40]
    original_title = dashboard.get("title", "Dashboard")
    dashboard["title"] = f"{original_title} (migrated to {target_language})"

    return dashboard
