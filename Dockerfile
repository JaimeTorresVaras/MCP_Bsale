FROM python:3.11-slim

WORKDIR /app

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY server.py .

# Puerto que expone el servidor SSE
EXPOSE 8000

# Variables de entorno requeridas (se inyectan en el panel de la plataforma)
# BSALE_API_TOKEN=tu_token_aqui
# MCP_TRANSPORT=sse
# PORT=8000 (ya es el default)

CMD ["python", "server.py"]
