#!/usr/bin/env bash
set -Eeuo pipefail

CONFIG="${1:-/opt/distributed-ai/run.json}"
PROJECT=/opt/distributed-ai/project
VENV=/opt/distributed-ai/venv
export HF_HOME=/opt/distributed-ai/huggingface
export HF_HUB_DISABLE_TELEMETRY=1
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=2
export TOKENIZERS_PARALLELISM=false
mkdir -p /opt/distributed-ai/runtime
exec > >(tee -a /var/log/distributed-ai-bootstrap.log) 2>&1
cd "$PROJECT"

# Falhas de instalação também preservam o log e encerram a EC2. O watchdog
# externo da AWS protege inclusive falhas anteriores a este script.
failed_setup() {
  exit_code=$?
  trap - EXIT
  if [ "$exit_code" -ne 0 ]; then
    python3 -m sistema.scripts.cloud_run --config "$CONFIG" \
      --bootstrap-error "Bootstrap terminou com código $exit_code" || true
  fi
  shutdown -h now || true
}
trap failed_setup EXIT

export DEBIAN_FRONTEND=noninteractive
# A DLAMI fornece o driver NVIDIA; venv e Compose variam entre versões da AMI.
timeout 600 apt-get update -o Acquire::Retries=3
timeout 900 apt-get install -y -o DPkg::Lock::Timeout=120 python3-venv ca-certificates curl
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  if ! grep -Rqs 'download.docker.com/linux/ubuntu' /etc/apt/sources.list.d /etc/apt/sources.list; then
  install -m 0755 -d /etc/apt/keyrings
  timeout 120 curl -fsSL --retry 3 https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # Pacotes do repositório oficial Docker, sem executar script remoto.
  . /etc/os-release
  cat > /etc/apt/sources.list.d/distributed-ai-docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  fi
  timeout 600 apt-get update -o Acquire::Retries=3
  if command -v dockerd >/dev/null; then
    timeout 900 apt-get install -y -o DPkg::Lock::Timeout=120 docker-buildx-plugin docker-compose-plugin
  else
    timeout 900 apt-get install -y -o DPkg::Lock::Timeout=120 docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi
fi
timeout 120 systemctl enable --now docker
if ! command -v nvidia-ctk >/dev/null; then
  echo 'A DLAMI precisa incluir NVIDIA Container Toolkit (nvidia-ctk).' >&2
  exit 1
fi
timeout 60 nvidia-ctk runtime configure --runtime=docker
timeout 120 systemctl restart docker
nvidia-smi
timeout 60 docker info >/dev/null
timeout 60 docker compose version
timeout 120 python3 -m venv "$VENV"
export PATH="$VENV/bin:$PATH"
timeout 600 python -m pip install --upgrade pip
timeout 1800 python -m pip install 'torch==2.7.1' --index-url https://download.pytorch.org/whl/cu126
timeout 1800 python -m pip install -r infra/aws/worker/requirements.txt
python -c 'import torch; assert torch.cuda.is_available(), "CUDA indisponível"; print(torch.cuda.get_device_name(0))'
python -m pip freeze > /opt/distributed-ai/runtime/requirements-resolved.txt
nvidia-smi -q > /opt/distributed-ai/runtime/gpu.txt
timeout 1800 python - "$CONFIG" <<'PY'
import json
import sys
from pathlib import Path
import subprocess
from huggingface_hub import HfApi, snapshot_download
from sistema.scripts.cloud_run import validate
from sistema.aplicacao.capacidade_nuvem import validate_devices
config = validate(json.loads(Path(sys.argv[1]).read_text()))
gpu_rows = subprocess.run(["nvidia-smi", "--query-gpu=uuid,memory.total,memory.free", "--format=csv,noheader,nounits"],
                          check=True, capture_output=True, text=True).stdout.splitlines()
devices = []
for row in gpu_rows:
    uuid, total, free = [part.strip() for part in row.split(",")]
    devices.append({"uuid": uuid, "total_mib": int(total), "free_mib": int(free)})
measurement = validate_devices(config, devices)
Path("/opt/distributed-ai/runtime/capacity.json").write_text(json.dumps(measurement, indent=2))
revision = HfApi().model_info(config["model"]).sha
# local_dir produz arquivos completos: montar apenas um snapshot do cache HF
# deixaria seus symlinks para ../../blobs quebrados dentro dos contêineres.
path = snapshot_download(config["model"], revision=revision, local_dir="/opt/distributed-ai/model")
config.update(model_snapshot=str(Path(path).resolve()), model_revision=revision)
Path(sys.argv[1]).write_text(json.dumps(config, indent=2))
Path("/opt/distributed-ai/runtime/model-snapshot.json").write_text(json.dumps({"model": config["model"], "revision": revision, "path": path}, indent=2))
PY
timeout 2400 docker build -t tcc-node-model:latest -f sistema/node/Dockerfile.model .
timeout 1800 docker build -t tcc-orch:latest -f sistema/orchestrator/Dockerfile .
timeout 180 docker run --rm --gpus all tcc-node-model:latest python -c 'import torch; assert torch.cuda.is_available(); print(torch.cuda.device_count())'

# O worker fica responsável pela publicação e desligamento a partir daqui.
trap - EXIT
exec python -m sistema.scripts.cloud_run --config "$CONFIG"
