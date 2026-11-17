terraform {
  required_version = ">= 1.11.4"

  required_providers {
    runpod = {
      source  = "runpod/runpod"
      version = "2.0.0"
    }
  }
}

provider "runpod" {}

locals {
  scientific = jsondecode(file("${path.module}/../cenarios-completos.json")).configuration
  gpu_distribution = [
    for gpu in range(local.scientific.gpu_count) :
    floor(local.scientific.nodes / local.scientific.gpu_count) + (gpu < local.scientific.nodes % local.scientific.gpu_count ? 1 : 0)
  ]
  runtime = {
    TCC_RUN_ID             = var.run_id
    TCC_RUN_PROFILE        = "campaign"
    TCC_NODE_COUNT         = tostring(local.scientific.nodes)
    TCC_GPU_COUNT          = tostring(local.scientific.gpu_count)
    TCC_MODELS_PER_GPU     = tostring(max(local.gpu_distribution...))
    TCC_INFERENCE_LAYOUT   = local.scientific.inference_layout
    MODEL_NAME             = local.scientific.model
    MODEL_REVISION         = local.scientific.model_revision
    MODEL_QUANTIZATION     = local.scientific.quantization
    MODEL_DEVICE           = "cuda"
    MODEL_MAX_NEW_TOKENS   = tostring(local.scientific.max_new_tokens)
    MODEL_TEMPERATURE      = tostring(local.scientific.temperature)
    MODEL_TOP_P            = tostring(local.scientific.top_p)
    HF_HOME                = "/workspace/huggingface"
    OMP_NUM_THREADS        = "1"
    MKL_NUM_THREADS        = "1"
    TOKENIZERS_PARALLELISM = "false"
  }
  campaign = var.campaign == null ? {} : {
    TCC_DEADLINE      = tostring(var.campaign.deadline)
    TCC_S3_BUCKET     = var.campaign.bucket
    TCC_S3_ENDPOINT   = var.campaign.endpoint
    TCC_S3_ACCESS_KEY = "{{ RUNPOD_SECRET_tcc_results_access_key }}"
    TCC_S3_SECRET_KEY = "{{ RUNPOD_SECRET_tcc_results_secret_key }}"
  }
}

resource "runpod_pod" "experiment" {
  name                   = "tcc-qwen-${var.run_id}"
  cloud                  = "SECURE"
  gpu_type_id            = "NVIDIA RTX A6000"
  gpu_count              = local.scientific.gpu_count
  allowed_cuda_versions  = ["13.2"]
  min_ram_per_gpu        = 50
  min_vcpu_count_per_gpu = 9
  disk                   = 180
  image                  = var.image
  registry               = var.registry_id
  start_ssh              = var.enable_ssh
  start_jupyter          = false
  ports                  = var.enable_ssh ? ["22/tcp"] : []
  env                    = merge(local.runtime, local.campaign)

  persistent_volume = {
    size = 30
    path = "/workspace"
  }
}

output "pod_id" {
  value = runpod_pod.experiment.id
}

output "configuration" {
  value = {
    gpu_count      = local.scientific.gpu_count
    nodes          = local.scientific.nodes
    gpu_load       = local.gpu_distribution
    models_per_gpu = max(local.gpu_distribution...)
    model          = local.scientific.model
    model_revision = local.scientific.model_revision
    quantization   = local.scientific.quantization
    layout         = local.scientific.inference_layout
  }
}
