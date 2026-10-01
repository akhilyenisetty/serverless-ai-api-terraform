# Terraform Syntax Cheat Sheet (the blocks you'll actually write)

Keep this open while you build. Every file in this repo is made of these blocks.

## The CLI loop
```bash
terraform init      # set up dir, download providers (run once, or after backend/module changes)
terraform fmt       # auto-format your .tf files
terraform validate  # check syntax
terraform plan      # preview changes (read-only, run constantly)
terraform apply      # make changes (prompts yes/no)
terraform output     # print outputs
terraform destroy    # tear everything down
terraform apply -auto-approve   # skip the yes prompt (careful)
```

## 1. Provider — who Terraform talks to
```hcl
provider "aws" {
  region = var.aws_region
}
```

## 2. Resource — one piece of infrastructure
Pattern: `resource "<TYPE>" "<LOCAL_NAME>" { ...args... }`
```hcl
resource "aws_dynamodb_table" "notes" {
  name         = "${var.project_name}-notes"   # string interpolation with ${...}
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {                                   # a nested block
    name = "id"
    type = "S"
  }
}
```
- `<TYPE>` = provider_resourcetype (look it up in the AWS provider docs).
- `<LOCAL_NAME>` = your nickname, used to reference it elsewhere (`aws_dynamodb_table.notes`).

## 3. Variable — an input
```hcl
variable "project_name" {
  description = "Prefix for resource names."
  type        = string          # string | number | bool | list(...) | map(...)
  default     = "mcp-on-aws"     # optional; if omitted, Terraform prompts for it
}
```
Use it anywhere with `var.project_name`.

## 4. Output — expose a value after apply
```hcl
output "table_name" {
  description = "The DynamoDB table name."
  value       = aws_dynamodb_table.notes.name
}
```

## 5. Reference / dependency — wire resources together
Just refer to another resource's attribute; Terraform figures out the order automatically.
```hcl
# format: <TYPE>.<LOCAL_NAME>.<ATTRIBUTE>
role_arn = aws_iam_role.lambda.arn
env_var  = aws_dynamodb_table.notes.name
```

## 6. Module — call a reusable folder of resources
```hcl
module "storage" {
  source      = "./modules/storage"   # path to the module folder
  name_prefix = var.project_name       # pass inputs (the module's variables)
}
```
Consume its outputs with `module.storage.table_name`.

Inside a module you write the SAME blocks (resource/variable/output) — a module is just a folder.

## 7. Data source — read something that already exists (don't create it)
```hcl
data "aws_caller_identity" "current" {}      # who am I
# use it: data.aws_caller_identity.current.account_id
```

## 8. Locals — computed/shared values (avoid repetition)
```hcl
locals {
  name = "${var.project_name}-${var.env}"
}
# use it: local.name
```

## 9. Common patterns you'll hit in this project

Zip a Lambda from source (Day 2):
```hcl
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../../app"
  output_path = "${path.module}/build/lambda.zip"
}
```

IAM role + attach a policy (Day 2, least privilege):
```hcl
resource "aws_iam_role" "lambda" {
  name = "${var.name_prefix}-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda_ddb" {
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Scan"]
      Resource = var.table_arn          # only THIS table = least privilege
    }]
  })
}
```

`for_each` — make many similar resources from a map/set (handy later):
```hcl
resource "aws_ssm_parameter" "cfg" {
  for_each = { LOG_LEVEL = "INFO", REGION = "us-east-1" }
  name     = "/${var.project_name}/${each.key}"
  type     = "String"
  value    = each.value
}
```

## Mental checklist when writing any resource
1. What's the resource **type**? (look it up in the AWS provider docs)
2. What are its **required arguments**?
3. Does it need to **reference** another resource? (use `type.name.attr`)
4. Should any value be a **variable** instead of hardcoded?
5. Do I need to **output** anything from it?
6. Run `terraform fmt` → `plan` → read it → `apply`.

## Where to look things up
- AWS provider docs (every resource, every argument):
  https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- Terraform language docs (syntax, functions, expressions):
  https://developer.hashicorp.com/terraform/language
