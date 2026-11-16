resource "aws_iam_openid_connect_provider" "github" {
  count          = var.existing_oidc_provider_arn == "" ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

locals {
  oidc_arn         = var.existing_oidc_provider_arn != "" ? var.existing_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn
  role_arn_pattern = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:role/${var.project_name}-run-*"
}

# Todos os papéis criados pelo workflow precisam desta fronteira. Mesmo que
# alterem suas políticas inline, não podem ultrapassar estas permissões.
resource "aws_iam_policy" "runtime_boundary" {
  name = "${var.project_name}-runtime-boundary"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"], Resource = "${aws_s3_bucket.results.arn}/runs/*" },
      { Effect = "Allow", Action = ["s3:ListBucket", "s3:GetBucketLocation", "s3:ListBucketMultipartUploads"], Resource = aws_s3_bucket.results.arn },
      { Effect = "Allow", Action = ["ssm:DescribeAssociation", "ssm:GetDeployablePatchSnapshotForInstance", "ssm:GetDocument", "ssm:DescribeDocument", "ssm:GetManifest", "ssm:GetParameter", "ssm:GetParameters", "ssm:ListAssociations", "ssm:ListInstanceAssociations", "ssm:PutInventory", "ssm:PutComplianceItems", "ssm:PutConfigurePackageResult", "ssm:UpdateAssociationStatus", "ssm:UpdateInstanceAssociationStatus", "ssm:UpdateInstanceInformation", "ssmmessages:CreateControlChannel", "ssmmessages:CreateDataChannel", "ssmmessages:OpenControlChannel", "ssmmessages:OpenDataChannel", "ec2messages:AcknowledgeMessage", "ec2messages:DeleteMessage", "ec2messages:FailMessage", "ec2messages:GetEndpoint", "ec2messages:GetMessages", "ec2messages:SendReply"], Resource = "*" },
      { Effect = "Allow", Action = "ec2:TerminateInstances", Resource = "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/*", Condition = { StringEquals = { "ec2:ResourceTag/Project" = var.project_name } } }
    ]
  })
}

resource "aws_iam_role" "github" {
  name                 = "${var.project_name}-github-actions"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = local.oidc_arn }
      Condition = { StringEquals = {
        "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        "token.actions.githubusercontent.com:sub" = distinct([for branch in [var.github_branch, var.github_default_branch] : "repo:${var.github_repository}:ref:refs/heads/${branch}"])
      } }
    }]
  })
}

resource "aws_iam_role_policy" "github" {
  name = "provision-validation-runs"
  role = aws_iam_role.github.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "ReadInfrastructure", Effect = "Allow", Action = ["ec2:Describe*"], Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = var.aws_region } } },
      { Sid = "ReadOfficialGPUImage", Effect = "Allow", Action = "ssm:GetParameter", Resource = "arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}::parameter/aws/service/deeplearning/ami/*" },
      { Sid = "CreateRunInstance", Effect = "Allow", Action = "ec2:RunInstances", Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = var.aws_region, "aws:RequestTag/Project" = var.project_name } } },
      # RunInstances também autoriza AMI, SG, subnet e ENI, que não recebem tags
      # no pedido; os novos instance/volume ficam restritos pela cláusula acima.
      { Sid = "UseRunPrerequisites", Effect = "Allow", Action = "ec2:RunInstances", Resource = ["arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}::image/*", "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:subnet/*", "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:security-group/*", "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:network-interface/*"] },
      { Sid = "ManageRunNetwork", Effect = "Allow", Action = ["ec2:CreateVpc", "ec2:DeleteVpc", "ec2:ModifyVpcAttribute", "ec2:CreateSubnet", "ec2:DeleteSubnet", "ec2:ModifySubnetAttribute", "ec2:CreateInternetGateway", "ec2:DeleteInternetGateway", "ec2:AttachInternetGateway", "ec2:DetachInternetGateway", "ec2:CreateRouteTable", "ec2:DeleteRouteTable", "ec2:CreateRoute", "ec2:DeleteRoute", "ec2:AssociateRouteTable", "ec2:DisassociateRouteTable", "ec2:ReplaceRouteTableAssociation", "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup", "ec2:AuthorizeSecurityGroupEgress", "ec2:RevokeSecurityGroupEgress", "ec2:CreateTags", "ec2:DeleteTags", "ec2:ModifyInstanceAttribute"], Resource = "*", Condition = { StringEquals = { "aws:RequestedRegion" = var.aws_region } } },
      { Sid = "TerminateProjectInstances", Effect = "Allow", Action = "ec2:TerminateInstances", Resource = "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/*", Condition = { StringEquals = { "ec2:ResourceTag/Project" = var.project_name } } },
      { Sid = "BoundedRunRoleCreation", Effect = "Allow", Action = "iam:CreateRole", Resource = local.role_arn_pattern, Condition = { ArnEquals = { "iam:PermissionsBoundary" = aws_iam_policy.runtime_boundary.arn } } },
      { Sid = "ManageRunRoles", Effect = "Allow", Action = ["iam:GetRole", "iam:DeleteRole", "iam:TagRole", "iam:UntagRole", "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:GetRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:ListInstanceProfilesForRole"], Resource = local.role_arn_pattern },
      { Sid = "AttachSSMOnly", Effect = "Allow", Action = ["iam:AttachRolePolicy", "iam:DetachRolePolicy"], Resource = local.role_arn_pattern, Condition = { ArnEquals = { "iam:PolicyARN" = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore" } } },
      { Sid = "RunInstanceProfiles", Effect = "Allow", Action = ["iam:CreateInstanceProfile", "iam:GetInstanceProfile", "iam:DeleteInstanceProfile", "iam:TagInstanceProfile", "iam:UntagInstanceProfile", "iam:AddRoleToInstanceProfile", "iam:RemoveRoleFromInstanceProfile"], Resource = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:instance-profile/${var.project_name}-run-*" },
      { Sid = "PassRunRoles", Effect = "Allow", Action = "iam:PassRole", Resource = local.role_arn_pattern, Condition = { StringEquals = { "iam:PassedToService" = ["ec2.amazonaws.com", "scheduler.amazonaws.com"] } } },
      { Sid = "ManageRunDeadlines", Effect = "Allow", Action = ["scheduler:CreateSchedule", "scheduler:GetSchedule", "scheduler:UpdateSchedule", "scheduler:DeleteSchedule", "scheduler:TagResource", "scheduler:UntagResource", "scheduler:ListTagsForResource"], Resource = "arn:${data.aws_partition.current.partition}:scheduler:${var.aws_region}:${data.aws_caller_identity.current.account_id}:schedule/default/${var.project_name}-*" },
      { Sid = "RunState", Effect = "Allow", Action = ["s3:ListBucket", "s3:GetBucketLocation"], Resource = aws_s3_bucket.state.arn },
      { Sid = "StateObjects", Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.state.arn}/runs/*" },
      { Sid = "RunResultsBucket", Effect = "Allow", Action = ["s3:ListBucket", "s3:GetBucketLocation"], Resource = aws_s3_bucket.results.arn },
      { Sid = "RunResultsObjects", Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:PutObjectTagging", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"], Resource = "${aws_s3_bucket.results.arn}/runs/*" }
    ]
  })
}
