mock_provider "runpod" {}

variables {
  run_id = "2xa6000-01"
}

run "campaign_uses_dedicated_qwen" {
  command = plan

  assert {
    condition     = runpod_pod.experiment.gpu_count == 2 && output.configuration.gpu_load == [25, 25]
    error_message = "A campanha deve distribuir os 50 nós em 25/25 nas duas GPUs."
  }

  assert {
    condition = (
      runpod_pod.experiment.env["MODEL_NAME"] == "Qwen/Qwen3-0.6B" &&
      runpod_pod.experiment.env["MODEL_QUANTIZATION"] == "nf4" &&
      runpod_pod.experiment.env["TCC_INFERENCE_LAYOUT"] == "per_node"
    )
    error_message = "A campanha deve usar uma instância Qwen NF4 por nó."
  }
  assert {
    condition = (
      runpod_pod.experiment.gpu_type_id == "NVIDIA RTX A6000" &&
      contains(runpod_pod.experiment.allowed_cuda_versions, "13.2") &&
      startswith(runpod_pod.experiment.image, "runpod/pytorch:2.1.0-cu1320-torch280-ubuntu2404@sha256:")
    )
    error_message = "A GPU e a imagem devem corresponder à oferta com PyTorch 2.8.0, CUDA 13.2 e Ubuntu 24.04."
  }

  assert {
    condition = (
      runpod_pod.experiment.disk == 180 &&
      runpod_pod.experiment.persistent_volume.size == 30 &&
      runpod_pod.experiment.persistent_volume.path == "/workspace"
    )
    error_message = "O Pod deve ter 180 GB temporários e 30 GB persistentes em /workspace."
  }
}
