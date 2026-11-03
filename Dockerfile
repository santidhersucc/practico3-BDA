# Imagen de la API de Sentinel (y de los scripts de carga y los tests).
# Se construye desde la RAÍZ del repo (build: . en docker-compose.yml) para poder copiar api/, scripts/ y data/.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Primero solo los requirements: mientras no cambien, Docker reutiliza esta capa y no reinstala todo.
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

# Misma estructura de carpetas que el repo: los scripts y los tests buscan data/ relativa a su ubicación.
COPY api ./api
COPY scripts ./scripts
COPY data ./data

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "api", "--host", "0.0.0.0", "--port", "8000"]
