# Outputs surface useful values after `terraform apply`.

output "notes_table" {
  description = "DynamoDB table the MCP tools read/write."
  value       = module.storage.table_name
}

output "api_url" {
  description = "Base HTTPS URL of the deployed service."
  value       = module.api.api_url
}

output "ui_url" {
  description = "Open this in any browser to chat with your cloud AI (served from the Lambda)."
  value       = module.api.api_url
}

output "chat_url" {
  description = "Chat/agent endpoint. POST {\"message\": \"...\"} to use cloud AI from any device."
  value       = "${module.api.api_url}/chat"
}

output "mcp_url" {
  description = "Remote MCP endpoint (bonus). Point Claude Desktop / Cursor / Copilot at this."
  value       = "${module.api.api_url}/mcp"
}
