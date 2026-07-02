import json
from pathlib import Path
from typing import Any


def load_dashboard(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_dashboard(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a Grafana dashboard JSON into one entry per panel.

    Each entry has: id, title, datasource, and queries (one per target that
    has an "expr", since some panels — e.g. text/row panels — have none, and
    others have several targets sharing one query language).
    """
    parsed_panels = []
    for panel in dashboard.get("panels", []):
        queries = [
            {"ref_id": target.get("refId"), "expr": target["expr"]}
            for target in panel.get("targets", [])
            if "expr" in target
        ]
        parsed_panels.append(
            {
                "id": panel.get("id"),
                "title": panel.get("title"),
                "datasource": panel.get("datasource"),
                "queries": queries,
            }
        )
    return parsed_panels
