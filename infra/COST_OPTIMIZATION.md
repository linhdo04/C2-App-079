# Demo cost optimization migration

This profile targets a small demonstration environment, not a highly available
production deployment. It changes the following architecture:

- regional GKE to zonal GKE, making the billing account's GKE free-tier credit
  applicable when it is available;
- managed Memorystore to a single Redis StatefulSet with a small persistent
  volume;
- two public load balancers to one by removing the Jenkins Ingress;
- smaller GKE nodes, Cloud SQL, Jenkins resources, and backup retention;
- Managed Service for Prometheus disabled.
- GKE Network Policy enforcement disabled to remove Calico's CPU reservation on
  the small demo nodes. The checked-in NetworkPolicy objects are therefore not
  enforced in this profile; production must enable enforcement or Dataplane V2.

## Expected interruption

The GKE topology change replaces the cluster and causes application downtime.
Cloud SQL is retained, but changing its tier can restart the instance briefly.
Terraform also destroys Memorystore after the application has moved to the
in-cluster Redis service.

Redis stores rate-limit counters and revoked JWT identifiers. At cutover, rotate
`JWT_SECRET_KEY` so every old token becomes invalid and users authenticate
again. Do not reuse the old key after deleting Memorystore.

## 1. Back up cluster state

Save these files outside the repository and protect them as secrets:

```bash
mkdir -p ../c2-app-cluster-backup
kubectl -n c2-app get secret backend-secrets -o json | jq \
  'del(.metadata.creationTimestamp, .metadata.resourceVersion,
    .metadata.uid, .metadata.managedFields,
    .metadata.annotations."kubectl.kubernetes.io/last-applied-configuration")' \
  > ../c2-app-cluster-backup/backend-secrets.json
kubectl -n jenkins get secret jenkins-admin -o json | jq \
  'del(.metadata.creationTimestamp, .metadata.resourceVersion,
    .metadata.uid, .metadata.managedFields,
    .metadata.annotations."kubectl.kubernetes.io/last-applied-configuration")' \
  > ../c2-app-cluster-backup/jenkins-admin.json
kubectl -n jenkins exec jenkins-0 -- tar czf /tmp/jenkins-home.tgz \
  -C /var/jenkins_home .
kubectl -n jenkins cp jenkins-0:/tmp/jenkins-home.tgz \
  ../c2-app-cluster-backup/jenkins-home.tgz
```

Record the current image tags and verify the PostgreSQL backup before
continuing:

```bash
kubectl -n c2-app get deployment backend frontend \
  -o jsonpath='{range .items[*]}{.metadata.name}{"="}{.spec.template.spec.containers[0].image}{"\n"}{end}'
gcloud sql backups list --instance devops-postgres
```

## 2. Review replacement plan

The existing cluster has deletion protection. Set
`cluster_deletion_protection = false` in the ignored `terraform.tfvars` only for
the migration, then run a saved plan:

```bash
cd infra/gke-data
terraform plan -out=cost-profile.tfplan
terraform show cost-profile.tfplan
```

The plan must retain the Cloud SQL instance and database. Expected destructive
actions are the old GKE cluster, Memorystore instance, and Jenkins public IP.
Do not apply if PostgreSQL is marked for replacement or destruction.

## 3. Apply infrastructure and reconnect kubectl

Run the reviewed plan during the maintenance window:

```bash
terraform apply cost-profile.tfplan
$(terraform output -raw get_credentials_command)
cd ../..
```

After the zonal cluster exists, restore `cluster_deletion_protection = true` and
apply that protection change separately.

## 4. Restore secrets and deploy workloads

Recreate the namespaces and secrets. The `jq` command below replaces
`JWT_SECRET_KEY` with a newly generated value before applying the Secret:

```bash
kubectl apply -f k8s/app/namespace.yaml
kubectl apply -f k8s/jenkins/namespace.yaml
NEW_JWT_SECRET="$(openssl rand -base64 48)"
jq --arg jwt "$NEW_JWT_SECRET" \
  '.data.JWT_SECRET_KEY = ($jwt | @base64)' \
  ../c2-app-cluster-backup/backend-secrets.json | kubectl apply -f -
kubectl apply -f ../c2-app-cluster-backup/jenkins-admin.json
kubectl apply -k k8s/app
kubectl -n c2-app rollout status statefulset/redis --timeout=5m
kubectl -n c2-app rollout status deployment/backend --timeout=5m
kubectl -n c2-app rollout status deployment/frontend --timeout=5m
```

Install Jenkins using `k8s/jenkins/README.md`, restore its home backup, and use
port-forwarding instead of a dedicated public Ingress.

## 5. Verify

```bash
kubectl -n c2-app get pods,svc,pvc,ingress,hpa
kubectl -n c2-app exec statefulset/redis -- sh -c \
  'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping'
curl --fail https://api.docker-linhdt.site/api/health
```

Check Billing Reports after 24–48 hours, grouped by SKU. Billing export and
reports lag behind resource changes, so the first day can still include charges
from the removed regional cluster and Memorystore.
