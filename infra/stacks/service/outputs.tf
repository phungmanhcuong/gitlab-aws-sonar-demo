output "api_url" {
  description = "HTTPS endpoint of this environment"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "image_tag" {
  description = "Commit SHA this environment runs"
  value       = var.image_tag
}

output "image_digest" {
  value = data.aws_ecr_image.app.image_digest
}

output "function_version" {
  description = "Lambda version the alias live points at"
  value       = aws_lambda_alias.live.function_version
}
