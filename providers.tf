# The AWS provider is what lets Terraform talk to your AWS account.
# Credentials come from your environment (AWS CLI: `aws configure`), NOT from this file.
provider "aws" {
  region = var.aws_region

  # default_tags are applied to every taggable resource this provider creates.
  default_tags {
    tags = var.tags
  }
}
