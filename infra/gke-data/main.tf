data "terraform_remote_state" "network" {
  backend = "local"

  config = {
    path = "../network/terraform.tfstate"
  }
}

locals {
  project_id = data.terraform_remote_state.network.outputs.project_id
  region     = data.terraform_remote_state.network.outputs.region
  zone       = data.terraform_remote_state.network.outputs.zone
  zones      = data.terraform_remote_state.network.outputs.zones

  cluster_name = data.terraform_remote_state.network.outputs.cluster_name

  network_name        = data.terraform_remote_state.network.outputs.network_name
  network_self_link   = data.terraform_remote_state.network.outputs.network_self_link
  subnet_name         = data.terraform_remote_state.network.outputs.subnet_name
  pods_range_name     = data.terraform_remote_state.network.outputs.pods_range_name
  services_range_name = data.terraform_remote_state.network.outputs.services_range_name

  private_services_range_name = data.terraform_remote_state.network.outputs.private_services_range_name

  labels = {
    project     = "c2-app"
    environment = var.environment
    managed_by  = "terraform"
  }
}

provider "google" {
  project = local.project_id
  region  = local.region
  zone    = local.zone
}

provider "google-beta" {
  project = local.project_id
  region  = local.region
  zone    = local.zone
}

# ----------------------------------------------------
# Required APIs for GKE and managed data services
# ----------------------------------------------------

resource "google_project_service" "container" {
  project = local.project_id
  service = "container.googleapis.com"

  disable_on_destroy = false
}

resource "google_project_service" "iam" {
  project = local.project_id
  service = "iam.googleapis.com"

  disable_on_destroy = false
}

resource "google_project_service" "sqladmin" {
  project = local.project_id
  service = "sqladmin.googleapis.com"

  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  project = local.project_id
  service = "artifactregistry.googleapis.com"

  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  project = local.project_id
  service = "cloudbuild.googleapis.com"

  disable_on_destroy = false
}

# ----------------------------------------------------
# GKE Cluster
# ----------------------------------------------------

module "gke" {
  source  = "terraform-google-modules/kubernetes-engine/google//modules/private-cluster"
  version = "~> 44.0"

  project_id = local.project_id
  name       = local.cluster_name

  regional = var.regional_cluster
  region   = local.region
  zones    = local.zones

  network    = local.network_name
  subnetwork = local.subnet_name

  ip_range_pods     = local.pods_range_name
  ip_range_services = local.services_range_name

  deletion_protection = var.cluster_deletion_protection

  enable_private_nodes    = true
  enable_private_endpoint = false
  master_ipv4_cidr_block  = "172.16.0.0/28"
  enable_shielded_nodes   = true
  identity_namespace      = "${local.project_id}.svc.id.goog"

  http_load_balancing                  = true
  horizontal_pod_autoscaling           = true
  monitoring_enable_managed_prometheus = false
  # Calico reserves too much CPU for the small demo nodes. Production profiles
  # must enable network policy enforcement or use Dataplane V2.
  network_policy       = false
  dns_cache            = false
  filestore_csi_driver = false

  release_channel = "REGULAR"

  create_service_account = true
  service_account_name   = "${local.cluster_name}-nodes"

  node_pools = [
    {
      name               = "main-pool"
      machine_type       = var.machine_type
      min_count          = var.node_min_count
      max_count          = var.node_max_count
      initial_node_count = var.node_count

      local_ssd_count = 0
      spot            = false
      preemptible     = false

      disk_size_gb = var.node_disk_size_gb
      disk_type    = "pd-balanced"
      image_type   = "COS_CONTAINERD"

      auto_repair  = true
      auto_upgrade = true
    }
  ]

  node_pools_oauth_scopes = {
    all = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }

  node_pools_labels = {
    all = local.labels
  }

  node_pools_tags = {
    all = [
      "gke-node",
      local.cluster_name
    ]
  }

  depends_on = [
    google_project_service.container,
    google_project_service.iam
  ]
}

# ----------------------------------------------------
# Cloud SQL PostgreSQL
# ----------------------------------------------------

resource "google_sql_database_instance" "postgres" {
  project = local.project_id

  name             = var.postgres_instance_name
  region           = local.region
  database_version = "POSTGRES_16"

  deletion_protection = var.postgres_deletion_protection

  settings {
    edition           = "ENTERPRISE"
    tier              = var.postgres_tier
    availability_type = var.postgres_availability_type

    disk_type       = "PD_SSD"
    disk_size       = 10
    disk_autoresize = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = var.postgres_point_in_time_recovery_enabled
      start_time                     = "18:00"
      transaction_log_retention_days = var.postgres_point_in_time_recovery_enabled ? 7 : null
      backup_retention_settings {
        retained_backups = var.postgres_backup_retained_count
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = local.network_self_link
    }

    user_labels = local.labels
  }

  depends_on = [
    google_project_service.sqladmin
  ]
}

resource "google_sql_database" "app" {
  project = local.project_id

  name     = var.postgres_database
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "app" {
  project = local.project_id

  name     = var.postgres_user
  instance = google_sql_database_instance.postgres.name
  password = var.postgres_password
}

# ----------------------------------------------------
# Artifact Registry
# ----------------------------------------------------

resource "google_artifact_registry_repository" "app_registry" {
  project       = local.project_id
  location      = local.region
  repository_id = var.artifact_registry_name

  description = "Docker Artifact Registry for C2 App"
  format      = "DOCKER"
  mode        = "STANDARD_REPOSITORY"

  labels = local.labels

  depends_on = [
    google_project_service.artifactregistry
  ]
}

resource "google_artifact_registry_repository_iam_member" "gke_artifact_registry_reader" {
  project    = local.project_id
  location   = local.region
  repository = google_artifact_registry_repository.app_registry.name

  role   = "roles/artifactregistry.reader"
  member = "serviceAccount:${module.gke.service_account}"

  depends_on = [
    module.gke,
    google_artifact_registry_repository.app_registry
  ]
}

# Stable public address referenced by the GKE Ingress manifest.
resource "google_compute_global_address" "app_ingress" {
  project = local.project_id
  name    = "c2-app-ingress-ip"
}

# Jenkins agents use Workload Identity to push images without service-account
# keys stored in Jenkins credentials.
resource "google_service_account" "jenkins_agent" {
  project      = local.project_id
  account_id   = "jenkins-agent"
  display_name = "Jenkins Kubernetes build agents"
}

resource "google_artifact_registry_repository_iam_member" "jenkins_writer" {
  project    = local.project_id
  location   = local.region
  repository = google_artifact_registry_repository.app_registry.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.jenkins_agent.email}"
}

resource "google_project_iam_member" "jenkins_cloud_build_editor" {
  project = local.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.jenkins_agent.email}"
}

resource "google_project_iam_member" "jenkins_cloud_build_runner" {
  project = local.project_id
  role    = "roles/cloudbuild.builds.builder"
  member  = "serviceAccount:${google_service_account.jenkins_agent.email}"
}

resource "google_service_account_iam_member" "jenkins_cloud_build_act_as" {
  service_account_id = google_service_account.jenkins_agent.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.jenkins_agent.email}"
}

resource "google_project_iam_member" "jenkins_service_usage" {
  project = local.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.jenkins_agent.email}"
}

resource "google_storage_bucket" "jenkins_build_source" {
  project                     = local.project_id
  name                        = "${local.project_id}-jenkins-build-source"
  location                    = local.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket_iam_member" "jenkins_build_source" {
  bucket = google_storage_bucket.jenkins_build_source.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.jenkins_agent.email}"
}

resource "google_service_account_iam_member" "jenkins_workload_identity" {
  service_account_id = google_service_account.jenkins_agent.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${local.project_id}.svc.id.goog[jenkins/jenkins-agent]"
}
