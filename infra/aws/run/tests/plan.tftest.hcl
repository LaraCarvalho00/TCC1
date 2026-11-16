mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_availability_zones" {
    defaults = { names = ["us-east-1a"] }
  }
  mock_data "aws_ec2_instance_type_offerings" {
    defaults = { locations = ["us-east-1a"] }
  }
}

run "ephemeral_gpu_host" {
  command = plan
  variables {
    run_id                           = "gh-1234567890123-1"
    results_bucket                   = "distributed-ai-test-results"
    runtime_permissions_boundary_arn = "arn:aws:iam::123456789012:policy/distributed-ai-runtime-boundary"
    expires_at                       = "2030-01-01T12:00:00"
    ami_id                           = "ami-0123456789abcdef0"
  }
  assert {
    condition     = aws_instance.run.instance_type == "g6e.48xlarge" && aws_instance.run.instance_initiated_shutdown_behavior == "terminate"
    error_message = "A máquina GPU deve ser descartada quando o sistema operacional desligar."
  }
  assert {
    condition     = aws_instance.run.root_block_device[0].encrypted && aws_instance.run.root_block_device[0].delete_on_termination
    error_message = "O volume deve ser criptografado e removido na terminação."
  }
  assert {
    condition     = aws_instance.run.metadata_options[0].http_tokens == "required" && aws_instance.run.metadata_options[0].http_put_response_hop_limit == 1
    error_message = "Exija IMDSv2 e impeça que os containers obtenham credenciais da máquina."
  }
  assert {
    condition     = length(aws_security_group.run.ingress) == 0
    error_message = "O experimento não deve abrir portas públicas."
  }
  assert {
    condition     = aws_scheduler_schedule.deadline.schedule_expression == "at(2030-01-01T12:00:00)" && aws_scheduler_schedule.deadline.action_after_completion == "DELETE"
    error_message = "O prazo externo deve ser absoluto e a agenda deve se remover após a execução."
  }
  assert {
    condition     = aws_iam_role.instance.permissions_boundary == var.runtime_permissions_boundary_arn && aws_iam_role.deadline.permissions_boundary == var.runtime_permissions_boundary_arn
    error_message = "Todos os papéis runtime devem respeitar a fronteira criada no bootstrap."
  }
  assert {
    condition     = !contains(jsondecode(aws_iam_role_policy.results.policy).Statement[1].Resource, "arn:aws:s3:::${var.results_bucket}/runs/${var.run_id}/*") && length(jsondecode(aws_iam_role_policy.results.policy).Statement[1].Resource) == 6
    error_message = "A instância só pode publicar resultados e status; não pode sobrescrever input ou control executados pelo workflow."
  }
}

run "reject_undersized_host_before_creation" {
  command = plan
  variables {
    run_id                           = "gh-1234567890123-1"
    results_bucket                   = "distributed-ai-test-results"
    runtime_permissions_boundary_arn = "arn:aws:iam::123456789012:policy/distributed-ai-runtime-boundary"
    expires_at                       = "2030-01-01T12:00:00"
    ami_id                           = "ami-0123456789abcdef0"
    instance_type                    = "g6e.12xlarge"
    node_count                       = 50
  }
  expect_failures = [aws_instance.run]
}
