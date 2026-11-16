data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  prefix = "${var.project_name}-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
}

resource "aws_s3_bucket" "state" {
  bucket        = "${local.prefix}-state"
  force_destroy = false
  lifecycle { prevent_destroy = true }
}

resource "aws_s3_bucket" "results" {
  bucket        = "${local.prefix}-results"
  force_destroy = false
  lifecycle { prevent_destroy = true }
}

resource "aws_s3_bucket_public_access_block" "private" {
  for_each                = { state = aws_s3_bucket.state.id, results = aws_s3_bucket.results.id }
  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "versioned" {
  for_each = { state = aws_s3_bucket.state.id, results = aws_s3_bucket.results.id }
  bucket   = each.value
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "encrypted" {
  for_each = { state = aws_s3_bucket.state.id, results = aws_s3_bucket.results.id }
  bucket   = each.value
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_policy" "tls" {
  for_each = { state = aws_s3_bucket.state, results = aws_s3_bucket.results }
  bucket   = each.value.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "RequireTLS", Effect = "Deny", Principal = "*", Action = "s3:*"
      Resource  = [each.value.arn, "${each.value.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_s3_bucket_lifecycle_configuration" "results" {
  bucket     = aws_s3_bucket.results.id
  depends_on = [aws_s3_bucket_versioning.versioned]
  rule {
    id     = "result-retention"
    status = "Enabled"
    filter { prefix = "runs/" }
    expiration { days = var.results_retention_days }
    noncurrent_version_expiration { noncurrent_days = 7 }
    abort_incomplete_multipart_upload { days_after_initiation = 1 }
  }
  rule {
    id     = "short-lived-inputs"
    status = "Enabled"
    filter {
      tag {
        key   = "purpose"
        value = "run-input"
      }
    }
    expiration { days = 14 }
  }
}
