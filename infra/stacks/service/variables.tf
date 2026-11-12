variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-southeast-1"
}

variable "name" {
  description = "Prefix of every resource; the ECR repository has this name"
  type        = string
  default     = "shortlinks"
}

variable "env" {
  description = "Environment: staging or production"
  type        = string

  validation {
    condition     = contains(["staging", "production"], var.env)
    error_message = "env must be staging or production."
  }
}

variable "image_tag" {
  description = "Commit SHA of the image to run; it must already be in ECR (built on main)"
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.image_tag))
    error_message = "image_tag must be a full 40-character commit SHA."
  }
}

variable "memory_mb" {
  description = "Lambda memory; CPU grows with it"
  type        = number
  default     = 512
}

variable "max_concurrency" {
  description = "Reserved concurrency: the most copies of the function that can run at once (cost and blast-radius cap)"
  type        = number
}

variable "throttle_rate" {
  description = "API Gateway steady-state requests per second"
  type        = number
}

variable "throttle_burst" {
  description = "API Gateway burst size"
  type        = number
}

variable "log_retention_days" {
  description = "How long CloudWatch keeps function and access logs"
  type        = number
}

variable "deletion_protection" {
  description = "Refuse to delete the DynamoDB table (production)"
  type        = bool
  default     = false
}
