terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" { region = var.region }

resource "aws_ecr_repository" "api" { name = "cloudmind-api" image_scanning_configuration { scan_on_push = true } }
resource "aws_ecr_repository" "worker" { name = "cloudmind-worker" image_scanning_configuration { scan_on_push = true } }

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

resource "aws_sqs_queue" "dlq" { name = "cloudmind-processing-dlq" }
resource "aws_sqs_queue" "processing" {
  name = "cloudmind-processing"
  visibility_timeout_seconds = 300
  redrive_policy = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dlq.arn, maxReceiveCount = 3 })
}
