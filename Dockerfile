FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ARM_MCP=0 \
    ARM_RETRIEVER=tfidf

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 arm \
    && useradd --uid 10001 --gid arm --create-home arm

COPY --chown=arm:arm backend/ ./backend/
COPY --chown=arm:arm etl/ ./etl/
COPY --chown=arm:arm mcp_servers/ ./mcp_servers/
COPY --chown=arm:arm frontend/ ./frontend/
COPY --chown=arm:arm papers/ ./papers/
COPY --chown=arm:arm data/ ./data/
COPY --chown=arm:arm docker/ ./docker/

USER arm
EXPOSE 8420
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "/app/docker/healthcheck.py"]
ENTRYPOINT ["python", "/app/docker/entrypoint.py"]
CMD ["app"]
