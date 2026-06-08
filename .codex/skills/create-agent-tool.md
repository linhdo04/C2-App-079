# Create Agent Tool

When creating a new Agent Tool:

1. Check existing tools first.
2. Reuse existing services.
3. Avoid direct database access if service layer exists.
4. Return structured output.
5. Add tool tests.
6. Register tool in agent graph if required.

Do not:

- Put business logic in prompts.
- Put SQL directly inside prompts.
- Duplicate existing tools.
