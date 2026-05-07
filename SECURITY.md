# Security Policy

The Arbiter can work with provider credentials, optional API surfaces, and persistence layers. Treat local environments and deployment configuration with the same care you would for any application that handles API secrets and generated outputs.

## Supported Security Posture

The project is designed to support:

- local development without mandatory API auth
- production-safe API behavior when `ARBITER_ENV=production`
- graceful disabling of optional services when dependencies are missing
- offline tests that do not require real provider calls or live credentials

## Reporting a Security Issue

If you discover a security issue, please avoid opening a public issue with exploit details.

Use one of these paths instead:

- open a private GitHub security advisory if available for the repository
- contact the maintainer directly through the GitHub profile linked in `README.md`

When reporting, include:

- affected component or route
- impact and realistic exploitation scenario
- reproduction steps
- whether the issue requires optional features such as API mode, SQL persistence, or Chroma

## Secret Handling

Do not commit:

- `.env` files
- provider API keys
- private benchmark data
- database dumps or local memory archives

Use environment variables for:

- `OPENAI_API_KEY`
- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`
- `API_KEY`

## Deployment Guidance

For any internet-facing deployment:

- set `ARBITER_ENV=production`
- set a real `API_KEY`
- restrict CORS origins intentionally
- keep provider credentials out of client-side code
- treat benchmark and memory data as potentially sensitive operational data

## Known Security Boundaries

The Arbiter is conservative, but it is not a sandboxed execution platform.

In particular:

- verifier execution paths are intentionally limited and conservative
- optional code verification does not claim to safely execute arbitrary untrusted programs
- SQL validation is only meant for simple, self-contained checks
- production hardening beyond the current API/auth model is still evolving

If you change anything touching auth, persistence, or execution behavior, add tests and document the boundary clearly.
