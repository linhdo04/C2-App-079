# C2 App on GKE

This directory contains the production baseline for the application. It assumes
the GKE, Cloud SQL, Memorystore, Artifact Registry, and static ingress IP from
`infra/` already exist.

## Required values

Do not apply the manifests with placeholders. Replace these values first:

- `PROJECT_ID` and `RELEASE_TAG` in `app/kustomization.yaml`
- `docker-linhdt.site` and `api.docker-linhdt.site` in the Ingress and backend ConfigMap
- Cloud SQL and Redis private IPs in `app/backend/configmap.yaml`; obtain them
  from `terraform output` in `infra/gke-data`
- all values shown in `app/backend/secret.example.yaml`

Build the frontend with the public API prefix because `NEXT_PUBLIC_*` values
are compiled into the browser bundle:

```bash
docker build \
  --build-arg NEXT_PUBLIC_API_URL=https://api.docker-linhdt.site/api \
  -t asia-southeast1-docker.pkg.dev/PROJECT_ID/c2-app/frontend:RELEASE_TAG \
  frontend
```

Build the backend with the same immutable release tag. Push both images before
updating the cluster. Never use `latest` for a production rollout.

## Secrets

`app/backend/secret.example.yaml` is a template and is intentionally excluded from the
Kustomize resources. In production, synchronize these keys from Google Secret
Manager with an approved secret operator. For a manual bootstrap only, create
the same `backend-secrets` Secret from a local, git-ignored env file:

```bash
kubectl create namespace c2-app --dry-run=client -o yaml | kubectl apply -f -
kubectl -n c2-app create secret generic backend-secrets \
  --from-env-file=backend.production.env \
  --dry-run=client -o yaml | kubectl apply -f -
```

The env file must define `POSTGRES_PASSWORD`, `REDIS_PASSWORD`,
`JWT_SECRET_KEY`, `DEEPSEEK_API_KEY`, `TAVILY_API_KEY`, and optionally
`LANGSMITH_API_KEY`. The Redis password is the sensitive
`redis_auth_string` Terraform output.

## Deploy

Point the domain's A record to the `ingress_ip` Terraform output, then run:

```bash
kubectl apply -k k8s/app
kubectl -n c2-app rollout status deployment/backend --timeout=5m
kubectl -n c2-app rollout status deployment/frontend --timeout=5m
```

Run database migrations once per release, before the backend rollout receives
traffic. The migration Job is excluded from Kustomize because Jobs are
immutable; substitute the exact backend image and use a release-specific name:

```bash
sed -e 's|name: backend-migrate|name: backend-migrate-RELEASE_TAG|' \
    -e 's|image: BACKEND_IMAGE|image: asia-southeast1-docker.pkg.dev/PROJECT_ID/c2-app/backend:RELEASE_TAG|' \
    k8s/app/backend/migration-job.yaml | kubectl apply -f -
kubectl -n c2-app wait --for=condition=complete \
  job/backend-migrate-RELEASE_TAG --timeout=5m
```

Confirm the managed certificate is active before expecting HTTPS traffic:

```bash
kubectl -n c2-app describe managedcertificate c2-app-certificate
kubectl -n c2-app get ingress,pods,hpa,pdb
```

The CPU/memory requests are safe initial values, not final capacity planning.
Tune them from production telemetry after load testing.
