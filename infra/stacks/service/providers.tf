provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "gitlab-aws-sonar-demo"
      Stack       = "service"
      Environment = var.env
      ManagedBy   = "terraform"
    }
  }
}
