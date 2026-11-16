output "instance_id" { value = aws_instance.run.id }
output "results_uri" { value = "s3://${var.results_bucket}/runs/${var.run_id}/" }
output "expires_at" { value = var.expires_at }
output "ami_id" { value = aws_instance.run.ami }
output "gpu_count" { value = local.gpu_count }
output "model_instances" { value = var.node_count }
