provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "gitlab-aws-sonar-demo"
      Stack     = "shared"
      ManagedBy = "terraform"
    }
  }
}
