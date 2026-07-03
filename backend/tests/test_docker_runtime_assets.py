from pathlib import Path


def test_migration_assets_are_included_in_backend_image() -> None:
    ignored_paths = {
        line.strip().rstrip("/")
        for line in Path(".dockerignore").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "alembic.ini" not in ignored_paths
    assert "migrations" not in ignored_paths
