# API module: a public HTTPS front door (API Gateway HTTP API) that forwards every request
# to the Lambda. HTTP API (v2) is the cheaper, simpler API Gateway flavor, ideal here.

resource "aws_apigatewayv2_api" "http" {
  name          = "${var.name_prefix}-api"
  protocol_type = "HTTP"
}

# Proxy integration: pass the raw request straight through to Lambda (the Web Adapter handles it).
resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.lambda_invoke_arn
  payload_format_version = "2.0"
}

# Catch-all route: send ANY method on ANY path to the integration (so /chat, /mcp work).
resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# Root route too, so the chat UI is served at the bare URL (/{proxy+} doesn't match "/").
resource "aws_apigatewayv2_route" "root" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# $default stage with auto-deploy = a stable public URL that updates on every apply.
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true
}

# Allow API Gateway to invoke the Lambda (without this, calls get 500s).
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
