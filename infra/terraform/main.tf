terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
  }

  backend "s3" {
    bucket = "aiops-incident-commander-tfstate"
    key    = "infra/terraform.tfstate"
    region = "us-east-1"
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "aiops-incident-commander"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# ─── VPC ────────────────────────────────────────────────────────────────────

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${var.cluster_name}-vpc"
  cidr = var.vpc_cidr

  azs             = var.availability_zones
  private_subnets = var.private_subnet_cidrs
  public_subnets  = var.public_subnet_cidrs

  enable_nat_gateway     = true
  single_nat_gateway     = var.environment == "dev"
  enable_dns_hostnames   = true
  enable_dns_support     = true

  public_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                    = 1
  }
  private_subnet_tags = {
    "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"           = 1
  }
}

# ─── EKS ─────────────────────────────────────────────────────────────────────

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = var.kubernetes_version

  vpc_id                         = module.vpc.vpc_id
  subnet_ids                     = module.vpc.private_subnets
  cluster_endpoint_public_access = true

  # Managed node groups
  eks_managed_node_groups = {
    aiops_system = {
      name           = "aiops-system"
      instance_types = ["t3.medium"]
      min_size       = 2
      max_size       = 5
      desired_size   = 2

      labels = {
        role = "system"
      }
      taints = []
    }

    aiops_agent = {
      name           = "aiops-agent"
      instance_types = ["t3.large"]
      min_size       = 1
      max_size       = 3
      desired_size   = 1

      labels = {
        role = "agent"
      }
    }
  }

  # IAM roles for service accounts
  enable_irsa = true
}

# ─── ECR ─────────────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "aiops_collector" {
  name                 = "${var.cluster_name}/collector"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "aiops_agent" {
  name                 = "${var.cluster_name}/agent"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "aiops_executor" {
  name                 = "${var.cluster_name}/executor"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

# ─── S3 for incident snapshots ───────────────────────────────────────────────

resource "aws_s3_bucket" "incident_snapshots" {
  bucket = "${var.cluster_name}-incident-snapshots-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "incident_snapshots" {
  bucket = aws_s3_bucket.incident_snapshots.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "incident_snapshots" {
  bucket = aws_s3_bucket.incident_snapshots.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ─── IAM for agent service account ───────────────────────────────────────────

resource "aws_iam_role" "aiops_agent" {
  name = "${var.cluster_name}-agent-role"
  assume_role_policy = data.aws_iam_policy_document.aiops_agent_trust.json
}

data "aws_iam_policy_document" "aiops_agent_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:sub"
      values   = ["system:serviceaccount:${var.namespace}:aiops-agent"]
    }
  }
}

resource "aws_iam_role_policy" "aiops_agent_s3" {
  name   = "aiops-agent-s3"
  role   = aws_iam_role.aiops_agent.id
  policy = data.aws_iam_policy_document.aiops_s3.json
}

data "aws_iam_policy_document" "aiops_s3" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.incident_snapshots.arn,
      "${aws_s3_bucket.incident_snapshots.arn}/*"
    ]
  }
}

# ─── Data sources ─────────────────────────────────────────────────────────────

data "aws_caller_identity" "current" {}
