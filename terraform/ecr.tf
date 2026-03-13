# --- ECR Repository ---
# This is where our CI pipeline pushes Docker images.
# EKS pulls images from here when creating pods.
resource "aws_ecr_repository" "counter_service" {
  name                 = "counter-service-guy"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Lifecycle policy: keep only the last 10 images to avoid storage costs
resource "aws_ecr_lifecycle_policy" "counter_service" {
  repository = aws_ecr_repository.counter_service.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}

# --- EBS Default Encryption ---
# Assignment requires encrypted storage.
# This ensures ALL new EBS volumes in the region are encrypted by default,
# including node root volumes and PersistentVolume claims.
resource "aws_ebs_encryption_by_default" "enabled" {
  enabled = true
}
