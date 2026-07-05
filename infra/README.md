# GCP infrastructure

The stacks are applied in order: `network`, then `gke-data`. The checked-in
defaults are a cost-optimized demo profile: a zonal GKE cluster, small nodes,
zonal shared-core Cloud SQL, Redis inside GKE, Artifact Registry, and one
reserved global IP for the application ingress. Automated database backups
remain enabled, while point-in-time recovery and Managed Service for Prometheus
are disabled. GKE Network Policy enforcement is also disabled because Calico's
system reservations leave insufficient CPU on `e2-medium` demo nodes.

For production, override the demo defaults with a regional cluster, a larger
node type, a dedicated Cloud SQL tier, regional database availability,
point-in-time recovery, longer backup retention, and managed highly available
Redis. Review the resulting monthly estimate and Terraform plan before applying
it. Production must also enable Network Policy enforcement or Dataplane V2.

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

The demo profile does not provision a public Jenkins IP. Access Jenkins through
`kubectl port-forward`; adding a dedicated GCE Ingress creates another external
load balancer with a continuous hourly cost.

## Apply the demo cost profile

Changing an existing regional cluster to zonal replaces the cluster. Follow
[COST_OPTIMIZATION.md](./COST_OPTIMIZATION.md) from start to finish. Do not run
`terraform apply` against the existing regional cluster without completing the
backup and migration steps. Terraform must report no Cloud SQL replacement or
destruction before approval.

Changing an existing zonal cluster to the regional private-cluster baseline
can replace the cluster. Always review the saved plan and prepare a migration
window; do not apply this transition blindly to a cluster already serving
traffic.
