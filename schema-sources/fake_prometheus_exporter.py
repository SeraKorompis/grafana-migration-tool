"""Fake e-commerce Prometheus exporter.

Serves synthetic metrics for a small online store so Prometheus has
something realistic to scrape for the schema-introspection demo:

  orders_total{status, region}          counter
  revenue_dollars_total{currency, region} counter
  active_users_gauge{plan}              gauge
  checkout_errors_total{error_type}     counter

Values drift a little on every scrape rather than sitting static, so a
schema/values query against Prometheus returns numbers that actually move.
"""
import random
import threading
import time

from prometheus_client import start_http_server
from prometheus_client.core import CollectorRegistry, CounterMetricFamily, GaugeMetricFamily
from prometheus_client.registry import Collector

PORT = 9105

REGIONS = ["us", "eu", "apac"]
ORDER_STATUSES = ["completed", "cancelled", "refunded"]
REGION_CURRENCY = {"us": "USD", "eu": "EUR", "apac": "GBP"}
PLANS = ["free", "pro", "enterprise"]
ERROR_TYPES = ["payment_declined", "timeout", "validation_error"]

# order value range in dollars, used to derive revenue from completed orders
ORDER_VALUE_RANGE = (15, 150)

_lock = threading.Lock()
_orders_total = {(status, region): 0.0 for status in ORDER_STATUSES for region in REGIONS}
_revenue_total = {region: 0.0 for region in REGIONS}
_checkout_errors_total = {error_type: 0.0 for error_type in ERROR_TYPES}
_active_users = {plan: random.uniform(200, 400) for plan in PLANS}


def _drift():
    """Advance counters and jitter the gauge by a small realistic amount.

    Tuned so totals land in the tens-of-orders-per-hour range for a small
    shop, not the millions a real e-commerce firehose would produce.
    """
    with _lock:
        for status, region in _orders_total:
            weight = 0.06 if status == "completed" else 0.015
            if random.random() < weight:
                count = random.randint(1, 2)
                _orders_total[(status, region)] += count
                if status == "completed":
                    order_value = random.uniform(*ORDER_VALUE_RANGE)
                    _revenue_total[region] += count * order_value

        for error_type in _checkout_errors_total:
            if random.random() < 0.02:
                _checkout_errors_total[error_type] += 1

        for plan in _active_users:
            jitter = random.uniform(-8, 8)
            _active_users[plan] = min(400, max(200, _active_users[plan] + jitter))


class EcommerceCollector(Collector):
    def collect(self):
        _drift()

        with _lock:
            orders = CounterMetricFamily(
                "orders_total", "Total number of orders placed", labels=["status", "region"]
            )
            for (status, region), value in _orders_total.items():
                orders.add_metric([status, region], value)
            yield orders

            revenue = CounterMetricFamily(
                "revenue_dollars_total", "Total revenue collected, in dollars", labels=["currency", "region"]
            )
            for region, value in _revenue_total.items():
                revenue.add_metric([REGION_CURRENCY[region], region], value)
            yield revenue

            errors = CounterMetricFamily(
                "checkout_errors_total", "Total checkout errors encountered", labels=["error_type"]
            )
            for error_type, value in _checkout_errors_total.items():
                errors.add_metric([error_type], value)
            yield errors

            active_users = GaugeMetricFamily(
                "active_users_gauge", "Current active users by subscription plan", labels=["plan"]
            )
            for plan, value in _active_users.items():
                active_users.add_metric([plan], value)
            yield active_users


if __name__ == "__main__":
    registry = CollectorRegistry()
    registry.register(EcommerceCollector())
    start_http_server(PORT, addr="0.0.0.0", registry=registry)
    print(f"Fake e-commerce exporter serving on :{PORT}/metrics")
    while True:
        time.sleep(1)
