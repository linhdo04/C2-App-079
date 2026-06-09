Title: Use SQLModel + Postgres (asyncpg)
Date: 2026-06-07
Status: Accepted

Context

We need typed DB models, migrations, and async database access.

Decision

Use `SQLModel` (typed models built on SQLAlchemy) with Postgres and `asyncpg`.

Consequences

- Pros: type-safe models, easy Pydantic interchange, compatibility with Alembic for migrations.
- Cons: some async integration boilerplate; SQLModel is newer than plain SQLAlchemy but simplifies model definitions.

Alternatives considered

- Plain SQLAlchemy: more verbose mapping and manual Pydantic models.
- Tortoise ORM: good async support but less compatibility with Alembic.
