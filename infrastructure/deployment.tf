resource "aws_cloudwatch_log_group" "api" { name = "/cloudmind/api" retention_in_days = 30 }
resource "aws_cloudwatch_log_group" "worker" { name = "/cloudmind/worker" retention_in_days = 30 }
resource "aws_ecs_cluster" "main" { name = "cloudmind" }

resource "aws_security_group" "alb" {
  name = "cloudmind-alb"; vpc_id = var.vpc_id
  ingress { from_port = 80, to_port = 80, protocol = "tcp", cidr_blocks = ["0.0.0.0/0"] }
  egress { from_port = 0, to_port = 0, protocol = "-1", cidr_blocks = ["0.0.0.0/0"] }
}
resource "aws_security_group" "api" {
  name = "cloudmind-api"; vpc_id = var.vpc_id
  ingress { from_port = 8000, to_port = 8000, protocol = "tcp", security_groups = [aws_security_group.alb.id] }
  egress { from_port = 0, to_port = 0, protocol = "-1", cidr_blocks = ["0.0.0.0/0"] }
}
resource "aws_security_group" "database" {
  name = "cloudmind-database"; vpc_id = var.vpc_id
  ingress { from_port = 5432, to_port = 5432, protocol = "tcp", security_groups = [aws_security_group.api.id] }
}

resource "aws_lb" "api" { name = "cloudmind-api" internal = false load_balancer_type = "application" security_groups = [aws_security_group.alb.id] subnets = var.public_subnet_ids }
resource "aws_lb_target_group" "api" {
  name = "cloudmind-api" port = 8000 protocol = "HTTP" vpc_id = var.vpc_id target_type = "ip"
  health_check { path = "/health" matcher = "200" }
}
resource "aws_lb_listener" "api" { load_balancer_arn = aws_lb.api.arn port = 80 protocol = "HTTP" default_action { type = "forward" target_group_arn = aws_lb_target_group.api.arn } }

resource "aws_db_subnet_group" "main" { name = "cloudmind" subnet_ids = var.private_subnet_ids }
resource "aws_db_instance" "postgres" {
  identifier = "cloudmind" engine = "postgres" engine_version = "16" instance_class = "db.t4g.micro"
  allocated_storage = 20 max_allocated_storage = 100 storage_encrypted = true
  db_name = "cloudmind" username = "cloudmind" password = var.db_password
  db_subnet_group_name = aws_db_subnet_group.main.name vpc_security_group_ids = [aws_security_group.database.id]
  backup_retention_period = 7 deletion_protection = true skip_final_snapshot = false final_snapshot_identifier = "cloudmind-final"
}

data "aws_iam_policy_document" "assume_ecs" { statement { actions = ["sts:AssumeRole"] principals { type = "Service", identifiers = ["ecs-tasks.amazonaws.com"] } } }
resource "aws_iam_role" "execution" { name = "cloudmind-ecs-execution" assume_role_policy = data.aws_iam_policy_document.assume_ecs.json }
resource "aws_iam_role_policy_attachment" "execution" { role = aws_iam_role.execution.name policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" }
data "aws_iam_policy_document" "execution_secrets" {
  statement { actions = ["secretsmanager:GetSecretValue"], resources = [var.database_url_secret_arn, var.jwt_secret_arn] }
}
resource "aws_iam_role_policy" "execution_secrets" { name = "cloudmind-task-secrets" role = aws_iam_role.execution.id policy = data.aws_iam_policy_document.execution_secrets.json }
resource "aws_iam_role" "api" { name = "cloudmind-api" assume_role_policy = data.aws_iam_policy_document.assume_ecs.json }
resource "aws_iam_role" "worker" { name = "cloudmind-worker" assume_role_policy = data.aws_iam_policy_document.assume_ecs.json }

data "aws_iam_policy_document" "api" {
  statement { actions = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"], resources = ["${aws_s3_bucket.documents.arn}/*"] }
  statement { actions = ["sqs:SendMessage"], resources = [aws_sqs_queue.processing.arn] }
  statement { actions = ["secretsmanager:GetSecretValue"], resources = [var.database_url_secret_arn, var.jwt_secret_arn] }
}
data "aws_iam_policy_document" "worker" {
  statement { actions = ["s3:GetObject"], resources = ["${aws_s3_bucket.documents.arn}/*"] }
  statement { actions = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"], resources = [aws_sqs_queue.processing.arn] }
  statement { actions = ["secretsmanager:GetSecretValue"], resources = [var.database_url_secret_arn, var.jwt_secret_arn] }
}
resource "aws_iam_role_policy" "api" { name = "cloudmind-api" role = aws_iam_role.api.id policy = data.aws_iam_policy_document.api.json }
resource "aws_iam_role_policy" "worker" { name = "cloudmind-worker" role = aws_iam_role.worker.id policy = data.aws_iam_policy_document.worker.json }

locals {
  shared_environment = [
    { name = "CLOUDMIND_STORAGE_BACKEND", value = "s3" }, { name = "CLOUDMIND_S3_BUCKET", value = aws_s3_bucket.documents.id },
    { name = "CLOUDMIND_QUEUE_BACKEND", value = "sqs" }, { name = "CLOUDMIND_SQS_QUEUE_URL", value = aws_sqs_queue.processing.url },
    { name = "CLOUDMIND_AWS_REGION", value = var.region }
  ]
  secrets = [{ name = "CLOUDMIND_DATABASE_URL", valueFrom = var.database_url_secret_arn }, { name = "CLOUDMIND_JWT_SECRET", valueFrom = var.jwt_secret_arn }]
}

resource "aws_ecs_task_definition" "api" {
  family = "cloudmind-api" network_mode = "awsvpc" requires_compatibilities = ["FARGATE"] cpu = 512 memory = 1024 execution_role_arn = aws_iam_role.execution.arn task_role_arn = aws_iam_role.api.arn
  container_definitions = jsonencode([{ name = "api", image = var.api_image, essential = true, portMappings = [{ containerPort = 8000 }], environment = local.shared_environment, secrets = local.secrets, logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.api.name, awslogs-region = var.region, awslogs-stream-prefix = "ecs" } } }])
}
resource "aws_ecs_task_definition" "worker" {
  family = "cloudmind-worker" network_mode = "awsvpc" requires_compatibilities = ["FARGATE"] cpu = 1024 memory = 2048 execution_role_arn = aws_iam_role.execution.arn task_role_arn = aws_iam_role.worker.arn
  container_definitions = jsonencode([{ name = "worker", image = var.worker_image, essential = true, environment = local.shared_environment, secrets = local.secrets, logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.worker.name, awslogs-region = var.region, awslogs-stream-prefix = "ecs" } } }])
}
resource "aws_ecs_service" "api" {
  name = "cloudmind-api" cluster = aws_ecs_cluster.main.id task_definition = aws_ecs_task_definition.api.arn desired_count = 1 launch_type = "FARGATE"
  network_configuration { subnets = var.private_subnet_ids security_groups = [aws_security_group.api.id] assign_public_ip = false }
  load_balancer { target_group_arn = aws_lb_target_group.api.arn container_name = "api" container_port = 8000 }
}
resource "aws_ecs_service" "worker" {
  name = "cloudmind-worker" cluster = aws_ecs_cluster.main.id task_definition = aws_ecs_task_definition.worker.arn desired_count = 1 launch_type = "FARGATE"
  network_configuration { subnets = var.private_subnet_ids security_groups = [aws_security_group.api.id] assign_public_ip = false }
}

output "api_url" { value = "http://${aws_lb.api.dns_name}" }
output "document_bucket" { value = aws_s3_bucket.documents.id }
output "database_host" { value = aws_db_instance.postgres.address }
output "api_repository" { value = aws_ecr_repository.api.repository_url }
output "worker_repository" { value = aws_ecr_repository.worker.repository_url }
