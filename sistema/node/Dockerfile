FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Instala apenas as dependências do nó (modo mock, sem modelo).
COPY sistema/requirements-node.txt ./requirements-node.txt
RUN pip install --no-cache-dir -r requirements-node.txt

COPY sistema/ ./sistema/

EXPOSE 8000
CMD ["uvicorn", "sistema.node.app:app", "--host", "0.0.0.0", "--port", "8000"]
