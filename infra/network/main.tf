provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

locals {
  network_name = "${var.cluster_name}-vpc"
  subnet_name  = "${var.cluster_name}-subnet"

  network_self_link = "projects/${var.project_id}/global/networks/${local.network_name}"

  pods_range_name     = "pods"
  services_range_name = "services"

  private_services_range_name = "${var.cluster_name}-private-services"

  labels = {
    project     = "c2-app"
    environment = "production"
    managed_by  = "terraform"
  }
}

# ----------------------------------------------------
# Required APIs for network stack
# ----------------------------------------------------

resource "google_project_service" "compute" {
  project = var.project_id
  service = "compute.googleapis.com"

  disable_on_destroy = false
}

resource "google_project_service" "service_networking" {
  project = var.project_id
  service = "servicenetworking.googleapis.com"

  disable_on_destroy = false
}

# ----------------------------------------------------
# VPC + Subnet + Secondary ranges
# ----------------------------------------------------

module "vpc" {
  source  = "terraform-google-modules/network/google"
  version = "~> 18.1"

  project_id   = var.project_id
  network_name = local.network_name
  routing_mode = "GLOBAL"

  subnets = [
    {
      subnet_name           = local.subnet_name
      subnet_ip             = "10.10.0.0/20"
      subnet_region         = var.region
      subnet_private_access = true
      subnet_flow_logs      = true
      description           = "Subnet for ${var.cluster_name} GKE cluster"
    }
  ]

  secondary_ranges = {
    (local.subnet_name) = [
      {
        range_name    = local.pods_range_name
        ip_cidr_range = "10.20.0.0/16"
      },
      {
        range_name    = local.services_range_name
        ip_cidr_range = "10.30.0.0/20"
      }
    ]
  }

  depends_on = [
    google_project_service.compute
  ]
}

# Private GKE nodes use Cloud NAT for outbound image pulls and external APIs.
resource "google_compute_router" "gke" {
  project = var.project_id
  name    = "${var.cluster_name}-router"
  region  = var.region
  network = local.network_self_link

  depends_on = [module.vpc]
}

resource "google_compute_router_nat" "gke" {
  project                            = var.project_id
  name                               = "${var.cluster_name}-nat"
  router                             = google_compute_router.gke.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}

# ----------------------------------------------------
# Private Service Access
#
# Used later by Cloud SQL private IP and Memorystore Redis.
# Keep this in the network stack.
# Do NOT destroy this every time you destroy GKE/Postgres/Redis.
# ----------------------------------------------------

resource "google_compute_global_address" "private_services_range" {
  project = var.project_id

  name          = local.private_services_range_name
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16

  network = local.network_self_link

  depends_on = [
    module.vpc,
    google_project_service.service_networking
  ]
}

resource "google_service_networking_connection" "private_services" {
  network = local.network_self_link
  service = "servicenetworking.googleapis.com"

  reserved_peering_ranges = [
    google_compute_global_address.private_services_range.name
  ]

  depends_on = [
    module.vpc,
    google_project_service.service_networking,
    google_compute_global_address.private_services_range
  ]
}
