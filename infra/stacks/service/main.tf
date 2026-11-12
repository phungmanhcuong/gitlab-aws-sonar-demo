# One environment of the service: API Gateway (HTTPS) -> Lambda alias "live" -> DynamoDB.
# Every deploy publishes a new Lambda version from the image of var.image_tag and moves "live" to it.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  name         = "${var.name}-${var.env}"
  account_id   = data.aws_caller_identity.current.account_id
  boundary_arn = "arn:${data.aws_partition.current.partition}:iam::${local.account_id}:policy/${var.name}-boundary"
}

# --- Image: resolve the commit tag to its digest, so the function pins exact bytes.
data "aws_ecr_repository" "app" {
  name = var.name
}

data "aws_ecr_image" "app" {
  repository_name = data.aws_ecr_repository.app.name
  image_tag       = var.image_tag
}

# --- Data
resource "aws_dynamodb_table" "links" {
  name                        = "${local.name}-links"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "code"
  deletion_protection_enabled = var.deletion_protection

  attribute {
    name = "code"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

# --- Function role: only this table and its own log group; bounded by the boundary the bootstrap created.
resource "aws_iam_role" "fn" {
  name                 = "${local.name}-fn"
  permissions_boundary = local.boundary_arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "fn" {
  name = "app"
  role = aws_iam_role.fn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Links"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.links.arn
      },
      {
        Sid      = "Logs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.fn.arn}:*"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "fn" {
  name              = "/aws/lambda/${local.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "access" {
  name              = "/aws/apigateway/${local.name}"
  retention_in_days = var.log_retention_days
}

# --- Function
resource "aws_lambda_function" "app" {
  function_name                  = local.name
  role                           = aws_iam_role.fn.arn
  package_type                   = "Image"
  image_uri                      = "${data.aws_ecr_repository.app.repository_url}@${data.aws_ecr_image.app.image_digest}"
  architectures                  = ["arm64"]
  memory_size                    = var.memory_mb
  timeout                        = 10
  publish                        = true
  reserved_concurrent_executions = var.max_concurrency

  environment {
    variables = {
      APP_ENV     = var.env
      APP_VERSION = var.image_tag
      TABLE_NAME  = aws_dynamodb_table.links.name
    }
  }

  depends_on = [aws_cloudwatch_log_group.fn, aws_iam_role_policy.fn]
}

resource "aws_lambda_alias" "live" {
  name             = "live"
  function_name    = aws_lambda_function.app.function_name
  function_version = aws_lambda_function.app.version
}

# --- HTTPS endpoint
resource "aws_apigatewayv2_api" "http" {
  name          = local.name
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "app" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_alias.live.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 12000
}

resource "aws_apigatewayv2_route" "all" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.app.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit    = var.throttle_rate
    throttling_burst_limit   = var.throttle_burst
    detailed_metrics_enabled = true
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      requestId = "$context.requestId"
      ip        = "$context.identity.sourceIp"
      time      = "$context.requestTime"
      method    = "$context.httpMethod"
      path      = "$context.path"
      status    = "$context.status"
      latencyMs = "$context.responseLatency"
      error     = "$context.integrationErrorMessage"
    })
  }
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.app.function_name
  qualifier     = aws_lambda_alias.live.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}

# --- Alarms (visible in the CloudWatch console; wire an SNS topic to notify people)
resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${local.name}-function-errors"
  alarm_description   = "The function raised errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.app.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "throttles" {
  alarm_name          = "${local.name}-function-throttles"
  alarm_description   = "Requests hit the reserved concurrency cap"
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = { FunctionName = aws_lambda_function.app.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.name}-api-5xx"
  alarm_description   = "The API answered with server errors"
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  dimensions          = { ApiId = aws_apigatewayv2_api.http.id, Stage = aws_apigatewayv2_stage.default.name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}
