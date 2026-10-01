output "api_url" {
  description = "Base HTTPS URL of the API (the MCP endpoint is this URL + /mcp)."
  value       = aws_apigatewayv2_api.http.api_endpoint
}
