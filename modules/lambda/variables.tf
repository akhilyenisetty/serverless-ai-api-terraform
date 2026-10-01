variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "table_name" {
  description = "DynamoDB table the tools + chat memory use (passed from the storage module)."
  type        = string
}

variable "table_arn" {
  description = "ARN of the DynamoDB table, used to scope the Lambda's IAM policy (least privilege)."
  type        = string
}

# ---- Compute backend for the /chat endpoint ----
variable "compute_backend" {
  description = "Where chat inference runs: 'bedrock' (AWS, no external key) or 'byok' (bring your own key)."
  type        = string
}

variable "bedrock_model_id" {
  description = "Bedrock model id used when compute_backend = bedrock."
  type        = string
}

variable "llm_provider" {
  description = "Provider when compute_backend = byok: anthropic | openai | grok | huggingface."
  type        = string
}

variable "llm_model" {
  description = "Provider model name when compute_backend = byok."
  type        = string
}

variable "llm_base_url" {
  description = "OpenAI-compatible base URL for grok/HF when compute_backend = byok."
  type        = string
}

variable "secret_arn" {
  description = "Secrets Manager ARN holding the API key (byok mode). Empty string when using bedrock."
  type        = string
  default     = ""
}
