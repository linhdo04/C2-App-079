#!/usr/bin/env bash

set -Eeuo pipefail

namespace="${NAMESPACE:-c2-app}"
deployment="${DEPLOYMENT:-backend}"
skip_confirmation=false

usage() {
  cat <<'EOF'
Usage: scripts/reset_and_seed_demo.sh [options]

Delete all PostgreSQL data in the public schema, preserve Alembic's migration
version, then run the backend demo seed.

Options:
  -n, --namespace NAME    Kubernetes namespace (default: c2-app)
  -d, --deployment NAME   Backend deployment (default: backend)
  -y, --yes               Skip the destructive-operation confirmation
  -h, --help              Show this help

Environment alternatives:
  NAMESPACE=c2-app DEPLOYMENT=backend scripts/reset_and_seed_demo.sh
EOF
}

while (($# > 0)); do
  case "$1" in
    -n | --namespace)
      namespace="${2:?Missing value for $1}"
      shift 2
      ;;
    -d | --deployment)
      deployment="${2:?Missing value for $1}"
      shift 2
      ;;
    -y | --yes)
      skip_confirmation=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

command -v kubectl >/dev/null 2>&1 || {
  echo "kubectl is required but was not found." >&2
  exit 1
}

context="$(kubectl config current-context)"
kubectl -n "$namespace" get deployment "$deployment" >/dev/null

# Refuse to erase data if the running image still contains the old one-user seed.
if ! kubectl -n "$namespace" exec "deployment/$deployment" -- python -c \
  'from scripts.seed_demo import DEMO_USERS; assert len(DEMO_USERS) == 2'; then
  echo "The running backend does not contain the two-user seed. Deploy it first." >&2
  exit 1
fi

echo "Kubernetes context : $context"
echo "Namespace          : $namespace"
echo "Deployment         : $deployment"
echo "WARNING: every row in every public PostgreSQL table will be deleted."
echo "The database schema and alembic_version will be preserved."

if [[ "$skip_confirmation" != true ]]; then
  expected="DELETE $namespace"
  read -r -p "Type '$expected' to continue: " confirmation
  if [[ "$confirmation" != "$expected" ]]; then
    echo "Cancelled."
    exit 1
  fi
fi

echo "Deleting application data..."
kubectl -n "$namespace" exec -i "deployment/$deployment" -- python - <<'PY'
import asyncio

from sqlalchemy import text

from infrastructure.database.postgres import close_db, db_session, init_db


async def main() -> None:
    await init_db()
    try:
        async with db_session() as session:
            await session.execute(
                text(
                    """
                    DO $$
                    DECLARE
                        table_names text;
                    BEGIN
                        SELECT string_agg(
                            format('%I.%I', schemaname, tablename),
                            ', '
                        )
                        INTO table_names
                        FROM pg_tables
                        WHERE schemaname = 'public'
                          AND tablename <> 'alembic_version';

                        IF table_names IS NOT NULL THEN
                            EXECUTE 'TRUNCATE TABLE '
                                || table_names
                                || ' RESTART IDENTITY CASCADE';
                        END IF;
                    END
                    $$;
                    """
                )
            )
    finally:
        await close_db()


asyncio.run(main())
PY

echo "Running demo seed..."
kubectl -n "$namespace" exec "deployment/$deployment" -- \
  python -m scripts.seed_demo

echo "Database reset and demo seed completed."
