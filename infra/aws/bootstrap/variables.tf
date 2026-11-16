variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "distributed-ai"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,23}$", var.project_name))
    error_message = "Use 3 a 24 caracteres minúsculos, números e hífens."
  }
}

variable "github_repository" {
  type    = string
  default = "allansouzaallu/TCC1"
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Informe owner/repository."
  }
}

variable "github_branch" {
  type    = string
  default = "sistema-ia-distribuida"
}

variable "github_default_branch" {
  description = "Branch padrão que executa o workflow agendado de limpeza."
  type        = string
  default     = "main"
}

variable "existing_oidc_provider_arn" {
  description = "ARN do provider token.actions.githubusercontent.com já existente na conta; vazio cria um."
  type        = string
  default     = ""
}

variable "results_retention_days" {
  description = "Prazo para expirar resultados no S3; baixe os dados antes se precisar preservá-los."
  type        = number
  default     = 90
  validation {
    condition     = var.results_retention_days >= 15 && floor(var.results_retention_days) == var.results_retention_days
    error_message = "A retenção deve ser um inteiro de pelo menos 15 dias."
  }
}
