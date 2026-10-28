# Verification record — 28 October 2026

This record describes the standalone repository, not tests from the original
DeepAudit application. No source workbook or private bank policy is a test dependency.

Local checks run in a new isolated Python 3.13 environment and Node.js 22.20:

Latest local results: **38 backend tests passed, 1 optional workbook test skipped;
8 frontend tests passed; 2 browser tests passed; both live smoke workflows passed.**
Type checking, production build and dependency/security scans also passed.

- Backend regression suite, including isolated tenant state, four-state
  applicability, approved mapping gates, gap closure, exact currency boundaries,
  XLSX archive/XML safeguards, PDF/DOCX parsing and the standalone app.
- Frontend contract/gateway tests, TypeScript checking and Next.js production build.
- Two Playwright browser checks using a real local web server and separate
  FastAPI process: coverage/policy analysis with JSON download, and a mobile
  layout retaining undetermined facts.
- Two live smoke requests traversing the web proxy to the API, verifying
  assessment IDs, source hashes, undetermined facts and absence of automatic approval.
- Python dependency audit, npm audit and publishable-tree secret scan.
- Python source distribution/wheel build, with embedded JSON asset checks.
- Docker Compose configuration validation.

The optional real AIAF workbook acceptance test skips when the operator's own
authorised workbook is absent. This is expected in a public clone; synthetic
XLSX import tests still run.

The local Docker daemon was unavailable. Linux image builds, non-root health
checks and live container/browser smoke tests are therefore configured as a
separate CI job; local Compose syntax validation is not recorded as an image
build or deployment success.

CI additionally checks Python 3.11/3.13 and Node.js 24. This repository has no
automatic cloud deployment. The project remains an experimental MVP while
durable storage, identity integration and expert mapping validation are pending.
