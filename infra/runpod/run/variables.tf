variable "run_id" {
  description = "Identificador único da execução, usado no nome do Pod."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,47}$", var.run_id))
    error_message = "Use até 48 letras minúsculas, números ou hífens, começando por letra ou número."
  }
}

variable "image" {
  description = "Imagem Linux amd64 fixada por digest. Padrão: Runpod PyTorch 2.8.0, CUDA 13.2 e Ubuntu 24.04."
  type        = string
  default     = "runpod/pytorch:2.1.0-cu1320-torch280-ubuntu2404@sha256:0e4233027c75e504110202dfd5c5ccc0b315826d9c5cb808738982dffcfda2ec"

  validation {
    condition     = can(regex("^[^ \\t\\n]+@sha256:[0-9a-f]{64}$", var.image))
    error_message = "Informe a imagem no formato repositorio@sha256:<digest>."
  }
}

variable "registry_id" {
  description = "ID da credencial do registry já cadastrada no RunPod. Use null para imagem pública."
  type        = string
  default     = null
}

variable "campaign" {
  description = "Configuração de execução assíncrona e bucket privado de resultados. As chaves vêm dos Secrets do Runpod."
  type = object({
    bucket   = string
    endpoint = string
    deadline = number
  })
  default = null
}

variable "enable_ssh" {
  description = "Habilita inspeção manual com a chave SSH já cadastrada no RunPod."
  type        = bool
  default     = false
}
