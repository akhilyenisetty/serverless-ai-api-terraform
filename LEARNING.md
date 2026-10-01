# Learn Terraform (focused prep before Day 1)

You already know AWS and backend, so you don't need a long course. You need the Terraform mental
model + the 7 concepts this project uses. Budget ~2 hours before Day 1.

## The mental model (read this first, 5 min)
Terraform is **declarative**: you write files that describe the infrastructure you *want*, and
Terraform makes reality match. You don't write step-by-step commands; you describe the end state.

The whole workflow is 5 commands:
- `terraform init`    → download providers, set up the working dir (run once per project/backend change)
- `terraform plan`    → READ-ONLY preview of what it will create/change/destroy (run constantly)
- `terraform apply`   → actually make the changes (asks "yes?" first)
- `terraform destroy` → tear it all down (so you don't get billed)
- `terraform fmt` / `validate` → auto-format / check syntax

## The 7 concepts you'll actually use (this is 90% of it)
1. **Provider** — the plugin that talks to a platform. We use the `aws` provider. (`providers.tf`)
2. **Resource** — one piece of infra: `resource "aws_dynamodb_table" "notes" { ... }`. Type + local name + config.
3. **Variable** — an input to make configs reusable: `var.project_name`. (`variables.tf`)
4. **Output** — a value you expose after apply (e.g. the table name, the API URL). (`outputs.tf`)
5. **State** — Terraform's record of what it created, in a `terraform.tfstate` file. **Remote state**
   stores it in S3 (shared, durable) with a DynamoDB lock so two people can't apply at once.
6. **Module** — a reusable folder of resources. Our root calls `modules/storage`, `modules/lambda`, etc.
7. **Reference / dependency** — resources refer to each other: `aws_s3_bucket.documents.arn`. Terraform
   builds a dependency graph from these and creates things in the right order automatically.

If you understand those 7, you can read every file in this repo.

## Best free resources (in priority order)
1. **HashiCorp "Get Started - AWS" (DO THIS ONE):** the official hands-on tutorial. Build → change →
   destroy real AWS infra, ~1 hour. It maps almost 1:1 to what you'll do here.
   https://developer.hashicorp.com/terraform/tutorials/aws-get-started
2. **All official tutorials hub** (modules, variables, state, remote state):
   https://developer.hashicorp.com/terraform/tutorials
3. **Terraform docs (reference, not a read-through):** look up any resource as you go, e.g. the AWS
   provider docs for `aws_lambda_function`, `aws_apigatewayv2_api`, `aws_dynamodb_table`.
   https://registry.terraform.io/providers/hashicorp/aws/latest/docs
4. **freeCodeCamp Terraform course (YouTube):** great if you prefer video for the fundamentals. Search
   "freeCodeCamp Terraform Course" on YouTube (~2.5 hrs, watch the first hour).
5. **Book (optional, for depth later):** *Terraform: Up & Running* by Yevgeniy Brikman — the standard
   reference. Not needed before Day 1; good for going deeper.

## Minimum to do before Day 1 (~2 hours)
- [ ] Read the mental model + 7 concepts above (15 min).
- [ ] Do the HashiCorp "Get Started - AWS" tutorial through **Build**, **Change**, and **Destroy**
      (~1 hr). This alone gets you comfortable with init/plan/apply/destroy on real AWS.
- [ ] Skim the "Define Input Variables", "Output Data", and "Store Remote State" tutorial pages so
      those words aren't new when we hit them here (20 min).
- [ ] Confirm your toolchain: `terraform -version` (>=1.6), `aws sts get-caller-identity` (proves your
      AWS CLI creds work).

Once that's done, open this repo's `versions.tf`, `providers.tf`, and `modules/storage/main.tf` and
you should be able to read them comfortably. Then start Day 1.

## Two things that trip up beginners (know them now)
- **State is precious.** Don't hand-edit or delete `terraform.tfstate`. That's why we put it in S3.
- **Always run `plan` before `apply`,** and read it. `plan` is your safety net; it shows exactly what
  will change before anything happens.
