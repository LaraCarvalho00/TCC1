data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}

resource "aws_iam_role" "instance" {
  name                 = "${local.name}-ec2"
  permissions_boundary = var.runtime_permissions_boundary_arn
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "results" {
  name = "run-artifacts"
  role = aws_iam_role.instance.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = "s3:GetObject", Resource = "arn:${data.aws_partition.current.partition}:s3:::${var.results_bucket}/runs/${var.run_id}/*" },
      { Effect = "Allow", Action = ["s3:PutObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"], Resource = [for key in ["results/*", "runtime/*", "checkpoints/*", "logs/*", "status.json", "results.tar.gz"] : "arn:${data.aws_partition.current.partition}:s3:::${var.results_bucket}/runs/${var.run_id}/${key}"] },
      { Effect = "Allow", Action = "s3:ListBucket", Resource = "arn:${data.aws_partition.current.partition}:s3:::${var.results_bucket}", Condition = { StringLike = { "s3:prefix" = ["runs/${var.run_id}", "runs/${var.run_id}/*"] } } },
      { Effect = "Allow", Action = "s3:GetBucketLocation", Resource = "arn:${data.aws_partition.current.partition}:s3:::${var.results_bucket}" }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "run" {
  name = "${local.name}-ec2"
  role = aws_iam_role.instance.name
}

resource "aws_iam_role" "deadline" {
  name                 = "${local.name}-deadline"
  permissions_boundary = var.runtime_permissions_boundary_arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }, ArnLike = { "aws:SourceArn" = "arn:${data.aws_partition.current.partition}:scheduler:${var.aws_region}:${data.aws_caller_identity.current.account_id}:schedule-group/default" } }
    }]
  })
}

resource "aws_iam_role_policy" "deadline" {
  name = "terminate-run-instance"
  role = aws_iam_role.deadline.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "ec2:TerminateInstances", Resource = aws_instance.run.arn }]
  })
}
