mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
}

run "persistent_private_storage_and_oidc" {
  command = plan
  override_resource {
    target          = aws_iam_policy.runtime_boundary
    override_during = plan
    values          = { arn = "arn:aws:iam::123456789012:policy/distributed-ai-runtime-boundary" }
  }
  override_resource {
    target          = aws_s3_bucket.state
    override_during = plan
    values          = { id = "distributed-ai-test-state", arn = "arn:aws:s3:::distributed-ai-test-state" }
  }
  override_resource {
    target          = aws_s3_bucket.results
    override_during = plan
    values          = { id = "distributed-ai-test-results", arn = "arn:aws:s3:::distributed-ai-test-results" }
  }
  variables {
    existing_oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
  }
  assert {
    condition     = !aws_s3_bucket.state.force_destroy && !aws_s3_bucket.results.force_destroy
    error_message = "A limpeza de uma execução não pode remover o estado ou os resultados persistentes."
  }
  assert {
    condition     = alltrue([for block in aws_s3_bucket_public_access_block.private : block.block_public_acls && block.block_public_policy && block.ignore_public_acls && block.restrict_public_buckets])
    error_message = "Todos os buckets devem bloquear acesso público."
  }
  assert {
    condition     = toset(jsondecode(aws_iam_role.github.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"]) == toset(["repo:allansouzaallu/TCC1:ref:refs/heads/sistema-ia-distribuida", "repo:allansouzaallu/TCC1:ref:refs/heads/main"])
    error_message = "OIDC deve aceitar apenas o repositório e as branches configuradas."
  }
  assert {
    condition     = length(aws_iam_role_policy.github.policy) <= 10240
    error_message = "A política inline do GitHub deve caber na cota IAM de 10.240 caracteres por role."
  }
}
