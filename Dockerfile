FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todos los módulos del servidor
COPY server.py config.py http_client.py cache.py transforms.py monitor.py domain.py ./
COPY tools/ ./tools/

EXPOSE 8000

# Variables de entorno requeridas (se inyectan en el panel de la plataforma)
# BSALE_API_TOKEN=tu_token_aqui
# MCP_TRANSPORT=sse
# PORT=8000 (ya es el default)

CMD ["python", "server.py"]
