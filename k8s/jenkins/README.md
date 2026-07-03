# Jenkins on GKE

The Jenkins controller is installed from the official chart, pinned to chart
version `5.9.32`. Builds run on ephemeral Kubernetes agents; the controller has
zero executors and must not build workloads itself.

## 1. Provision GCP dependencies

Apply and review the `infra/gke-data` plan. It creates:

- the `jenkins-ingress-ip` global address;
- `jenkins-agent@PROJECT_ID.iam.gserviceaccount.com`;
- repository-scoped Artifact Registry writer access;
- a Workload Identity binding for `jenkins/jenkins-agent`.

Set the DNS A record for `jenkins.docker-linhdt.site` to:

```bash
cd infra/gke-data
terraform output -raw jenkins_ingress_ip
```

## 2. Bootstrap Kubernetes resources

Create the namespace first, then an admin Secret. Keep the password outside Git:

```bash
kubectl apply -f k8s/jenkins/namespace.yaml
JENKINS_ADMIN_PASSWORD="$(openssl rand -base64 32)"
printf '%s\n' "$JENKINS_ADMIN_PASSWORD"
kubectl -n jenkins create secret generic jenkins-admin \
  --from-literal=jenkins-admin-user=admin \
  --from-literal=jenkins-admin-password="$JENKINS_ADMIN_PASSWORD"
```

Store the generated password in a password manager. To supply a chosen password,
replace the command substitution with the value from your secret manager.

Install the GKE-specific certificate and health check, plus the namespace-scoped
deployment permission for agents:

```bash
kubectl apply -f k8s/jenkins/storage-class.yaml
kubectl apply -f k8s/jenkins/gke-resources.yaml
kubectl apply -f k8s/jenkins/deploy-rbac.yaml
```

## 3. Install Jenkins with Helm

```bash
helm repo add jenkins https://charts.jenkins.io
helm repo update jenkins
helm upgrade --install jenkins jenkins/jenkins \
  --namespace jenkins \
  --version 5.9.32 \
  --values k8s/jenkins/values.yaml \
  --rollback-on-failure \
  --timeout 15m
```

Check readiness and the managed certificate:

```bash
kubectl -n jenkins rollout status statefulset/jenkins --timeout=10m
kubectl -n jenkins get pods,pvc,ingress
kubectl -n jenkins describe managedcertificate jenkins-certificate
```

The certificate becomes active only after DNS points to the reserved address.
Until then, access Jenkins locally with:

```bash
kubectl -n jenkins port-forward service/jenkins 8080:8080
```

## Security and operations

- Do not mount `/var/run/docker.sock` into Jenkins.
- Build images only in ephemeral agents using a rootless builder or a reviewed
  dedicated build image.
- Put Git credentials, webhook secrets, and application secrets in Jenkins
  credentials or an external secret manager, never in `values.yaml`.
- Back up the Jenkins PVC or export Jenkins Configuration as Code before chart
  upgrades.
- Review chart and plugin updates explicitly; versions are intentionally pinned.

The chart creates the PVC. `storage-class.yaml` dynamically provisions a
regional balanced Persistent Disk and retains it if the PVC is deleted. Do not
create a static PV/PVC for the same Jenkins home.

## Configure the C2 App pipeline

Apply the latest `infra/gke-data` Terraform plan, then commit and push
`Jenkinsfile` and `cloudbuild.yaml`. Terraform enables Cloud Build, creates a
short-lived source bucket, and grants the Jenkins Workload Identity only the
build, source-upload, and Artifact Registry permissions it needs.

In Jenkins, create a **Multibranch Pipeline** named `c2-app`:

1. Add a Git branch source using
   `https://github.com/AI20K-Build-Cohort-2/C2-App-079.git`.
2. Leave credentials empty while the repository is public.
3. Set the script path to `Jenkinsfile`.
4. Save, then run **Scan Multibranch Pipeline Now**.

Pull requests and non-main branches run backend/frontend checks only. `main`
also asks Google Cloud Build to produce native amd64 images, runs the Alembic
migration Job, and rolls out both Deployments. Images use immutable tags in the
form `<jenkins-build-number>-<git-sha>`.

The pipeline deploys images only. Namespace, Secret, Ingress, and other
platform resources remain managed separately so an application build cannot
change cluster security or credentials.
