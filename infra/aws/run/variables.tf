variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "distributed-ai"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,23}$", var.project_name))
    error_message = "Use um nome de 3 a 24 caracteres minúsculos, números e hífens."
  }
}

variable "run_id" {
  description = "Identificador único de até 32 caracteres; determina o prefixo S3 e os nomes dos recursos."
  type        = string
  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9-]{0,31}$", var.run_id))
    error_message = "run_id aceita de 1 a 32 caracteres alfanuméricos/hífens."
  }
}

variable "results_bucket" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.results_bucket))
    error_message = "Informe o nome do bucket S3, sem s3://."
  }
}

variable "runtime_permissions_boundary_arn" {
  type        = string
  description = "Output do bootstrap; obrigatório nos papéis runtime criados pelo GitHub."
}

variable "expires_at" {
  type        = string
  description = "Limite UTC absoluto, sem sufixo de timezone: YYYY-MM-DDTHH:mm:ss."
  validation {
    condition     = can(timeadd("${var.expires_at}Z", "0s")) && can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$", var.expires_at))
    error_message = "Use um timestamp UTC como 2026-11-20T12:00:00."
  }
}

variable "instance_type" {
  type    = string
  default = "g6e.48xlarge"
  validation {
    condition     = contains(["g6e.4xlarge", "g6e.12xlarge", "g6e.48xlarge"], var.instance_type)
    error_message = "Use g6e.4xlarge, g6e.12xlarge ou g6e.48xlarge para modelos dedicados."
  }
}

variable "node_count" {
  type    = number
  default = 50
  validation {
    condition     = var.node_count >= 6 && var.node_count <= 100 && floor(var.node_count) == var.node_count
    error_message = "Use de 6 a 100 nós inteiros, sujeitos ao orçamento de VRAM do perfil."
  }
}

variable "ami_id" {
  type        = string
  default     = ""
  description = "Override opcional de DLAMI Ubuntu x86_64 com driver NVIDIA; vazio consulta o SSM oficial."
  validation {
    condition     = var.ami_id == "" || can(regex("^ami-[a-f0-9]{8,17}$", var.ami_id))
    error_message = "Informe uma AMI válida ou deixe vazio."
  }
}

variable "root_volume_gib" {
  type    = number
  default = 150
  validation {
    condition     = var.root_volume_gib >= 100 && var.root_volume_gib <= 500 && floor(var.root_volume_gib) == var.root_volume_gib
    error_message = "Use um volume inteiro de 100 a 500 GiB."
  }
}
