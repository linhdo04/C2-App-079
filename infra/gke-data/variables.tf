variable "node_count" {
  description = "Initial number of GKE nodes per zone"
  type        = number
  default     = 3
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
  default     = "e2-standard-2"
}

variable "node_disk_size_gb" {
  description = "GKE node disk size in GB"
  type        = number
  default     = 30
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

variable "redis_instance_name" {
  description = "Memorystore Redis instance name"
  type        = string
  default     = "devops-redis"
}

variable "redis_memory_size_gb" {
  description = "Redis memory size in GB"
  type        = number
  default     = 1
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
  default     = "db-custom-1-3840"
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

variable "redis_tier" {
  description = "Memorystore service tier; use BASIC for demo and STANDARD_HA for HA"
  type        = string
  default     = "BASIC"

  validation {
    condition     = contains(["BASIC", "STANDARD_HA"], var.redis_tier)
    error_message = "redis_tier must be BASIC or STANDARD_HA."
  }
}
