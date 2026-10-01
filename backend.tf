# Remote state: store this project's state in the S3 bucket + DynamoDB lock table that the
# bootstrap created. Filled in with the bootstrap's outputs.
terraform {
  backend "s3" {
    bucket         = "ai-doc-api-tfstate-d342be23"         # from bootstrap output: state_bucket
    key            = "serverless-ai-api/terraform.tfstate" # path of this project's state file inside the bucket
    region         = "us-east-1"
    dynamodb_table = "ai-doc-api-tflock" # from bootstrap output: lock_table
    encrypt        = true                # encrypt the state at rest
  }
}
