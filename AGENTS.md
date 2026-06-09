# AGENTS.md

# Codex CLI Instructions

## Project Overview

This repository contains:

- `backend/`: FastAPI backend
- `frontend/`: Next.js frontend
- `backend/docs/agent/`: documentation for the application's AI Agent, not Codex instructions

---

## Project Command Rules

Prefer project-defined commands over raw tool commands.

Use Makefile scripts for backend tasks.

Examples:

- Use `make format`, not raw `ruff format .`
- Use `make lint`, not raw `ruff check . --fix`
- Use `make lint-check`, not raw `ruff check .`
- Use `make typecheck`, not raw `mypy .`
- Use `make test`, not raw `pytest`
- Use `make check`, not separate manual checks when full verification is needed
- Use `make db-migrate m="name"`, not manually creating migration files
- Use `make db-upgrade`, not raw migration edits

Raw tool commands are allowed only when:

- no Makefile command exists
- debugging a tool-specific issue
- explicitly requested

## General Rules

- Follow the existing project architecture.
- Read relevant code before making changes.
- Make the smallest change necessary.
- Prefer modifying existing code over creating new abstractions.
- Reuse existing patterns whenever possible.
- Explain what changed before finishing a task.
- Do not commit unless explicitly asked.
- Do not modify unrelated files.
- Do not perform large-scale refactors unless explicitly requested.

---

## Scope Control

- Focus only on the requested task.
- Do not rename files, folders, classes, functions, or APIs unless required.
- Do not introduce new patterns when existing patterns already solve the problem.
- Avoid touching unrelated modules.

---

## Bug Fix Workflow

Before fixing a bug:

1. Identify the root cause.
2. Explain the root cause.
3. Describe the proposed fix.
4. Implement the fix.
5. Add or update tests.

Do not make speculative fixes.

---

## Architecture Rules

- Follow existing architectural decisions.
- Review relevant ADRs before making architectural changes.

ADR location:

```text
backend/docs/adr/
```

Current ADRs include:

- FastAPI
- SQLModel + PostgreSQL
- Redis rate limiting
- LangChain/Gemini integration

Do not replace established architectural patterns unless explicitly instructed.

---

## Backend Rules

### Code Location

Backend application code belongs in:

```text
backend/src/
```

Tests belong in:

```text
backend/tests/
```

### Development Rules

- Keep business logic testable.
- Prefer dependency injection patterns already used by the project.
- Keep functions focused and small.
- Maintain type safety.
- Preserve existing API contracts unless instructed otherwise.

### Unit Testing

Always write or update tests when:

- adding backend features
- changing backend behavior
- fixing backend bugs

Requirements:

- Add success-path tests.
- Add failure-path tests.
- Add regression tests for bug fixes when practical.

Never remove tests to make CI pass.

---

## Database Rules

- Do not modify schema unless required.
- Do not edit historical migrations.
- Create a new migration when schema changes are necessary.
- Keep models, migrations, and tests synchronized.
- Never hand-write a migration file unless explicitly instructed.
- Never bypass the Makefile command when a Makefile command exists.

If schema changes are introduced:

1. Update models.
2. Create migration.
3. Update tests.
4. Verify migration execution.

---

## API Rules

- Preserve backward compatibility whenever possible.
- Do not change request/response schemas without explicit approval.
- Update API documentation when API behavior changes.
- Keep validation consistent.

---

## AI Agent Rules

The application contains an AI Agent implementation.

Relevant directory:

```text
backend/src/agent/
```

Relevant documentation:

```text
backend/docs/agent/
```

When modifying agent code:

- Read backend/docs/agent/README.md first.
- Preserve existing workflows.
- Preserve graph behavior unless explicitly requested.
- Preserve state compatibility.
- Explain impacts before changing:
  - prompts
  - graph structure
  - tools
  - memory/state handling

Do not redesign the agent architecture unless explicitly requested.

---

## Next.js 16 App Router Rules

### Server Components by default

- Components are Server Components by default.
- Do not add `"use client"` unless required.
- Use Client Components only for:
  - local state
  - event handlers
  - browser APIs
  - effects
  - interactive UI

### Route file responsibilities

Route files should stay thin.

Allowed in `page.tsx`:

- route-level composition
- async data fetching
- metadata
- passing props to components

Avoid in `page.tsx`:

- large JSX sections
- complex forms
- charts
- tables
- reusable cards
- client-side state
- event handlers

If `page.tsx` exceeds ~150 lines, extract components.

### Recommended structure

```text
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── loading.tsx
│   ├── error.tsx
│   └── ...
├── components/
│   ├── ui/
│   ├── layout/
│   └── features/
│       ├── missions/
│       ├── telemetry/
│       ├── coverage/
│       └── agent/
├── hooks/
├── lib/
└── types/
```

### Development Rules

- Keep frontend code type-safe.
- Prefer reusable components.
- Avoid unnecessary dependencies.
- Prefer server components where appropriate.
- Keep components focused and maintainable.

---

## Mobile-First Design

Always design mobile-first.

Requirements:

- Start with mobile layouts first.
- Enhance progressively for tablet and desktop.
- Use responsive breakpoints only for larger screens.
- Avoid desktop-first implementations.
- Avoid horizontal scrolling.
- Support screens as small as 320px wide.
- Ensure touch targets are at least 44x44px.
- Prefer vertical stacking before multi-column layouts.

For every new UI:

1. Design mobile layout first.
2. Then tablet.
3. Then desktop.

---

## Accessibility

Ensure accessibility basics are respected.

Requirements:

- Use semantic HTML.
- Inputs must have labels.
- Images must have alt text.
- Buttons must have accessible text.
- Support keyboard navigation.
- Avoid color-only communication.

---

## Responsive UI Checklist

Before completing frontend work, verify:

- Mobile (320px–640px)
- Tablet (~768px)
- Desktop (1024px+)

Check:

- Navigation
- Forms
- Dialogs
- Tables
- Cards
- Text wrapping
- Overflow behavior

---

## Dependencies

- Prefer existing dependencies.
- Avoid adding new dependencies unless necessary.
- Explain why a new dependency is needed.
- Prefer built-in framework capabilities first.

---

## Documentation

Update documentation when behavior changes.

Examples:

- README
- API docs
- Architecture docs
- ADRs

If setup, configuration, architecture, or workflows change, documentation must be updated.

---

## Required Checks Before Commit

### Backend

Before committing backend changes:

```bash
cd backend
make format
make lint
make check
```

Before committing frontend changes:

```bash
cd backend
bun format:fix && bun format:check
bun lint:check
```

All commands must pass.

---

### Frontend

Before committing frontend changes:

```bash
cd frontend
bun run lint:check
bun run format:fix
bun run format:check
```

All commands must pass.

---

### Full Stack Changes

If both backend and frontend changed:

Run all backend checks and all frontend checks.

---

## Failure Handling

If any verification step fails:

1. Stop.
2. Explain the failure.
3. Fix the issue when it is related to the task.
4. Re-run verification.
5. Report results.

Do not ignore failing checks.

---

## Completion Checklist

Before considering a task complete:

- Requested functionality implemented.
- No unrelated changes made.
- Relevant tests added or updated.
- Documentation updated if needed.
- Verification commands executed.
- Results reported to the user.
