Title: Use FastAPI for the HTTP API
Date: 2026-06-07
Status: Accepted

Context

The backend needs a web framework that supports async I/O, type hints, and good developer ergonomics for building JSON APIs.

Decision

Use FastAPI as the primary web framework.

Consequences

- Pros: native async support, Pydantic typing and validation, automatic OpenAPI docs, good performance with Uvicorn/ASGI.
- Cons: learning curve for ASGI and middlewares but outweighed by benefits.

Alternatives considered

- Flask (sync): simpler but lacks first-class async and Pydantic integration.
- Django: heavy-weight for this service scope.
