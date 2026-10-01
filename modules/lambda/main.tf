# Lambda module: packages the app as a ZIP (no Docker needed) and runs it on a managed
# Python runtime. The app is an ASGI web app wrapped with Mangum, which translates API
# Gateway events into ASGI calls, so our Starlette app runs unchanged. IAM is least-privilege.
#
# Requires `python3` + `pip` on the machine running terraform (used to vendor Linux wheels).

# ---- Build the deployment package: Linux deps + app code ----
# --platform/--only-binary fetch Lambda-compatible (manylinux, cp312) wheels even on macOS.
resource "null_resource" "build" {
  triggers = {
    server       = filesha256("${path.module}/../../app/mcp_server.py")
    requirements = filesha256("${path.module}/../../app/requirements.txt")
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      rm -rf "${path.module}/build"
      mkdir -p "${path.module}/build"
      python3 -m pip install \
        -r "${path.module}/../../app/requirements.txt" \
        --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 \
        --only-binary=:all: --target "${path.module}/build"
      cp "${path.module}/../../app/mcp_server.py" "${path.module}/build/"
    EOT
  }
}

data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/build"
  output_path = "${path.module}/function.zip"
  depends_on  = [null_resource.build]
}

# ---- Execution role + least-privilege policy ----
resource "aws_iam_role" "lambda" {
  name = "${var.name_prefix}-mcp-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name = "${var.name_prefix}-mcp-policy"
  role = aws_iam_role.lambda.id

  # Least privilege: always logs + its own table; Bedrock only in bedrock mode; the
  # secret only in byok mode. concat() drops the empty lists when a mode is off.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid      = "Logs"
          Effect   = "Allow"
          Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
          Resource = "arn:aws:logs:*:*:*"
        },
        {
          # Scoped to ONLY this table (+ its indexes). The function can't touch anything else.
          Sid      = "DynamoDB"
          Effect   = "Allow"
          Action   = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
          Resource = [var.table_arn, "${var.table_arn}/index/*"]
        }
      ],
      var.compute_backend == "bedrock" ? [
        {
          Sid      = "Bedrock"
          Effect   = "Allow"
          Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
          Resource = "*"
        }
      ] : [],
      var.secret_arn != "" ? [
        {
          Sid      = "ReadApiKeySecret"
          Effect   = "Allow"
          Action   = ["secretsmanager:GetSecretValue"]
          Resource = var.secret_arn
        }
      ] : []
    )
  })
}

# ---- Log group (explicit so we control retention) ----
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name_prefix}-mcp"
  retention_in_days = 14
}

# ---- The function (ZIP package on a managed Python runtime) ----
resource "aws_lambda_function" "mcp" {
  function_name    = "${var.name_prefix}-mcp"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "mcp_server.handler" # Mangum handler in mcp_server.py
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 30
  memory_size      = 512

  environment {
    variables = {
      TABLE_NAME       = var.table_name
      COMPUTE_BACKEND  = var.compute_backend
      BEDROCK_MODEL_ID = var.bedrock_model_id
      LLM_PROVIDER     = var.llm_provider
      LLM_MODEL        = var.llm_model
      LLM_BASE_URL          = var.llm_base_url
      SECRET_ARN            = var.secret_arn
      EXTERNAL_MCP_SERVERS  = var.external_mcp_servers_json
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda,
  ]
}

# ---- A basic alarm so errors are visible (good DevOps signal for reviewers) ----
resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${var.name_prefix}-mcp-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Fires when the MCP Lambda logs any errors in a 5-minute window."
  dimensions          = { FunctionName = aws_lambda_function.mcp.function_name }
}
