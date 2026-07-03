"""Seed script: writes synthetic sales data into InfluxDB.

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

Run once, after `docker-compose up` has InfluxDB ready, to backfill history:

    python schema-sources/seed_influxdb.py

Set SEED_LOOP=1 to keep running afterwards, writing one fresh point per
series every SEED_LOOP_INTERVAL_SECONDS (default 60) so panels stay backed
by live-looking data instead of going flat past the initial backfill. This
is how docker-compose.yml's `influx-seeder` service runs it.
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

SEED_LOOP = os.environ.get("SEED_LOOP", "0") == "1"
SEED_LOOP_INTERVAL_SECONDS = int(os.environ.get("SEED_LOOP_INTERVAL_SECONDS", "60"))

REGIONS = ["us", "eu", "apac"]
ORDER_STATUSES = ["completed", "cancelled", "refunded"]
REGION_CURRENCY = {"us": "USD", "eu": "EUR", "apac": "GBP"}
PLANS = ["free", "pro", "enterprise"]
ERROR_TYPES = ["payment_declined", "timeout", "validation_error"]
ORDER_VALUE_RANGE = (15, 150)

HISTORY_HOURS = 6
STEP_MINUTES = 5


def _backfill_timestamps() -> list[float]:
    now = time.time()
    steps = int(HISTORY_HOURS * 60 / STEP_MINUTES)
    return [now - (steps - i) * STEP_MINUTES * 60 for i in range(steps + 1)]


def _wait_for_influxdb_ready(timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{INFLUXDB_URL}/health", timeout=5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(2)
    raise RuntimeError(f"InfluxDB at {INFLUXDB_URL} was not ready within {timeout_seconds}s")


class SeriesState:
    """Cumulative counters/gauge, carried forward so a continuing loop keeps
    incrementing from where the backfill left off instead of resetting to zero.
    """

    def __init__(self):
        self.sales_totals = {(status, region): 0 for status in ORDER_STATUSES for region in REGIONS}
        self.revenue_totals = {region: 0.0 for region in REGIONS}
        self.error_totals = {error_type: 0 for error_type in ERROR_TYPES}
        self.active_users = {plan: random.uniform(200, 400) for plan in PLANS}

    def step(self, ts: float) -> list[str]:
        """Advance one tick and return this tick's line-protocol points."""
        ts_ns = int(ts * 1e9)
        lines = []

        for status, region in self.sales_totals:
            weight = 0.35 if status == "completed" else 0.08
            if random.random() < weight:
                count = random.randint(1, 3)
                self.sales_totals[(status, region)] += count
                if status == "completed":
                    self.revenue_totals[region] += count * random.uniform(*ORDER_VALUE_RANGE)
            lines.append(
                f"sales,region={region},status={status} count={self.sales_totals[(status, region)]}i {ts_ns}"
            )

        for region, amount in self.revenue_totals.items():
            currency = REGION_CURRENCY[region]
            lines.append(f"revenue,region={region},currency={currency} amount={amount:.2f} {ts_ns}")

        for error_type in self.error_totals:
            if random.random() < 0.1:
                self.error_totals[error_type] += 1
            lines.append(f"errors,type={error_type} count={self.error_totals[error_type]}i {ts_ns}")

        for plan in self.active_users:
            self.active_users[plan] = min(400, max(200, self.active_users[plan] + random.uniform(-8, 8)))
            lines.append(f"users,plan={plan} active={self.active_users[plan]:.1f} {ts_ns}")

        return lines


def build_backfill() -> tuple[list[str], SeriesState]:
    """Build line-protocol points for a walk from HISTORY_HOURS ago up to now."""
    state = SeriesState()
    lines = []
    for ts in _backfill_timestamps():
        lines.extend(state.step(ts))
    return lines, state


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
    _wait_for_influxdb_ready()

    lines, state = build_backfill()
    print(f"Writing {len(lines)} points to {INFLUXDB_URL} (org={INFLUXDB_ORG}, bucket={INFLUXDB_BUCKET})...")
    write_lines(lines)
    print("Done. Measurements written: sales, revenue, users, errors")

    if SEED_LOOP:
        print(f"Looping: writing a fresh point every {SEED_LOOP_INTERVAL_SECONDS}s (Ctrl+C to stop)...")
        while True:
            time.sleep(SEED_LOOP_INTERVAL_SECONDS)
            now = time.time()
            write_lines(state.step(now))
            print(f"Wrote a fresh point at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))}")
