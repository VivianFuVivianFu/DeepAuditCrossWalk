# Contributing

Use Python 3.11+ and Node.js 22 or 24. Install `backend[dev]` and run `npm ci`
inside `web/`. Run backend tests, Ruff, web tests, typecheck and build before
opening a pull request. Describe the concrete problem, changed behaviour,
verification and remaining limitations.

For regulatory data, include the authoritative source URL, clause reference,
version, date, legal status, applicability conditions and a proposed control
interpretation. Clearly label proposed versus expert-reviewed mappings.
Never reproduce licensed ISO text or upload bank-confidential material.

Add meaningful regressions for false coverage, missing applicability facts,
wrong currency thresholds, cross-tenant access or unsafe document parsing.
Use original synthetic fixtures; the source AIAF workbook is intentionally absent.

Contributions are licensed under Apache-2.0. Respectful technical disagreement
is welcome; harassment, personal attacks and disclosure of private information
are not. Maintainers may remove abusive material and restrict participation.
