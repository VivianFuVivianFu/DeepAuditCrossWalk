import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { afterEach, describe, expect, it } from "vitest";
import { hashPassword } from "../app/security";

const WORKER_SCRIPT = path.resolve(
  __dirname,
  "helpers",
  "security_process_worker.cjs"
);

type WorkerResponse = {
  id: number;
  ok: boolean;
  pid: number;
  status?: number;
  setCookie?: string | null;
  body?: Record<string, any>;
  revoked?: boolean;
  backendCalled?: boolean;
  backendHeaders?: Record<string, string>;
  error?: string;
};

class SecurityWorkerProcess {
  private proc: ChildProcessWithoutNullStreams;
  private nextId = 1;
  private pending = new Map<
    number,
    { resolve: (res: WorkerResponse) => void; reject: (err: Error) => void }
  >();
  public pid: number = 0;

  constructor(envOverrides: Record<string, string>) {
    this.proc = spawn(process.execPath, [WORKER_SCRIPT], {
      cwd: path.resolve(__dirname, ".."),
      env: {
        ...process.env,
        NODE_NO_WARNINGS: "1",
        ...envOverrides,
      },
      stdio: ["pipe", "pipe", "pipe"],
    });

    const rl = readline.createInterface({
      input: this.proc.stdout,
      terminal: false,
    });

    rl.on("line", (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      try {
        const msg: WorkerResponse = JSON.parse(trimmed);
        const entry = this.pending.get(msg.id);
        if (entry) {
          this.pending.delete(msg.id);
          entry.resolve(msg);
        }
      } catch {
        // Ignore non-JSON stdout lines
      }
    });

    this.proc.on("exit", (code) => {
      for (const [, entry] of this.pending.entries()) {
        entry.reject(new Error(`Worker exited unexpectedly with code ${code}`));
      }
      this.pending.clear();
    });
  }

  async send(
    action: string,
    payload: Record<string, unknown> = {}
  ): Promise<WorkerResponse> {
    const id = this.nextId++;
    return new Promise<WorkerResponse>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Worker request timed out for action '${action}'`));
      }, 15000);

      this.pending.set(id, {
        resolve: (res) => {
          clearTimeout(timer);
          resolve(res);
        },
        reject: (err) => {
          clearTimeout(timer);
          reject(err);
        },
      });

      this.proc.stdin.write(JSON.stringify({ id, action, payload }) + "\n");
    });
  }

  async start(): Promise<void> {
    const pong = await this.send("ping");
    if (!pong.ok) {
      throw new Error(`Worker failed to start: ${pong.error}`);
    }
    this.pid = pong.pid;
  }

  async stop(): Promise<void> {
    if (this.proc.killed || this.proc.exitCode !== null) return;
    return new Promise<void>((resolve) => {
      this.proc.once("exit", () => resolve());
      this.proc.kill();
      setTimeout(() => resolve(), 1000);
    });
  }
}

function extractCookiePair(setCookieHeader: string | null | undefined): string {
  if (!setCookieHeader) {
    throw new Error("Missing Set-Cookie header in login response");
  }
  return setCookieHeader.split(";")[0].trim();
}

describe("P0.6 Real Multi-Process Session Revocation, Membership & Rate-Limit Verification", () => {
  const activeWorkers: SecurityWorkerProcess[] = [];
  const tempFiles: string[] = [];

  function createTempStateFilePath(prefix: string): string {
    const p = path.join(
      os.tmpdir(),
      `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2)}.json`
    );
    tempFiles.push(p);
    tempFiles.push(`${p}.lock`);
    return p;
  }

  async function spawnWorker(
    envOverrides: Record<string, string>
  ): Promise<SecurityWorkerProcess> {
    const w = new SecurityWorkerProcess(envOverrides);
    activeWorkers.push(w);
    await w.start();
    return w;
  }

  afterEach(async () => {
    while (activeWorkers.length > 0) {
      const w = activeWorkers.pop()!;
      await w.stop();
    }
    for (const f of tempFiles.splice(0, tempFiles.length)) {
      try {
        if (fs.existsSync(f)) fs.unlinkSync(f);
      } catch {}
    }
  });

  it("Scenario A: Revocation Visibility Across Running OS Processes & After Process Restarts (plus SHA-256 SID digest storage)", async () => {
    const stateFile = createTempStateFilePath("p06_scenario_a");
    const commonEnv = {
      ENV: "development",
      WORKSPACE_SESSION_SECRET: "p06-multiprocess-session-secret-32chars-min!!",
      SESSION_REVOCATION_PATH: stateFile,
      BANKING_CROSSWALK_TENANT_ID: "local-workspace",
    };

    // 1 & 2. Start independent OS Process A and Process B
    const procA = await spawnWorker(commonEnv);
    const procB = await spawnWorker(commonEnv);
    expect(procA.pid).toBeGreaterThan(0);
    expect(procB.pid).toBeGreaterThan(0);
    expect(procA.pid).not.toBe(procB.pid);
    expect(procA.pid).not.toBe(process.pid);

    // 3. Establish an authenticated session via Process A
    const loginRes = await procA.send("login", {
      body: {
        username: "reviewer",
        password: "reviewer-local-pass",
        tenant_id: "local-workspace",
      },
    });
    expect(loginRes.status).toBe(200);
    const cookieHeader = extractCookiePair(loginRes.setCookie);
    const csrfToken = String(loginRes.body?.csrf_token || "");
    const rawSessionId = String(loginRes.body?.session_id || "");
    expect(csrfToken.length).toBeGreaterThan(10);
    expect(rawSessionId.length).toBeGreaterThan(10);

    // 4. Verify access through BOTH Process A and Process B (warming up both process caches)
    const accessA1 = await procA.send("workspace_post", {
      headers: { Cookie: cookieHeader, "X-CSRF-Token": csrfToken },
      body: { action: "list_questionnaires" },
    });
    expect(accessA1.status).toBe(200);

    const accessB1 = await procB.send("workspace_post", {
      headers: { Cookie: cookieHeader, "X-CSRF-Token": csrfToken },
      body: { action: "list_questionnaires" },
    });
    expect(accessB1.status).toBe(200);

    // 5. Logout through Process A
    const logoutRes = await procA.send("logout", {
      headers: {
        Cookie: cookieHeader,
        "X-CSRF-Token": csrfToken,
        Origin: "http://localhost",
      },
    });
    expect(logoutRes.status).toBe(200);

    // 6 & 7. Attempt to reuse the old session through Process B -> MUST be rejected (401)
    const accessBAfterLogout = await procB.send("workspace_post", {
      headers: { Cookie: cookieHeader, "X-CSRF-Token": csrfToken },
      body: { action: "list_questionnaires" },
    });
    expect(accessBAfterLogout.status).toBe(401);
    expect(accessBAfterLogout.backendCalled).toBe(false);

    const getBAfterLogout = await procB.send("workspace_get", {
      headers: { Cookie: cookieHeader },
    });
    expect(getBAfterLogout.status).toBe(401);

    const sessionBAfterLogout = await procB.send("session", {
      headers: { Cookie: cookieHeader },
    });
    expect(sessionBAfterLogout.status).toBe(200);
    expect(sessionBAfterLogout.body?.authenticated).toBe(false);

    // Verify raw session ID is NOT stored in plaintext on disk (must use cryptographic digest)
    expect(fs.existsSync(stateFile)).toBe(true);
    const rawDiskContent = fs.readFileSync(stateFile, "utf8");
    expect(rawDiskContent).not.toContain(rawSessionId);

    // 8 & 9. Restart both processes and confirm the revoked session remains rejected
    await procA.stop();
    await procB.stop();

    const procA2 = await spawnWorker(commonEnv);
    const procB2 = await spawnWorker(commonEnv);
    expect(procA2.pid).not.toBe(procA.pid);
    expect(procB2.pid).not.toBe(procB.pid);

    const afterRestartA = await procA2.send("workspace_get", {
      headers: { Cookie: cookieHeader },
    });
    expect(afterRestartA.status).toBe(401);

    const afterRestartB = await procB2.send("workspace_post", {
      headers: { Cookie: cookieHeader, "X-CSRF-Token": csrfToken },
      body: { action: "list_questionnaires" },
    });
    expect(afterRestartB.status).toBe(401);
  });

  it("Scenario B: Concurrent Logout Across Separate Processes Preserves Every Revocation (No Lost Updates)", async () => {
    const stateFile = createTempStateFilePath("p06_scenario_b");
    const commonEnv = {
      ENV: "development",
      WORKSPACE_SESSION_SECRET: "p06-concurrent-session-secret-32chars-min!!",
      SESSION_REVOCATION_PATH: stateFile,
      BANKING_CROSSWALK_TENANT_ID: "local-workspace",
    };

    const procA = await spawnWorker(commonEnv);
    const procB = await spawnWorker(commonEnv);

    // 1. Create 16 distinct sessions across Process A and Process B
    const sessions: Array<{
      index: number;
      cookie: string;
      csrf: string;
      sid: string;
    }> = [];

    for (let i = 0; i < 16; i++) {
      const targetProc = i % 2 === 0 ? procA : procB;
      const login = await targetProc.send("login", {
        body: {
          username: "analyst",
          password: "analyst-local-pass",
          tenant_id: "local-workspace",
        },
      });
      expect(login.status).toBe(200);
      sessions.push({
        index: i,
        cookie: extractCookiePair(login.setCookie),
        csrf: String(login.body?.csrf_token),
        sid: String(login.body?.session_id),
      });
    }

    // Warm up both processes with an initial check
    for (const s of sessions) {
      const checkA = await procA.send("is_revoked", { sid: s.sid });
      const checkB = await procB.send("is_revoked", { sid: s.sid });
      expect(checkA.revoked).toBe(false);
      expect(checkB.revoked).toBe(false);
    }

    // 2. Concurrently revoke even sessions on Process A and odd sessions on Process B
    await Promise.all(
      sessions.map((s) => {
        const worker = s.index % 2 === 0 ? procA : procB;
        return worker.send("logout", {
          headers: {
            Cookie: s.cookie,
            "X-CSRF-Token": s.csrf,
            Origin: "http://localhost",
          },
        });
      })
    );

    // 3 & 4. Verify every single revocation is preserved across Process A, Process B, and a fresh Process C
    const procC = await spawnWorker(commonEnv);
    for (const s of sessions) {
      const revA = await procA.send("is_revoked", { sid: s.sid });
      const revB = await procB.send("is_revoked", { sid: s.sid });
      const revC = await procC.send("is_revoked", { sid: s.sid });
      expect(revA.revoked).toBe(true);
      expect(revB.revoked).toBe(true);
      expect(revC.revoked).toBe(true);

      const wsRes = await procB.send("workspace_get", {
        headers: { Cookie: s.cookie },
      });
      expect(wsRes.status).toBe(401);
    }
  });

  it("Scenario C: Cross-Process Membership, Account Disable/Delete & Role Downgrade Enforcement", async () => {
    const stateFile = createTempStateFilePath("p06_scenario_c");
    const commonUsers = [
      {
        user_id: "usr-disable-target",
        username: "disable_me",
        display_name: "Disable Target",
        password_hash: hashPassword("pass-disable-123"),
        tenants: { "local-workspace": ["reviewer"] },
      },
      {
        user_id: "usr-delete-target",
        username: "delete_me",
        display_name: "Delete Target",
        password_hash: hashPassword("pass-delete-123"),
        tenants: { "local-workspace": ["reviewer"] },
      },
      {
        user_id: "usr-tenant-target",
        username: "tenant_mover",
        display_name: "Tenant Target",
        password_hash: hashPassword("pass-tenant-123"),
        tenants: {
          "tenant-alpha": ["reviewer"],
          "tenant-beta": ["reviewer"],
        },
      },
      {
        user_id: "usr-downgrade-target",
        username: "downgrade_me",
        display_name: "Downgrade Target",
        password_hash: hashPassword("pass-downgrade-123"),
        tenants: { "local-workspace": ["reviewer"] },
      },
      {
        user_id: "usr-admin-target",
        username: "admin_target",
        display_name: "Admin Target",
        password_hash: hashPassword("pass-admin-123"),
        tenants: { "local-workspace": ["admin"] },
      },
    ];

    const commonEnv = {
      ENV: "development",
      WORKSPACE_SESSION_SECRET: "p06-membership-session-secret-32chars-min!!",
      SESSION_REVOCATION_PATH: stateFile,
      WORKSPACE_USERS_JSON: JSON.stringify(commonUsers),
    };

    const procA = await spawnWorker(commonEnv);
    const procB = await spawnWorker(commonEnv);

    // Log in all 5 accounts via Process A
    const loginDisable = await procA.send("login", {
      body: { username: "disable_me", password: "pass-disable-123" },
    });
    const loginDelete = await procA.send("login", {
      body: { username: "delete_me", password: "pass-delete-123" },
    });
    const loginTenantBeta = await procA.send("login", {
      body: {
        username: "tenant_mover",
        password: "pass-tenant-123",
        tenant_id: "tenant-beta",
      },
    });
    const loginDowngrade = await procA.send("login", {
      body: { username: "downgrade_me", password: "pass-downgrade-123" },
    });
    const loginAdmin = await procA.send("login", {
      body: { username: "admin_target", password: "pass-admin-123" },
    });

    expect(loginDisable.status).toBe(200);
    expect(loginDelete.status).toBe(200);
    expect(loginTenantBeta.status).toBe(200);
    expect(loginDowngrade.status).toBe(200);
    expect(loginAdmin.status).toBe(200);

    // Confirm Process B initially allows privileged operations for all 5 sessions
    for (const login of [
      loginDisable,
      loginDelete,
      loginTenantBeta,
      loginDowngrade,
    ]) {
      const res = await procB.send("workspace_post", {
        headers: {
          Cookie: extractCookiePair(login.setCookie),
          "X-CSRF-Token": String(login.body?.csrf_token),
        },
        body: {
          action: "review_clause",
          clause_id: "CL-100",
          status: "approved",
        },
      });
      expect(res.status).toBe(200);
    }

    const adminDeletePolicyBefore = await procB.send("workspace_post", {
      headers: {
        Cookie: extractCookiePair(loginAdmin.setCookie),
        "X-CSRF-Token": String(loginAdmin.body?.csrf_token),
      },
      body: { action: "delete_policy", policy_id: "POL-1" },
    });
    expect(adminDeletePolicyBefore.status).toBe(200);

    // Execute account / membership / role changes on Process A ONLY:
    // 1. Disable user account
    const op1 = await procA.send("set_user_disabled", {
      user_id: "usr-disable-target",
      disabled: true,
    });
    expect(op1.ok).toBe(true);

    // 2. Delete user account
    const op2 = await procA.send("delete_user", {
      user_id: "usr-delete-target",
    });
    expect(op2.ok).toBe(true);

    // 3. Remove tenant-beta membership
    const op3 = await procA.send("set_user_roles", {
      user_id: "usr-tenant-target",
      tenant_id: "tenant-beta",
      roles: null,
    });
    expect(op3.ok).toBe(true);

    // 4. Downgrade Reviewer to Analyst
    const op4 = await procA.send("set_user_roles", {
      user_id: "usr-downgrade-target",
      tenant_id: "local-workspace",
      roles: ["analyst"],
    });
    expect(op4.ok).toBe(true);

    // 5. Revoke Admin permissions (downgrade Admin -> Reviewer)
    const op5 = await procA.send("set_user_roles", {
      user_id: "usr-admin-target",
      tenant_id: "local-workspace",
      roles: ["reviewer"],
    });
    expect(op5.ok).toBe(true);

    // Verify immediate enforcement on Process B!
    // 1. Disabled user rejected with 401 on Process B
    const afterDisableB = await procB.send("workspace_get", {
      headers: { Cookie: extractCookiePair(loginDisable.setCookie) },
    });
    expect(afterDisableB.status).toBe(401);

    // 2. Deleted user rejected with 401 on Process B
    const afterDeleteB = await procB.send("workspace_get", {
      headers: { Cookie: extractCookiePair(loginDelete.setCookie) },
    });
    expect(afterDeleteB.status).toBe(401);

    // 3. Removed tenant membership rejected with 403 on Process B
    const afterTenantRemovalB = await procB.send("workspace_get", {
      headers: { Cookie: extractCookiePair(loginTenantBeta.setCookie) },
    });
    expect(afterTenantRemovalB.status).toBe(403);

    // 4. Reviewer downgraded to Analyst rejected with 403 on review_clause in Process B, but allowed read/upload
    const afterDowngradeReviewB = await procB.send("workspace_post", {
      headers: {
        Cookie: extractCookiePair(loginDowngrade.setCookie),
        "X-CSRF-Token": String(loginDowngrade.body?.csrf_token),
      },
      body: {
        action: "review_clause",
        clause_id: "CL-100",
        status: "approved",
      },
    });
    expect(afterDowngradeReviewB.status).toBe(403);
    expect(afterDowngradeReviewB.backendCalled).toBe(false);

    const afterDowngradeReadB = await procB.send("workspace_post", {
      headers: {
        Cookie: extractCookiePair(loginDowngrade.setCookie),
        "X-CSRF-Token": String(loginDowngrade.body?.csrf_token),
      },
      body: { action: "list_questionnaires" },
    });
    expect(afterDowngradeReadB.status).toBe(200);
    // And verify backend assertion carries the downgraded "analyst" role, not "reviewer"
    expect(afterDowngradeReadB.backendHeaders?.["X-Role"]).toBe("analyst");

    // 5. Admin downgraded to Reviewer rejected with 403 on delete_policy in Process B
    const afterAdminRevokeB = await procB.send("workspace_post", {
      headers: {
        Cookie: extractCookiePair(loginAdmin.setCookie),
        "X-CSRF-Token": String(loginAdmin.body?.csrf_token),
      },
      body: { action: "delete_policy", policy_id: "POL-1" },
    });
    expect(afterAdminRevokeB.status).toBe(403);
    expect(afterAdminRevokeB.backendCalled).toBe(false);
  });

  it("Scenario D: Cross-Process Login Rate Limiting Cannot Be Bypassed By Worker Distribution Or Spoofed X-Forwarded-For", async () => {
    const stateFile = createTempStateFilePath("p06_scenario_d");
    const commonEnv = {
      ENV: "development",
      WORKSPACE_SESSION_SECRET: "p06-ratelimit-session-secret-32chars-min!!",
      SESSION_REVOCATION_PATH: stateFile,
    };

    const procA = await spawnWorker(commonEnv);
    const procB = await spawnWorker(commonEnv);

    // 3 failed attempts on Process A and 2 failed attempts on Process B (total 5)
    // Even with spoofed rotating X-Forwarded-For headers on every request!
    for (let i = 0; i < 5; i++) {
      const worker = i % 2 === 0 ? procA : procB;
      const res = await worker.send("login", {
        headers: {
          "X-Forwarded-For": `203.0.113.${10 + i}`,
        },
        body: {
          username: "analyst",
          password: `wrong-password-${i}`,
        },
      });
      expect(res.status).toBe(401);
    }

    // 6th attempt on Process B (with yet another spoofed X-Forwarded-For and even the CORRECT password) MUST be rate-limited (429)
    const sixthAttemptB = await procB.send("login", {
      headers: {
        "X-Forwarded-For": "198.51.100.99",
      },
      body: {
        username: "analyst",
        password: "analyst-local-pass",
      },
    });
    expect(sixthAttemptB.status).toBe(429);

    // And on Process A as well
    const seventhAttemptA = await procA.send("login", {
      headers: {
        "X-Forwarded-For": "198.51.100.100",
      },
      body: {
        username: "analyst",
        password: "analyst-local-pass",
      },
    });
    expect(seventhAttemptA.status).toBe(429);
  });

  it("Scenario E: Fail-Closed Behaviour When Security State Storage Is Corrupted Or Multi-Instance Is Unsafely Configured", async () => {
    const stateFile = createTempStateFilePath("p06_scenario_e");
    const commonEnv = {
      ENV: "development",
      WORKSPACE_SESSION_SECRET: "p06-failclosed-session-secret-32chars-min!!",
      SESSION_REVOCATION_PATH: stateFile,
      BANKING_CROSSWALK_TENANT_ID: "local-workspace",
    };

    const procA = await spawnWorker(commonEnv);
    const procB = await spawnWorker(commonEnv);

    const loginRes = await procA.send("login", {
      body: {
        username: "reviewer",
        password: "reviewer-local-pass",
      },
    });
    expect(loginRes.status).toBe(200);
    const cookieHeader = extractCookiePair(loginRes.setCookie);

    const okBefore = await procB.send("workspace_get", {
      headers: { Cookie: cookieHeader },
    });
    expect(okBefore.status).toBe(200);

    // Corrupt the persisted security state file on disk
    fs.writeFileSync(stateFile, "{corrupted-json-security-state!!!", "utf8");

    // Process B must NOT silently fall back to memory or allow authenticated access; it must fail closed (401 or 503)
    const afterCorruptB = await procB.send("workspace_get", {
      headers: { Cookie: cookieHeader },
    });
    expect([401, 503]).toContain(afterCorruptB.status);

    // Also verify unsupported multi-instance topology fails readiness check (503)
    const procMulti = await spawnWorker({
      ...commonEnv,
      ENV: "production",
      CROSSWALK_API_KEY: "prod-api-key-12345",
      WORKSPACE_USERS_JSON: JSON.stringify([
        {
          user_id: "usr-prod-1",
          username: "reviewer",
          password_hash: hashPassword("prod-pass-123"),
          tenants: { "local-workspace": ["reviewer"] },
        },
      ]),
      DEPLOYMENT_TOPOLOGY: "multi_instance",
    });

    const multiSessionRes = await procMulti.send("session");
    expect(multiSessionRes.status).toBe(503);
    expect(multiSessionRes.body?.ready).toBe(false);
  });

  it("Scenario F: Backward-Compatible Migration From Legacy v1 Revocation Format & Expired Entry Pruning", async () => {
    const stateFile = createTempStateFilePath("p06_scenario_f");
    const now = Math.floor(Date.now() / 1000);
    const legacyV1Entries = [
      {
        sid: "legacy-raw-sid-active-999",
        revokedAt: now - 60,
        expiresAt: now + 3600,
      },
      {
        sid: "legacy-raw-sid-expired-111",
        revokedAt: now - 7200,
        expiresAt: now - 3600,
      },
    ];
    fs.writeFileSync(stateFile, JSON.stringify(legacyV1Entries), "utf8");

    const commonEnv = {
      ENV: "development",
      WORKSPACE_SESSION_SECRET: "p06-migration-session-secret-32chars-min!!",
      SESSION_REVOCATION_PATH: stateFile,
    };

    const procA = await spawnWorker(commonEnv);
    const procB = await spawnWorker(commonEnv);

    // Active legacy v1 entry is recognized as revoked across both processes
    const activeCheckA = await procA.send("is_revoked", {
      sid: "legacy-raw-sid-active-999",
    });
    const activeCheckB = await procB.send("is_revoked", {
      sid: "legacy-raw-sid-active-999",
    });
    expect(activeCheckA.revoked).toBe(true);
    expect(activeCheckB.revoked).toBe(true);

    // Expired legacy v1 entry is pruned / not revoked
    const expiredCheckA = await procA.send("is_revoked", {
      sid: "legacy-raw-sid-expired-111",
    });
    expect(expiredCheckA.revoked).toBe(false);

    // Trigger a write on Process A to upgrade the file to v2 format with SHA-256 digests
    await procA.send("revoke_session", {
      sid: "new-session-id-to-trigger-v2-upgrade",
      expiresAt: now + 3600,
    });

    const upgradedRaw = fs.readFileSync(stateFile, "utf8");
    const upgradedParsed = JSON.parse(upgradedRaw);
    expect(upgradedParsed.version).toBe(2);
    expect(upgradedRaw).not.toContain("legacy-raw-sid-active-999");
    expect(upgradedRaw).not.toContain("new-session-id-to-trigger-v2-upgrade");
    expect(upgradedRaw).not.toContain("legacy-raw-sid-expired-111");

    // Process B still sees both revocations after v2 migration
    const afterUpgradeB1 = await procB.send("is_revoked", {
      sid: "legacy-raw-sid-active-999",
    });
    const afterUpgradeB2 = await procB.send("is_revoked", {
      sid: "new-session-id-to-trigger-v2-upgrade",
    });
    expect(afterUpgradeB1.revoked).toBe(true);
    expect(afterUpgradeB2.revoked).toBe(true);
  });
});
