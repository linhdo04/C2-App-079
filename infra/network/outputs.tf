output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "zone" {
  value = var.zone
}

output "zones" {
  value = var.zones
}

output "cluster_name" {
  value = var.cluster_name
}

output "network_name" {
  value = local.network_name
}

output "network_self_link" {
  value = local.network_self_link
}

output "subnet_name" {
  value = local.subnet_name
}

output "pods_range_name" {
  value = local.pods_range_name
}

output "services_range_name" {
  value = local.services_range_name
}

output "private_services_range_name" {
  value = google_compute_global_address.private_services_range.name
}
