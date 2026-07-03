output "cluster_name" {
  value = module.gke.name
}

output "cluster_location" {
  value = module.gke.location
}

output "network_name" {
  value = local.network_name
}

output "subnet_name" {
  value = local.subnet_name
}

output "node_pools" {
  value = module.gke.node_pools_names
}

output "node_service_account" {
  value = module.gke.service_account
}

output "get_credentials_command" {
  value = "gcloud container clusters get-credentials ${module.gke.name} --region ${local.region} --project ${local.project_id}"
}

output "postgres_private_ip" {
  value = google_sql_database_instance.postgres.private_ip_address
}

output "postgres_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}

output "postgres_database" {
  value = google_sql_database.app.name
}

output "postgres_user" {
  value = google_sql_user.app.name
}

output "redis_host" {
  value = google_redis_instance.redis.host
}

output "redis_port" {
  value = google_redis_instance.redis.port
}

output "redis_auth_string" {
  description = "Sensitive Redis AUTH value; store it in a secret manager"
  value       = google_redis_instance.redis.auth_string
  sensitive   = true
}

output "artifact_registry_repository" {
  value = google_artifact_registry_repository.app_registry.name
}

output "backend_image_repository" {
  value = "${local.region}-docker.pkg.dev/${local.project_id}/${var.artifact_registry_name}/backend"
}

output "frontend_image_repository" {
  value = "${local.region}-docker.pkg.dev/${local.project_id}/${var.artifact_registry_name}/frontend"
}

output "ingress_ip" {
  value = google_compute_global_address.app_ingress.address
}

output "jenkins_ingress_ip" {
  value = google_compute_global_address.jenkins_ingress.address
}

output "jenkins_agent_service_account" {
  value = google_service_account.jenkins_agent.email
}

output "jenkins_build_source_bucket" {
  value = google_storage_bucket.jenkins_build_source.name
}
