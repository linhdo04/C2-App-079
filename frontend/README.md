# Autonomous Drones Frontend

Next.js 16 frontend for authentication and the agricultural AI Agent workspace.

## Development

```bash
pnpm install
pnpm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## UI Library

Reusable UI primitives live in `components/ui`. They follow the shadcn/ui source-owned component model and use Radix
UI where an accessible primitive is required. Theme tokens are defined as CSS variables in `app/globals.css`.

Add another shadcn component from the `frontend` directory:

```bash
npmx shadcn@latest add <component>
```

Review generated styles against the existing agricultural theme before using the component.

## Verification

```bash
pnpm run lint:check
pnpm run format:fix
pnpm run format:check
pnpm run build
```
