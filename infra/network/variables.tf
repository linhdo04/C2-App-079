variable "project_id" {
  description = "Google Cloud project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud region"
  type        = string
  default     = "asia-southeast1"
}

variable "zone" {
  description = "Google Cloud zone"
  type        = string
  default     = "asia-southeast1-a"
}

variable "zones" {
  description = "Zones used by the regional GKE node pools"
  type        = list(string)
  default = [
    "asia-southeast1-a",
    "asia-southeast1-b",
    "asia-southeast1-c",
  ]
}

variable "cluster_name" {
  description = "Base name for GKE/network resources"
  type        = string
  default     = "devops-gke-demo"
}
