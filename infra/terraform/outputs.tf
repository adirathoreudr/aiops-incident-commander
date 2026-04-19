output "cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
  sensitive   = true
}

output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "cluster_certificate_authority_data" {
  description = "Cluster CA data"
  value       = module.eks.cluster_certificate_authority_data
  sensitive   = true
}

output "ecr_collector_url" {
  description = "Collector ECR URL"
  value       = aws_ecr_repository.aiops_collector.repository_url
}

output "ecr_agent_url" {
  description = "Agent ECR URL"
  value       = aws_ecr_repository.aiops_agent.repository_url
}

output "ecr_executor_url" {
  description = "Executor ECR URL"
  value       = aws_ecr_repository.aiops_executor.repository_url
}

output "incident_snapshots_bucket" {
  description = "S3 bucket for incident snapshots"
  value       = aws_s3_bucket.incident_snapshots.bucket
}

output "agent_iam_role_arn" {
  description = "IAM role ARN for aiops-agent service account"
  value       = aws_iam_role.aiops_agent.arn
}
