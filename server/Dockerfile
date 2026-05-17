FROM python:3.12-slim

WORKDIR /app
COPY server/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ server/
COPY power/ power/

ENV BOARDFARM_DB_PATH=/data/boardfarm.db
VOLUME ["/data"]
EXPOSE 8765

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8765"]
