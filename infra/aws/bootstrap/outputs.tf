output "state_bucket" { value = aws_s3_bucket.state.id }
output "results_bucket" { value = aws_s3_bucket.results.id }
output "github_role_arn" { value = aws_iam_role.github.arn }
output "runtime_permissions_boundary_arn" { value = aws_iam_policy.runtime_boundary.arn }
output "aws_region" { value = var.aws_region }
output "project_name" { value = var.project_name }
