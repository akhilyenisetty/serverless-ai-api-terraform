# Input variables make the stack reusable and configurable.
variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name prefix used for all resource names."
  type        = string
  default     = "mcp-on-aws"
}

variable "tags" {
  description = "Tags applied to every resource (good for cost tracking + ownership)."
  type        = map(string)
  default = {
    Project   = "serverless-ai-api-terraform"
    ManagedBy = "Terraform"
    Owner     = "Akhil Yenisetty"
  }
}

# ---------------------------------------------------------------------------
# Compute backend for the /chat endpoint — YOUR choice as the operator.
#   "bedrock" : inference runs in your own AWS via Bedrock. No external key.
#   "byok"    : bring your own key (Anthropic / OpenAI / Grok / HF).
# ---------------------------------------------------------------------------
variable "compute_backend" {
  description = "Chat compute backend: 'bedrock' or 'byok'."
  type        = string
  default     = "bedrock"
  validation {
    condition     = contains(["bedrock", "byok"], var.compute_backend)
    error_message = "compute_backend must be 'bedrock' or 'byok'."
  }
}

variable "bedrock_model_id" {
  description = "Bedrock model id (bedrock mode). Newer Claude models require a cross-region inference profile (the 'us.'-prefixed id)."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "llm_provider" {
  description = "Provider for byok mode: anthropic | openai | grok | huggingface."
  type        = string
  default     = "anthropic"
}

variable "llm_model" {
  description = "Model name for byok mode (e.g. claude-3-haiku-20240307, gpt-4o-mini)."
  type        = string
  default     = ""
}

variable "llm_base_url" {
  description = "OpenAI-compatible base URL for grok/HF in byok mode (e.g. https://api.x.ai/v1)."
  type        = string
  default     = "https://api.openai.com/v1"
}

variable "llm_api_key" {
  description = "API key for byok mode. Optional: leave blank and set the secret value out-of-band (recommended, keeps the key out of state)."
  type        = string
  default     = ""
  sensitive   = true
}

# External MCP servers the chat can connect to (option C). The chat discovers each
# server's tools and can call them. Example:
#   external_mcp_servers = [{ name = "whatsapp", url = "https://.../mcp", auth = "token" }]
variable "external_mcp_servers" {
  description = "List of external MCP servers {name, url, auth} the chat agent can use."
  type = list(object({
    name = string
    url  = string
    auth = optional(string, "")
  }))
  default   = []
  sensitive = true # auth tokens
}
