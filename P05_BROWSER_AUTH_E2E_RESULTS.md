# DeepAudit Crosswalk — P0.5 Browser Auth E2E Test Results

**Date:** 2026-11-14  
**Framework:** Playwright 1.60.0 (Chromium headless)  
**Test Spec:** `web/e2e/app.spec.ts`  
**Application URL:** `http://localhost:3000`  
**Backend URL:** `http://127.0.0.1:8000`

---

## 1. Test Overview & Objectives

The End-to-End browser test suite validates the full user journey across both anonymous public demo access and authenticated private document workspace operations.

The tests verify:
1. **Unauthenticated Boundary:** Visiting the private workspace tabs ("1. Assess a Document" or "2. Add Enterprise Policies") presents the sign-in modal and displays badge `"Sign-In Required for Private Workspace"`.
2. **Synthetic Demo Isolation:** Anonymous users can run the public example `DEMO_BANKING_V1` end-to-end without credentials, viewing obligations, approved mappings, and gap findings.
3. **Interactive Workspace Sign-In:** Submitting credentials (`analyst` / `analyst-local-pass`) issues a secure cookie session, renders the user badge (`"Local Governance Analyst (analyst) · Tenant: local-workspace"`), and unlocks document upload forms.
4. **Target Feasibility Warning:** Clicking "AI Governance Strategy (Planned)" prominently displays the planned/unavailable warning stating strategy assessment is not simulated via questionnaire coverage.
5. **Interactive Sign-Out:** Clicking "Sign out" revokes the active session cookie and restores the unauthenticated sign-in prompt.
6. **Mobile Responsive Viewport:** Responsive context form layout fits iPhone-class viewports (390x844) without horizontal overflow.

---

## 2. Test Execution Output

```bash
cd web
pnpm exec playwright test
```

```text
Running 2 tests using 1 worker

[WebServer]  ⚠ Cross origin request detected from 127.0.0.1 to /_next/* resource.
  ok 1 e2e/app.spec.ts:3:5 › document-first authenticated workspace and isolated synthetic demo workflows (14.2s)
  ok 2 e2e/app.spec.ts:80:5 › mobile context form fits the viewport and unknown facts are retained (1.5s)

  2 passed (20.2s)
```

---

## 3. Step-by-Step Test Breakdown

### Scenario 1: `document-first authenticated workspace and isolated synthetic demo workflows`
- **Step 1 — Initial Unauthenticated Landing:**
  - Verified `h1` contains `"your assessment misses"`.
  - Buttons `"1. Assess a Document (Primary)"` and `"2. Add Enterprise Policies (Optional)"` visible.
  - Sign-in prompt `"Sign in to access private tenant documents"` visible.
  - Username and password inputs present and accessible.
  - Snapshot saved: `test-results/home-desktop.png`.
- **Step 2 — Anonymous Synthetic Demo Workflow:**
  - Clicked `"Synthetic Demo Example (DEMO_BANKING_V1)"`.
  - Clicked `"Load example"`, then clicked `"Run assessment"`.
  - Backend responded with 201 Created from `/v1/assessments/coverage`.
  - Verified `"Traceable assessment results"` and `"Export JSON"` rendered.
  - Expanded first obligation detail; verified `"Approved mappings: none"`.
  - Snapshot saved: `test-results/coverage-desktop.png`.
- **Step 3 — Authenticated Workspace Sign-In:**
  - Selected tab `"1. Assess a Document (Primary)"`.
  - Filled username `analyst` and password `analyst-local-pass`.
  - Clicked `"Sign in to Workspace →"`.
  - Verified session badge updated to contain `"analyst"`.
  - Verified `"Sign out"` button became visible.
  - Verified `"Upload Enterprise Questionnaire"` upload zone became visible.
- **Step 4 — Strategy Feasibility Verification:**
  - Clicked `"AI Governance Strategy (Planned)"`.
  - Verified callout text `/Planned \/ Unavailable in PR 2/i` rendered.
  - Returned to `"AI Assurance Questionnaire (.xlsx)"`.
- **Step 5 — Sign-Out Verification:**
  - Clicked `"Sign out"`.
  - Verified sign-in prompt restored.
  - Verified session badge returned to `"Sign-In Required for Private Workspace"`.

### Scenario 2: `mobile context form fits the viewport and unknown facts are retained`
- Set viewport to 390x844 (mobile standard).
- Loaded `/` and clicked synthetic demo.
- Verified select field `"APRA-regulated entity"` has default value `"unknown"`.
- Verified `document.documentElement.scrollWidth <= innerWidth` (zero horizontal overflow).
- Snapshot saved: `test-results/home-mobile.png`.

---

## 4. Visual Evidence Artifacts Generated
- `web/test-results/home-desktop.png`: Unauthenticated landing screen with two-upload navigation.
- `web/test-results/coverage-desktop.png`: Full-page trace of synthetic demo assessment results.
- `web/test-results/home-mobile.png`: Mobile viewport rendering with zero horizontal clipping.
