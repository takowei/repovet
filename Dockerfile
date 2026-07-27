# repovet deploy image: CLI + GitHub App webhook server + leaderboard scan
# loop, all from the same source tree. No frontend, no compiled assets --
# this is a pure-Python package (see pyproject.toml).
#
# Used by two services in docker-compose.bongo.yml, differing only in CMD:
#   - app:        python -m repovet.app_server   (webhook HTTP server)
#   - scan-cron:  scripts/scan_loop.sh            (daily leaderboard scan)

FROM python:3.11-slim AS builder

WORKDIR /build

COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.11-slim AS runtime

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

COPY --from=builder /install /usr/local

COPY src/ ./src/
COPY leaderboard/ ./leaderboard/
COPY scripts/ ./scripts/

# HOME=/data so repovet's default cache/plan-store paths (~/.cache/repovet/)
# land on the mounted volume instead of the ephemeral container filesystem.
ENV HOME=/data
RUN mkdir -p /data && chown -R appuser:appgroup /app /data
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["python", "-m", "repovet.app_server"]
