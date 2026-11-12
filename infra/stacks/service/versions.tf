terraform {
  required_version = ">= 1.10" # S3 native state locking (use_lockfile)

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
  }

  # bucket, key and region come from `terraform init -backend-config=...` (see ci/infra.yml).
  backend "s3" {
    use_lockfile = true
    encrypt      = true
  }
}
