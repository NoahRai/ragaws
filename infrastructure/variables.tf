variable "region" { type = string, default = "us-east-1" }
variable "vpc_id" { type = string, description = "Existing VPC ID for CloudMind." }
variable "public_subnet_ids" { type = list(string), description = "At least two public subnet IDs for the ALB." }
variable "private_subnet_ids" { type = list(string), description = "At least two private subnet IDs for ECS and RDS." }
variable "api_image" { type = string, description = "Immutable ECR image URI for the FastAPI service." }
variable "worker_image" { type = string, description = "Immutable ECR image URI for the worker service." }
variable "database_url_secret_arn" { type = string, description = "Secrets Manager ARN containing a DATABASE_URL string." }
variable "jwt_secret_arn" { type = string, description = "Secrets Manager ARN containing the JWT secret." }
variable "db_password" { type = string, sensitive = true, description = "RDS master password; supply via TF_VAR_db_password and protect state." }
