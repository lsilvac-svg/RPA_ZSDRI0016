# Interfaz web de la plataforma de RPAs SAP.
# El worker que opera SAP GUI NO corre aquí: necesita Windows con escritorio.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 rpa \
    && mkdir -p /app/staticfiles /app/media /app/logs \
    && chown -R rpa:rpa /app
USER rpa

EXPOSE 8030

ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
