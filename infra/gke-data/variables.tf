variable "node_count" {
  description = "Initial number of GKE nodes per zone"
  type        = number
  default     = 3
}

variable "regional_cluster" {
  description = "Create a regional GKE cluster; keep false for the low-cost zonal demo profile"
  type        = bool
  default     = false
}

variable "cluster_deletion_protection" {
  description = "Protect the GKE cluster from deletion; disable only during a reviewed topology migration"
  type        = bool
  default     = true
}

variable "node_min_count" {
  description = "Minimum number of GKE nodes per zone"
  type        = number
  default     = 1
}

variable "node_max_count" {
  description = "Maximum number of GKE nodes per zone"
  type        = number
  default     = 3
}

variable "machine_type" {
  description = "GKE node machine type"
  type        = string
  default     = "e2-medium"
}

variable "node_disk_size_gb" {
  description = "GKE node disk size in GB"
  type        = number
  default     = 20
}

variable "postgres_instance_name" {
  description = "Cloud SQL PostgreSQL instance name"
  type        = string
  default     = "devops-postgres"
}

variable "postgres_database" {
  description = "Application database name"
  type        = string
  default     = "appdb"
}

variable "postgres_user" {
  description = "Application database user"
  type        = string
  default     = "appuser"
}

variable "postgres_password" {
  description = "Application database password"
  type        = string
  sensitive   = true
}

variable "artifact_registry_name" {
  description = "Artifact Registry Docker repository name"
  type        = string
  default     = "c2-app"
}

variable "environment" {
  description = "Deployment environment label"
  type        = string
  default     = "production"
}

variable "postgres_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-f1-micro"
}

variable "postgres_point_in_time_recovery_enabled" {
  description = "Enable PostgreSQL point-in-time recovery; disable for low-cost demo environments"
  type        = bool
  default     = false
}

variable "postgres_backup_retained_count" {
  description = "Number of automated Cloud SQL backups to retain"
  type        = number
  default     = 3

  validation {
    condition     = var.postgres_backup_retained_count >= 1 && var.postgres_backup_retained_count <= 365
    error_message = "postgres_backup_retained_count must be between 1 and 365."
  }
}

variable "postgres_availability_type" {
  description = "Cloud SQL availability type; use ZONAL for demo and REGIONAL for HA"
  type        = string
  default     = "ZONAL"

  validation {
    condition     = contains(["ZONAL", "REGIONAL"], var.postgres_availability_type)
    error_message = "postgres_availability_type must be ZONAL or REGIONAL."
  }
}

variable "postgres_deletion_protection" {
  description = "Protect the production database from accidental deletion"
  type        = bool
  default     = true
}
