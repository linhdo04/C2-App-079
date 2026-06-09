from pathlib import Path


def test_password_hash_migration_marks_legacy_users() -> None:
    migration = Path(
        "migrations/versions/31c9ab7d2c7f_add_user_password_hash.py"
    ).read_text()

    assert "op.add_column" in migration
    assert "password_hash" in migration
    assert "!legacy-user-no-password!" in migration
    assert "op.drop_column" in migration
