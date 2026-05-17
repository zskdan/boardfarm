FROM python:3.12-slim

# socat for UART proxying
RUN apt-get update && apt-get install -y --no-install-recommends socat avahi-utils && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY agent/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY agent/ agent/
COPY power/ power/

EXPOSE 8766

CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8766"]
