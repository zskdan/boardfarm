FROM python:3.12-slim

# socat for UART proxying
RUN apt-get update && apt-get install -y --no-install-recommends socat avahi-utils && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY boardfarm_agent/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY boardfarm_agent/ boardfarm_agent/
COPY power/ power/

COPY .git/ .git/
RUN git rev-parse --short HEAD > boardfarm_agent/VERSION 2>/dev/null || true
RUN rm -rf .git

EXPOSE 8766

CMD ["uvicorn", "boardfarm_agent.main:app", "--host", "0.0.0.0", "--port", "8766"]
