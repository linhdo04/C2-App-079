# GCP infrastructure

The stacks are applied in order: `network`, then `gke-data`. The production
defaults create a regional GKE cluster, regional Cloud SQL with backups and
point-in-time recovery, highly available Memorystore Redis with AUTH, Artifact
Registry, and a reserved global ingress IP.

Copy each `terraform.tfvars.example` to `terraform.tfvars`, set real values,
then run `terraform fmt`, `terraform validate`, and `terraform plan` in each
stack before applying. Variable files and state are ignored and must not be
committed.

The current `gke-data` stack reads the network stack from a local state file so
it remains compatible with the state already created for this repository. For
team/production operation, migrate both states to versioned, encrypted GCS
buckets with state locking and change the `terraform_remote_state` backend to
`gcs` before allowing CI to apply infrastructure. Do not copy an existing local
state file into Git.

Database deletion protection defaults to enabled. Deliberately disable it in a
reviewed change before destroying the production data stack.

Changing an existing zonal cluster to the regional private-cluster baseline
can replace the cluster. Always review the saved plan and prepare a migration
window; do not apply this transition blindly to a cluster already serving
traffic.
