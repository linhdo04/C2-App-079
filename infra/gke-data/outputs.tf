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
  value = "gcloud container clusters get-credentials ${module.gke.name} --${var.regional_cluster ? "region" : "zone"} ${module.gke.location} --project ${local.project_id}"
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

output "jenkins_agent_service_account" {
  value = google_service_account.jenkins_agent.email
}

output "jenkins_build_source_bucket" {
  value = google_storage_bucket.jenkins_build_source.name
}
