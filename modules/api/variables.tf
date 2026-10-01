variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "lambda_invoke_arn" {
  description = "Invoke ARN of the Lambda to route requests to."
  type        = string
}

variable "lambda_function_name" {
  description = "Lambda function name (to grant API Gateway permission to invoke it)."
  type        = string
}
