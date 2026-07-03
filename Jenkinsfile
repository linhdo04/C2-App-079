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
        }
      }
    }

    stage('CI') {
      parallel {
        stage('Backend') {
          steps {
            container('backend-ci') {
              dir('backend') {
                sh 'make check'
              }
            }
          }
        }
        stage('Frontend') {
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
        anyOf {
          branch 'main'
          expression { env.GIT_BRANCH == 'origin/main' }
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
              --substitutions="_REGION=$REGION,_REPOSITORY=$REPOSITORY,_IMAGE_TAG=$IMAGE_TAG,_NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL" \
              --suppress-logs
          '''
        }
      }
    }

    stage('Migrate and Deploy') {
      when {
        anyOf {
          branch 'main'
          expression { env.GIT_BRANCH == 'origin/main' }
        }
      }
      steps {
        container('kubectl') {
          sh '''
            BACKEND_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/backend:$IMAGE_TAG"
            FRONTEND_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/frontend:$IMAGE_TAG"
            MIGRATION_JOB="backend-migrate-$IMAGE_TAG"

            sed \
              -e "s|name: backend-migrate|name: $MIGRATION_JOB|" \
              -e "s|image: BACKEND_IMAGE|image: $BACKEND_IMAGE|" \
              k8s/app/backend/migration-job.yaml > migration-job.yaml

            kubectl apply -f migration-job.yaml
            kubectl -n c2-app wait --for=condition=complete "job/$MIGRATION_JOB" --timeout=10m

            kubectl -n c2-app set image deployment/backend "backend=$BACKEND_IMAGE"
            kubectl -n c2-app set image deployment/frontend "frontend=$FRONTEND_IMAGE"
            kubectl -n c2-app rollout status deployment/backend --timeout=10m
            kubectl -n c2-app rollout status deployment/frontend --timeout=10m
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
