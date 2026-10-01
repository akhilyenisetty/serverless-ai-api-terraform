# Storage module: the DynamoDB "knowledge base" table the MCP server's tools read and write.
# A "module" is just a reusable folder of Terraform. The root module calls this one.

resource "aws_dynamodb_table" "notes" {
  name         = "${var.name_prefix}-notes"
  billing_mode = "PAY_PER_REQUEST" # on-demand: no capacity planning, cheap for low traffic
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }
}
