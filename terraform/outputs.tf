# These values are printed after `terraform apply` and can be
# referenced by scripts and CI/CD pipelines.

output "cluster_name" {
  description = "Name of the EKS cluster"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = aws_eks_cluster.main.endpoint
}

output "ecr_repository_url" {
  description = "URL of the ECR repository for pushing images"
  value       = aws_ecr_repository.counter_service.repository_url
}

output "region" {
  description = "AWS region"
  value       = var.region
}
