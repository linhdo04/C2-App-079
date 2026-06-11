# Autonomous Drones Frontend

Next.js 16 frontend for authentication and the agricultural AI Agent workspace.

## Development

```bash
bun install
bun run dev
```

Open [http://localhost:3000](http://localhost:3000).

## UI Library

Reusable UI primitives live in `components/ui`. They follow the shadcn/ui source-owned component model and use Radix
UI where an accessible primitive is required. Theme tokens are defined as CSS variables in `app/globals.css`.

Available components:

- `Button`: `default`, `secondary`, `outline`, `ghost`, `destructive`, and `link` variants; supports `asChild`.
- `Card`: header, title, description, content, and footer composition.
- `Alert`: `default`, `success`, and `destructive` variants.
- `Input` and `Textarea`: native form props with focus, invalid, and disabled states.
- `Field`: label, description, and validation error composition.
- `Spinner`: accessible loading indicator.

Example:

```tsx
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

<Field>
  <FieldLabel htmlFor="email">Email</FieldLabel>
  <Input
    id="email"
    type="email"
  />
  <Button type="submit">Submit</Button>
</Field>;
```

Add another shadcn component from the `frontend` directory:

```bash
bunx shadcn@latest add <component>
```

Review generated styles against the existing agricultural theme before using the component.

## Verification

```bash
bun run lint:check
bun run format:fix
bun run format:check
bun run build
```
