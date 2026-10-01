# Values the api module needs to wire API Gateway to this function.
output "invoke_arn" {
  description = "ARN API Gateway uses to invoke the function."
  value       = aws_lambda_function.mcp.invoke_arn
}

output "function_name" {
  description = "Function name (needed to grant API Gateway invoke permission)."
  value       = aws_lambda_function.mcp.function_name
}
