locals {
  name      = "${var.project_name}-run-${substr(var.run_id, 0, 16)}-${substr(sha256(var.run_id), 0, 6)}"
  gpu_count = { "g6e.4xlarge" = 1, "g6e.12xlarge" = 4, "g6e.48xlarge" = 8 }[var.instance_type]
}

data "aws_ssm_parameter" "dlami" {
  count = var.ami_id == "" ? 1 : 0
  name  = "/aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-22.04/latest/ami-id"
}

resource "aws_instance" "run" {
  ami                                  = var.ami_id != "" ? var.ami_id : nonsensitive(data.aws_ssm_parameter.dlami[0].value)
  instance_type                        = var.instance_type
  subnet_id                            = aws_subnet.run.id
  vpc_security_group_ids               = [aws_security_group.run.id]
  associate_public_ip_address          = true
  iam_instance_profile                 = aws_iam_instance_profile.run.name
  instance_initiated_shutdown_behavior = "terminate"
  user_data_replace_on_change          = true
  lifecycle {
    precondition {
      condition     = ceil(var.node_count / local.gpu_count) * 4 + 6 <= 44
      error_message = "Perfil insuficiente para uma LLM residente por nó: orçamento de 4 GiB por cópia mais 6 GiB de reserva em cada GPU de 44 GiB."
    }
  }
  user_data = templatefile("${path.module}/user-data.sh.tftpl", {
    aws_region     = var.aws_region
    results_bucket = var.results_bucket
    run_id         = var.run_id
    expires_at     = var.expires_at
  })
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }
  root_block_device {
    volume_size           = var.root_volume_gib
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
    tags                  = { Project = var.project_name, RunId = var.run_id, ManagedBy = "terraform" }
  }
  tags       = { Name = local.name }
  depends_on = [aws_iam_role_policy.results, aws_iam_role_policy_attachment.ssm, aws_route.internet, aws_route_table_association.run]
}

# O encerramento independe do runner GitHub, da conexão SSH e do processo Python.
resource "aws_scheduler_schedule" "deadline" {
  name                         = "${var.project_name}-${var.run_id}"
  group_name                   = "default"
  schedule_expression          = "at(${var.expires_at})"
  schedule_expression_timezone = "UTC"
  action_after_completion      = "DELETE"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = "arn:${data.aws_partition.current.partition}:scheduler:::aws-sdk:ec2:terminateInstances"
    role_arn = aws_iam_role.deadline.arn
    input    = jsonencode({ InstanceIds = [aws_instance.run.id] })
    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 3
    }
  }
  depends_on = [aws_iam_role_policy.deadline]
}
