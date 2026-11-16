# Uma única rede pública temporária permite baixar o modelo e publicar no S3.
# Não há NAT Gateway, Elastic IP nem portas de entrada expostas.
data "aws_availability_zones" "available" { state = "available" }

data "aws_ec2_instance_type_offerings" "gpu" {
  location_type = "availability-zone"
  filter {
    name   = "instance-type"
    values = [var.instance_type]
  }
}

locals {
  gpu_availability_zones = sort(tolist(setintersection(toset(data.aws_availability_zones.available.names), data.aws_ec2_instance_type_offerings.gpu.locations)))
}

resource "aws_vpc" "run" {
  cidr_block           = "10.84.0.0/24"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = local.name }
}

resource "aws_subnet" "run" {
  vpc_id                  = aws_vpc.run.id
  cidr_block              = "10.84.0.0/26"
  availability_zone       = try(local.gpu_availability_zones[0], null)
  map_public_ip_on_launch = true
  tags                    = { Name = local.name }
  lifecycle {
    precondition {
      condition     = length(local.gpu_availability_zones) > 0
      error_message = "O tipo de instância GPU escolhido não é oferecido nas zonas disponíveis desta região."
    }
  }
}

resource "aws_internet_gateway" "run" {
  vpc_id = aws_vpc.run.id
  tags   = { Name = local.name }
}

resource "aws_route_table" "run" {
  vpc_id = aws_vpc.run.id
  tags   = { Name = local.name }
}

resource "aws_route" "internet" {
  route_table_id         = aws_route_table.run.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.run.id
}

resource "aws_route_table_association" "run" {
  subnet_id      = aws_subnet.run.id
  route_table_id = aws_route_table.run.id
}

resource "aws_security_group" "run" {
  name_prefix = "${local.name}-"
  description = "No ingress; nodes and inference communicate only inside the host"
  vpc_id      = aws_vpc.run.id
  ingress     = []
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = local.name }
}
