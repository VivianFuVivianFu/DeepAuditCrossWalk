# DeepAudit Crosswalk

[![CI](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/workflows/ci.yml/badge.svg)](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

*Open-source AI governance coverage assessment for Australian financial services.*

## Overview

DeepAudit Crosswalk helps organisations identify potential gaps between applicable regulatory requirements, internal enterprise policies and their existing AI governance documentation. Built with a focus on Australian banking and financial services, the platform takes a document-first approach: it evaluates the assurance questionnaires and policy documents an organisation already uses, rather than requiring teams to complete another governance questionnaire. It supports regulatory requirement mapping, coverage gap detection, source traceability and structured human review.

## What You Can Do

### Assess a Governance Document

Upload an existing AI Governance or Assurance Questionnaire in `.xlsx` format. DeepAudit Crosswalk previews the extracted questions and compares them against applicable requirements to surface potential coverage gaps, incomplete requirements and items requiring human review.

You can run an assessment in two modes:

- **Regulatory-Only (Default):** Evaluates your questionnaire against applicable external regulatory obligations and selected governance standards.
- **Enterprise-Enhanced (Optional):** Evaluates your questionnaire against both external obligations and an explicitly selected, approved internal Enterprise Baseline.

### Add Enterprise Policies (Optional)

Upload internal governance documents—such as AI Governance, Risk Management, Privacy, Cybersecurity, Data Governance or Delegated Authority policies—to build an optional Enterprise Baseline. The platform extracts candidate requirements and proposed control mappings so authorised reviewers can approve or reject them and compile a versioned baseline.

Enterprise Policy uploads are optional, supplement only your workspace's assessments, never alter the shared regulatory library, and require explicit human approval before taking effect.

## How It Works

`Upload documents → Select assessment requirements → Identify coverage gaps → Review findings`

Start by uploading your existing `.xlsx` questionnaire, optionally configure high-level organisational applicability context, and choose either Regulatory-Only or an approved Enterprise Baseline. The platform links every finding back to the relevant regulatory provision, internal policy clause and questionnaire item, and allows you to export a structured JSON report for further review. A separate synthetic demonstration tab is also included for exploring example data without uploading documents.

## Getting Started

The application separates its stateless synthetic demo (`public-demo`) from the private local document workspace. Because `.env.example` and `compose.yaml` default to `public-demo`, private document uploads require a non-demo workspace tenant ID.

### Local Development (Python and Node.js)

Prerequisites: Python 3.11+ and Node.js 22 or 24. When running the development servers without overriding `BANKING_CROSSWALK_TENANT_ID`, the web workspace binds to `local-private-workspace`:

```bash
git clone https://github.com/VivianFuVivianFu/DeepAuditCrossWalk.git
cd DeepAuditCrossWalk
python -m venv .venv
# Activate .venv for your shell
pip install -e './backend[dev]'
uvicorn banking_crosswalk.app:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd web
npm ci
npm run dev
```

Open `http://localhost:3000` for the web workspace and `http://localhost:8000/docs` for the API reference.

### Docker Compose

To use the private two-upload workspace with Docker Compose, configure a non-demo workspace tenant ID and local API key before starting the containers:

```bash
cp .env.example .env
# In .env, set BANKING_CROSSWALK_TENANT_ID=local-private-workspace
# and set CROSSWALK_API_KEY to a non-empty local secret string.
docker compose up --build
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and [docs/PERSISTENCE.md](docs/PERSISTENCE.md) for detailed configuration and optional PostgreSQL persistence.

## Current Status

DeepAudit Crosswalk is an **Experimental MVP**.

- **Available today:** Web-based `.xlsx` Questionnaire import and coverage assessment, optional Enterprise Policy upload and human review, Regulatory-Only and Enterprise-Enhanced assessment modes, traceable gap findings, JSON report export and an isolated synthetic demonstration workflow.
- **Planned and current limitations:** AI Governance Strategy assessment (for `.docx`, `.pdf` and text strategy documents) is planned and currently unavailable. Production semantic model integration, federated multi-tenant authentication and certified compliance automation are not implemented.

Assessment outputs support professional review by governance, risk, compliance and legal teams; they do not establish regulatory compliance or operational control effectiveness.

## Contributing & Collaboration

We welcome contributions and feedback from AI governance and assurance practitioners, risk and compliance professionals, open-source developers and researchers working on regulatory mapping and evaluation accuracy.

To report a bug, suggest an improvement or contribute changes, please see [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and [GitHub Issues](https://github.com/VivianFuVivianFu/DeepAuditCrossWalk/issues).

## License

This repository is licensed under the Apache License 2.0. See [LICENSE](LICENSE), [NOTICE](NOTICE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for license terms and attribution details.
