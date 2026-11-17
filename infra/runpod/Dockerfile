FROM runpod/pytorch:2.1.0-cu1320-torch280-ubuntu2404@sha256:0e4233027c75e504110202dfd5c5ccc0b315826d9c5cb808738982dffcfda2ec

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false

COPY sistema/requirements-node.txt sistema/requirements-orchestrator.txt sistema/node/requirements-dedicated.txt ./
RUN python -m pip install --no-cache-dir -r requirements-node.txt -r requirements-orchestrator.txt -r requirements-dedicated.txt boto3==1.40.72 \
    && python -c 'import torch; assert torch.__version__.split("+")[0] == "2.8.0"'

COPY sistema/ sistema/
COPY infra/runpod/cenarios-completos.json infra/runpod/cenarios-completos.json
ARG CODE_REVISION
ENV TCC_CODE_REVISION=${CODE_REVISION}
RUN python -m sistema.scripts.runpod_worker --check-config

ENTRYPOINT ["python", "-m", "sistema.scripts.runpod_worker"]
CMD []
