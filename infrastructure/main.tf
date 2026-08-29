terraform { required_providers { aws = { source = "hashicorp/aws" } } }
provider "aws" { region = var.region }
variable "region" { type = string, default = "us-east-1" }
resource "aws_s3_bucket" "documents" { bucket_prefix = "cloudmind-documents-" }
resource "aws_sqs_queue" "processing" { name = "cloudmind-processing" visibility_timeout_seconds = 300 }
resource "aws_sqs_queue" "dlq" { name = "cloudmind-processing-dlq" }
output "document_bucket" { value = aws_s3_bucket.documents.id }
