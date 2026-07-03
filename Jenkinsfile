pipeline {
  agent {
    kubernetes {
      defaultContainer 'jnlp'
      yaml '''
apiVersion: v1
kind: Pod
spec:
  serviceAccountName: jenkins-agent
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: backend-ci
      image: ghcr.io/astral-sh/uv:python3.12-bookworm
      command: ["sleep"]
      args: ["99d"]
      env:
        - name: HOME
          value: /tmp
        - name: UV_CACHE_DIR
          value: /tmp/uv-cache
        - name: UV_LINK_MODE
          value: copy
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
    - name: frontend-ci
      image: node:22-alpine
      command: ["sleep"]
      args: ["99d"]
      env:
        - name: HOME
          value: /tmp
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
    - name: gcloud
      image: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
      command: ["sleep"]
      args: ["99d"]
      env:
        - name: HOME
          value: /tmp
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
    - name: kubectl
      image: alpine/k8s:1.33.4
      command: ["sleep"]
      args: ["99d"]
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
'''
    }
  }

  options {
    skipDefaultCheckout true
    disableConcurrentBuilds()
    timestamps()
    timeout(time: 45, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  parameters {
    booleanParam(
      name: 'FORCE_FULL_PIPELINE',
      defaultValue: false,
      description: 'Run all CI/CD stages even when backend/frontend files are unchanged. Production deploy remains restricted to main.',
    )
  }

  environment {
    PROJECT_ID = 'c2-app-501203'
    REGION = 'asia-southeast1'
    REPOSITORY = 'c2-app'
    SOURCE_BUCKET = 'c2-app-501203-jenkins-build-source'
    BUILD_SERVICE_ACCOUNT = 'jenkins-agent@c2-app-501203.iam.gserviceaccount.com'
    NEXT_PUBLIC_API_URL = 'https://api.docker-linhdt.site/api'
    // Safe placeholders required only while loading backend settings in CI.
    TAVILY_API_KEY = 'ci-placeholder'
    JWT_SECRET_KEY = 'ci-only-key-with-at-least-32-characters'
    LANGSMITH_TRACING = 'false'
    APP_ENV = 'testing'
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
        script {
          env.SHORT_SHA = sh(script: 'git rev-parse --short=12 HEAD', returnStdout: true).trim()
          env.IMAGE_TAG = "${env.BUILD_NUMBER}-${env.SHORT_SHA}"
          sh '''
            BASE_COMMIT="${GIT_PREVIOUS_SUCCESSFUL_COMMIT:-${GIT_PREVIOUS_COMMIT:-HEAD^}}"
            git diff --name-only "$BASE_COMMIT" HEAD > .jenkins-changed-files
            echo "Changed files since $BASE_COMMIT:"
            cat .jenkins-changed-files
          '''
          env.MIGRATIONS_CHANGED = sh(
            script: "grep -q '^backend/migrations/' .jenkins-changed-files",
            returnStatus: true,
          ) == 0 ? 'true' : 'false'
          env.PROMPTS_CHANGED = sh(
            script: "grep -Eq '^backend/(src/agent/prompt_defaults\\.py|src/scripts/sync_prompts\\.py)' .jenkins-changed-files",
            returnStatus: true,
          ) == 0 ? 'true' : 'false'
          env.BACKEND_CHANGED = sh(
            script: "grep -q '^backend/' .jenkins-changed-files",
            returnStatus: true,
          ) == 0 ? 'true' : 'false'
          env.FRONTEND_CHANGED = sh(
            script: "grep -q '^frontend/' .jenkins-changed-files",
            returnStatus: true,
          ) == 0 ? 'true' : 'false'
          if (params.FORCE_FULL_PIPELINE) {
            env.BACKEND_CHANGED = 'true'
            env.FRONTEND_CHANGED = 'true'
            env.MIGRATIONS_CHANGED = 'true'
            env.PROMPTS_CHANGED = 'true'
            echo 'FORCE_FULL_PIPELINE enabled: all conditional stages will run.'
          }
          echo "Backend changed: ${env.BACKEND_CHANGED}"
          echo "Frontend changed: ${env.FRONTEND_CHANGED}"
          echo "Migrations changed: ${env.MIGRATIONS_CHANGED}"
          echo "Prompts changed: ${env.PROMPTS_CHANGED}"
        }
      }
    }

    stage('CI') {
      parallel {
        stage('Backend') {
          when {
            expression { env.BACKEND_CHANGED == 'true' }
          }
          steps {
            container('backend-ci') {
              dir('backend') {
                sh '''
                  uv sync --frozen --extra dev
                  make check
                '''
              }
            }
          }
        }
        stage('Frontend') {
          when {
            expression { env.FRONTEND_CHANGED == 'true' }
          }
          steps {
            container('frontend-ci') {
              dir('frontend') {
                sh '''
                  corepack pnpm install --frozen-lockfile
                  corepack pnpm run lint:check
                  corepack pnpm run format:check
                  NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" corepack pnpm run build
                '''
              }
            }
          }
        }
      }
    }

    stage('Build and Push') {
      when {
        allOf {
          anyOf {
            branch 'main'
            expression { env.GIT_BRANCH == 'origin/main' }
          }
          expression {
            env.BACKEND_CHANGED == 'true' || env.FRONTEND_CHANGED == 'true'
          }
        }
      }
      steps {
        container('gcloud') {
          sh '''
            gcloud builds submit . \
              --project="$PROJECT_ID" \
              --config=cloudbuild.yaml \
              --service-account="projects/$PROJECT_ID/serviceAccounts/$BUILD_SERVICE_ACCOUNT" \
              --gcs-source-staging-dir="gs://$SOURCE_BUCKET/source" \
              --substitutions="_REGION=$REGION,_REPOSITORY=$REPOSITORY,_IMAGE_TAG=$IMAGE_TAG,_NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL,_BUILD_BACKEND=$BACKEND_CHANGED,_BUILD_FRONTEND=$FRONTEND_CHANGED" \
              --suppress-logs
          '''
        }
      }
    }

    stage('Database Migration') {
      when {
        allOf {
          anyOf {
            branch 'main'
            expression { env.GIT_BRANCH == 'origin/main' }
          }
          expression { env.MIGRATIONS_CHANGED == 'true' }
        }
      }
      steps {
        container('kubectl') {
          sh '''
            BACKEND_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/backend:$IMAGE_TAG"
            MIGRATION_JOB="backend-migrate-$IMAGE_TAG"

            sed \
              -e "s|name: backend-migrate|name: $MIGRATION_JOB|" \
              -e "s|image: BACKEND_IMAGE|image: $BACKEND_IMAGE|" \
              k8s/app/backend/migration-job.yaml > migration-job.yaml

            RENDERED_IMAGE="$(sed -n 's/^[[:space:]]*image:[[:space:]]*//p' migration-job.yaml | head -1)"
            if [ "$RENDERED_IMAGE" != "$BACKEND_IMAGE" ]; then
              echo "Migration image mismatch: expected $BACKEND_IMAGE, rendered $RENDERED_IMAGE" >&2
              exit 1
            fi

            kubectl apply -f migration-job.yaml

            for _ in $(seq 1 120); do
              SUCCEEDED="$(kubectl -n c2-app get "job/$MIGRATION_JOB" -o jsonpath='{.status.succeeded}')"
              FAILED="$(kubectl -n c2-app get "job/$MIGRATION_JOB" -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}')"
              if [ "$SUCCEEDED" = "1" ]; then
                echo "Migration completed successfully."
                break
              fi
              if [ "$FAILED" = "True" ]; then
                kubectl -n c2-app logs "job/$MIGRATION_JOB" --all-containers=true --tail=300 || true
                exit 1
              fi
              sleep 5
            done

            if [ "${SUCCEEDED:-0}" != "1" ]; then
              kubectl -n c2-app describe "job/$MIGRATION_JOB" || true
              kubectl -n c2-app logs "job/$MIGRATION_JOB" --all-containers=true --tail=300 || true
              echo "Migration timed out after 10 minutes." >&2
              exit 1
            fi
          '''
        }
      }
    }

    stage('Sync Prompts') {
      when {
        allOf {
          anyOf {
            branch 'main'
            expression { env.GIT_BRANCH == 'origin/main' }
          }
          expression { env.PROMPTS_CHANGED == 'true' }
        }
      }
      steps {
        container('backend-ci') {
          dir('backend') {
            withCredentials([string(credentialsId: 'langsmith-api-key', variable: 'LANGSMITH_API_KEY')]) {
              withEnv([
                'APP_ENV=production',
                'LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com',
                'LANGSMITH_PROJECT=c2_app_production',
                'LANGSMITH_TRACING=false',
              ]) {
                sh 'make agent-prompts-sync'
              }
            }
          }
        }
      }
    }

    stage('Deploy') {
      when {
        allOf {
          anyOf {
            branch 'main'
            expression { env.GIT_BRANCH == 'origin/main' }
          }
          expression {
            env.BACKEND_CHANGED == 'true' || env.FRONTEND_CHANGED == 'true'
          }
        }
      }
      steps {
        container('kubectl') {
          sh '''
            BACKEND_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/backend:$IMAGE_TAG"
            FRONTEND_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/frontend:$IMAGE_TAG"

            if [ "$BACKEND_CHANGED" = "true" ]; then
              kubectl -n c2-app set image deployment/backend "backend=$BACKEND_IMAGE"
              kubectl -n c2-app rollout status deployment/backend --timeout=10m
            fi

            if [ "$FRONTEND_CHANGED" = "true" ]; then
              kubectl -n c2-app set image deployment/frontend "frontend=$FRONTEND_IMAGE"
              kubectl -n c2-app rollout status deployment/frontend --timeout=10m
            fi
          '''
        }
      }
    }
  }

  post {
    always {
      echo "Image tag: ${env.IMAGE_TAG ?: 'not-built'}"
    }
  }
}
