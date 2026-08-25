FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY sistema/requirements-orchestrator.txt ./requirements-orchestrator.txt
RUN pip install --no-cache-dir -r requirements-orchestrator.txt

COPY sistema/ ./sistema/

CMD ["python", "-m", "sistema.orchestrator.run", "--config", "sistema/config/experiment.yaml"]
