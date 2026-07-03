"""One-time seed script: writes synthetic sales data into InfluxDB.

Populates InfluxDB with data that represents the same underlying business
concepts as the Prometheus fake-exporter metrics, but under deliberately
different measurement/tag/field names -- the kind of naming drift a real
migration runs into, so query translation has an actual target schema to
ground against instead of assuming names carry over 1:1:

  Prometheus                              InfluxDB
  orders_total{status,region}          -> sales{region,status}   field: count
  revenue_dollars_total{currency,region} -> revenue{region,currency} field: amount
  active_users_gauge{plan}             -> users{plan}            field: active
  checkout_errors_total{error_type}    -> errors{type}           field: count

Run once, after `docker-compose up` has InfluxDB ready:

    python schema-sources/seed_influxdb.py
"""
import os
import random
import time
import urllib.error
import urllib.request

INFLUXDB_URL = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_ORG = os.environ.get("INFLUXDB_ORG", "hackathon")
INFLUXDB_BUCKET = os.environ.get("INFLUXDB_BUCKET", "ecommerce")
INFLUXDB_TOKEN = os.environ.get("INFLUXDB_TOKEN", "dev-token-please-change")

REGIONS = ["us", "eu", "apac"]
ORDER_STATUSES = ["completed", "cancelled", "refunded"]
REGION_CURRENCY = {"us": "USD", "eu": "EUR", "apac": "GBP"}
PLANS = ["free", "pro", "enterprise"]
ERROR_TYPES = ["payment_declined", "timeout", "validation_error"]
ORDER_VALUE_RANGE = (15, 150)

HISTORY_HOURS = 6
STEP_MINUTES = 5


def _timestamps() -> list[float]:
    now = time.time()
    steps = int(HISTORY_HOURS * 60 / STEP_MINUTES)
    return [now - (steps - i) * STEP_MINUTES * 60 for i in range(steps + 1)]


def build_lines() -> list[str]:
    """Build line-protocol points for a walk from 6 hours ago up to now."""
    lines = []

    sales_totals = {(status, region): 0 for status in ORDER_STATUSES for region in REGIONS}
    revenue_totals = {region: 0.0 for region in REGIONS}
    error_totals = {error_type: 0 for error_type in ERROR_TYPES}
    active_users = {plan: random.uniform(200, 400) for plan in PLANS}

    for ts in _timestamps():
        ts_ns = int(ts * 1e9)

        for status, region in sales_totals:
            weight = 0.35 if status == "completed" else 0.08
            if random.random() < weight:
                count = random.randint(1, 3)
                sales_totals[(status, region)] += count
                if status == "completed":
                    revenue_totals[region] += count * random.uniform(*ORDER_VALUE_RANGE)
            lines.append(
                f"sales,region={region},status={status} count={sales_totals[(status, region)]}i {ts_ns}"
            )

        for region, amount in revenue_totals.items():
            currency = REGION_CURRENCY[region]
            lines.append(f"revenue,region={region},currency={currency} amount={amount:.2f} {ts_ns}")

        for error_type in error_totals:
            if random.random() < 0.1:
                error_totals[error_type] += 1
            lines.append(f"errors,type={error_type} count={error_totals[error_type]}i {ts_ns}")

        for plan in active_users:
            active_users[plan] = min(400, max(200, active_users[plan] + random.uniform(-8, 8)))
            lines.append(f"users,plan={plan} active={active_users[plan]:.1f} {ts_ns}")

    return lines


def write_lines(lines: list[str]) -> None:
    url = f"{INFLUXDB_URL}/api/v2/write?org={INFLUXDB_ORG}&bucket={INFLUXDB_BUCKET}&precision=ns"
    request = urllib.request.Request(
        url,
        data="\n".join(lines).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Token {INFLUXDB_TOKEN}",
            "Content-Type": "text/plain; charset=utf-8",
        },
    )
    try:
        urllib.request.urlopen(request)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"InfluxDB write failed: HTTP {exc.code} - {exc.read().decode('utf-8')}") from exc


if __name__ == "__main__":
    points = build_lines()
    print(f"Writing {len(points)} points to {INFLUXDB_URL} (org={INFLUXDB_ORG}, bucket={INFLUXDB_BUCKET})...")
    write_lines(points)
    print("Done. Measurements written: sales, revenue, users, errors")
