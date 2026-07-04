FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fake_prometheus_exporter.py seed_influxdb.py .

EXPOSE 9105

CMD ["python", "fake_prometheus_exporter.py"]
