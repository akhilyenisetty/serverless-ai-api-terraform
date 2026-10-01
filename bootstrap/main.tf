# One-time bootstrap: creates the S3 bucket + DynamoDB table that hold the MAIN stack's
# remote state. This uses LOCAL state (chicken-and-egg: you can't store state remotely
# in a bucket that doesn't exist yet). Run this once, then wire backend.tf in the root.

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "state" {
  bucket = "ai-doc-api-tfstate-${random_id.suffix.hex}"
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "lock" {
  name         = "ai-doc-api-tflock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"
  attribute {
    name = "LockID"
    type = "S"
  }
}

# After apply, copy these two values into the root backend.tf.
output "state_bucket" { value = aws_s3_bucket.state.id }
output "lock_table" { value = aws_dynamodb_table.lock.name }
