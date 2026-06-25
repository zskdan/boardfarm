FROM python:3.12-slim

WORKDIR /app
COPY server/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ server/
COPY power/ power/

# Compute version from git at build time; falls back to ARG override or "unknown"
ARG BOARDFARM_VERSION=
COPY .git/ .git/
RUN git rev-parse --short=8 HEAD > /tmp/git_sha 2>/dev/null || true
RUN sha=$(cat /tmp/git_sha 2>/dev/null); \
    tag=$(git describe --tags --abbrev=0 2>/dev/null || true); \
    dirty=$(git status --porcelain 2>/dev/null | grep -q . && echo -dirty || true); \
    ver=${BOARDFARM_VERSION:-${tag:+$tag-}${sha}${dirty}}; \
    echo "${ver:-unknown}" > /tmp/version
RUN rm -rf .git

ENV BOARDFARM_DB_PATH=/data/boardfarm.db
ENV BOARDFARM_VERSION_FILE=/tmp/version
VOLUME ["/data"]
EXPOSE 8765

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8765"]
