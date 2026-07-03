from typing import Any, Optional

MIGRATED_STATUSES = {"approved", "edited"}

# Reverse of main.py's DATASOURCE_TYPE_TO_QUERY_LANGUAGE - keep in sync if either changes.
# "SQL" is ambiguous between mysql/postgres source-side; postgres is just a reasonable default
# for the migrated target since we have no way to know which the user actually runs.
TARGET_LANGUAGE_TO_DATASOURCE_TYPE = {
    "InfluxDB Flux": "influxdb",
    "LogQL": "loki",
    "SQL": "postgres",
}

# Grafana's target/query-target model stores the query text under a different key per
# datasource plugin - Prometheus/Loki use "expr", InfluxDB's Flux mode uses "query", and
# Postgres/MySQL's SQL editor uses "rawSql". Writing translated text into the wrong field
# leaves the query box empty in Grafana even though the JSON "looks" correct.
TARGET_LANGUAGE_TO_QUERY_FIELD = {
    "InfluxDB Flux": "query",
    "LogQL": "expr",
    "SQL": "rawSql",
}


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

    A panel's top-level "datasource" is only swapped to the target type once every one
    of its targets is migrated - if even one target is still pending/rejected, that
    target needs the *original* datasource to keep working, so the panel-level field
    (shared by all targets) must stay put rather than breaking the unmigrated ones.
    """
    target_datasource_type = TARGET_LANGUAGE_TO_DATASOURCE_TYPE.get(target_language)
    target_query_field = TARGET_LANGUAGE_TO_QUERY_FIELD.get(target_language, "expr")

    for panel in dashboard.get("panels", []):
        panel_id = panel.get("id")
        expr_targets = [target for target in panel.get("targets", []) if "expr" in target]
        if not expr_targets:
            continue

        panel_fully_migrated = True
        for target in expr_targets:
            ref_id = target.get("refId")
            decision = decisions.get((panel_id, ref_id))

            if decision and decision["status"] in MIGRATED_STATUSES and decision.get("translated_query"):
                if target_query_field != "expr":
                    target.pop("expr", None)
                target[target_query_field] = decision["translated_query"]
                target.pop("migrationNote", None)
                continue

            panel_fully_migrated = False
            status = decision["status"] if decision else "pending"
            reason = "rejected during review" if status == "rejected" else "not yet reviewed"
            target["migrationNote"] = (
                f"NOT MIGRATED ({reason}) — original query preserved as-is. "
                f"Needs manual migration to {target_language}."
            )

        if panel_fully_migrated and target_datasource_type:
            panel["datasource"] = {"type": target_datasource_type, "uid": f"${{ds_{target_datasource_type}}}"}

    original_uid = dashboard.get("uid")
    if original_uid:
        dashboard["uid"] = f"{original_uid}-migrated"[:40]
    original_title = dashboard.get("title", "Dashboard")
    dashboard["title"] = f"{original_title} (migrated to {target_language})"

    return dashboard
