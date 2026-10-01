# Root module: wires the building blocks together.
#   storage -> DynamoDB table (MCP notes + chat conversation memory)
#   secret  -> Secrets Manager container for the BYOK API key (byok mode only)
#   lambda  -> the server: /chat agent (Bedrock or BYOK) + remote MCP server
#   api     -> public HTTPS front door (API Gateway) that reaches the Lambda

module "storage" {
  source      = "./modules/storage"
  name_prefix = var.project_name
}

# Created only in byok mode. The key VALUE is set either from var.llm_api_key or,
# preferably, out-of-band so it never lands in Terraform state:
#   aws secretsmanager put-secret-value --secret-id <name> --secret-string 'sk-...'
resource "aws_secretsmanager_secret" "llm" {
  count = var.compute_backend == "byok" ? 1 : 0
  name  = "${var.project_name}-llm-key"
}

resource "aws_secretsmanager_secret_version" "llm" {
  count         = var.compute_backend == "byok" && var.llm_api_key != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.llm[0].id
  secret_string = var.llm_api_key
}

module "lambda" {
  source      = "./modules/lambda"
  name_prefix = var.project_name
  table_name  = module.storage.table_name
  table_arn   = module.storage.table_arn

  compute_backend  = var.compute_backend
  bedrock_model_id = var.bedrock_model_id
  llm_provider     = var.llm_provider
  llm_model        = var.llm_model
  llm_base_url     = var.llm_base_url
  secret_arn       = length(aws_secretsmanager_secret.llm) > 0 ? aws_secretsmanager_secret.llm[0].arn : ""
}

module "api" {
  source               = "./modules/api"
  name_prefix          = var.project_name
  lambda_invoke_arn    = module.lambda.invoke_arn
  lambda_function_name = module.lambda.function_name
}
