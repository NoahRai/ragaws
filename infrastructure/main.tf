terraform { required_providers { aws = { source = "hashicorp/aws" } } }
provider "aws" { region = var.region }
variable "region" { type = string, default = "us-east-1" }
resource "aws_s3_bucket" "documents" { bucket_prefix = "cloudmind-documents-" }
resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id
  block_public_acls = true
  block_public_policy = true
  ignore_public_acls = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}
resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_sqs_queue" "processing" { name = "cloudmind-processing" visibility_timeout_seconds = 300 }
resource "aws_sqs_queue" "dlq" { name = "cloudmind-processing-dlq" }
output "document_bucket" { value = aws_s3_bucket.documents.id }
