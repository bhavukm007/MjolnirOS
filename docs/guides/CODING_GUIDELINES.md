# MjolnirOS Coding Guidelines

Version: 1.1.0

These guidelines define the coding standards for the MjolnirOS project.

All code generated for this repository must follow these rules.

---

## Engineering Philosophy

Build software like a production engineering team.

Priorities:

1. Reliability
2. Readability
3. Maintainability
4. Performance
5. Security
6. Scalability

Never sacrifice maintainability for speed.

---

## General Rules

- Follow Clean Architecture.
- Follow SOLID Principles.
- Prefer composition over inheritance.
- Keep modules independent.
- Avoid duplicated code.
- Avoid unnecessary complexity.
- Keep functions small and focused.
- Every class should have a single responsibility.

---

## Project Structure

Every feature belongs inside its own module.

Example:

```text
backend/app/<capability>/
frontend/src/
plugins/<plugin-name>/
tests/
```

Never place unrelated files together.

---

## Naming Convention

Folders

snake_case

Example

memory_agent

Files

snake_case.py

Classes

PascalCase

Example

MemoryManager

Functions

snake_case

Variables

snake_case

Constants

UPPER_CASE

---

## Python Standards

- Python 3.12+
- Full type hints
- Dataclasses where appropriate
- Async programming where beneficial
- Use pathlib instead of string paths
- Prefer context managers

---

## API Standards

FastAPI Backend

REST endpoints

Consistent JSON responses

Example

{
    "success": true,
    "message": "...",
    "data": {}
}

Return proper HTTP status codes.

---

## Logging

Every module must use structured logging.

Log levels:

INFO

WARNING

ERROR

CRITICAL

Never use print() for debugging.

Store logs inside

logs/

---

## Configuration

Never hardcode:

Passwords

API Keys

Tokens

Paths

Ports

Store configurable values inside

config/

Use .env where required.

---

## Error Handling

Never silently ignore exceptions.

Catch only expected exceptions.

Provide meaningful error messages.

Log every unexpected error.

---

## Testing

Every new feature requires tests.

Testing includes:

- Unit Tests
- Integration Tests
- End-to-End Tests (where applicable)

Never merge code that breaks tests.

---

## Documentation

Every public class must include a docstring.

Every module should have documentation.

Update documentation whenever architecture changes.

---

## Git Workflow

Use Conventional Commits.

Examples:

feat(memory): add semantic search

fix(browser): resolve login issue

docs: update architecture

refactor(github): improve repository service

test(vision): add OCR tests

---

## Branch Strategy

main

Stable releases only.

feature/<feature-name>

New features.

fix/<bug-name>

Bug fixes.

---

## Pull Requests

Every PR should include:

- Summary
- Files changed
- Testing performed
- Breaking changes (if any)

---

## Security

Never expose:

Passwords

Secrets

API Keys

Tokens

Never commit .env files.

Always validate user input.

Always request confirmation before dangerous operations.

---

## Plugin System Development

Every plugin must contain:

manifest.json

plugin.py

README.md

permissions.json

Plugins must remain isolated from the core system.

---

## Performance

Keep startup fast.

Avoid unnecessary background tasks.

Use lazy loading where appropriate.

Minimize CPU and RAM usage.

---

## UI Guidelines

Theme:

Dark

Design:

Modern

Minimal

Glassmorphism

Responsive

Accessible

---

## AI Guidelines

Default Model:

Ollama

qwen2.5:3b

Support switching models.

Never require paid APIs for core functionality.

---

## Documentation Files

Always keep updated:

README.md

[CHANGELOG.md](../../CHANGELOG.md)

[ROADMAP.md](../releases/ROADMAP.md)

[MASTER_SPEC.md](../reference/MASTER_SPEC.md)

[ARCHITECTURE.md](../reference/ARCHITECTURE.md)

---

## Completion Checklist

Before completing any phase:

✓ Code compiles

✓ Tests pass

✓ Documentation updated

✓ CHANGELOG updated

✓ Git commit created

✓ GitHub push completed

✓ No placeholder code

✓ No TODO comments

✓ No unused imports

✓ No debug prints

---

These coding guidelines are mandatory for all future development of MjolnirOS.
