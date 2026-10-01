# Expose values the root module / lambda module need (the Lambda must know the table to use).
output "table_name" {
  value = aws_dynamodb_table.notes.name
}

output "table_arn" {
  value = aws_dynamodb_table.notes.arn
}
