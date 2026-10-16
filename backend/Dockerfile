FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY shelltrace ./shelltrace
COPY eval ./eval
RUN pip install .
# Cloud Run supplies PORT; the app calls its own /mcp endpoint over loopback, so ST_MCP_URL must match it.
CMD ["python", "-m", "shelltrace"]
