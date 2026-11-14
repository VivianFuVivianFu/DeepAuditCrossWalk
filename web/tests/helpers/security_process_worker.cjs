"use strict";

const Module = require("node:module");
const readline = require("node:readline");

const origResolveFilename = Module._resolveFilename;
Module._resolveFilename = function (request, parent, isMain, options) {
  if (request === "next/server") {
    request = "next/server.js";
  }
  return origResolveFilename.call(this, request, parent, isMain, options);
};

if (typeof Module.registerHooks === "function") {
  Module.registerHooks({
    resolve(specifier, context, nextResolve) {
      if (specifier === "next/server") {
        return nextResolve("next/server.js", context);
      }
      if (
        (specifier.startsWith("./") || specifier.startsWith("../")) &&
        !specifier.endsWith(".ts") &&
        !specifier.endsWith(".js")
      ) {
        try {
          return nextResolve(`${specifier}.ts`, context);
        } catch {
          return nextResolve(specifier, context);
        }
      }
      return nextResolve(specifier, context);
    },
  });
}

const security = require("../../app/security.ts");
const { POST: loginPOST } = require("../../app/api/auth/login/route.ts");
const { POST: logoutPOST } = require("../../app/api/auth/logout/route.ts");
const { GET: sessionGET } = require("../../app/api/auth/session/route.ts");
const {
  GET: workspaceGET,
  POST: workspacePOST,
} = require("../../app/api/workspace/route.ts");

async function handleCommand(cmd) {
  const { id, action, payload = {} } = cmd;
  try {
    if (action === "ping") {
      return { id, ok: true, pid: process.pid };
    }

    if (action === "login") {
      const headers = {
        "Content-Type": "application/json",
        ...(payload.headers || {}),
      };
      const req = new Request(payload.url || "http://localhost/api/auth/login", {
        method: "POST",
        headers,
        body: JSON.stringify(payload.body || {}),
      });
      const res = await loginPOST(req);
      const data = await res.json().catch(() => ({}));
      return {
        id,
        ok: true,
        pid: process.pid,
        status: res.status,
        setCookie: res.headers.get("set-cookie"),
        body: data,
      };
    }

    if (action === "logout") {
      const headers = { ...(payload.headers || {}) };
      const req = new Request(payload.url || "http://localhost/api/auth/logout", {
        method: "POST",
        headers,
      });
      const res = await logoutPOST(req);
      const data = await res.json().catch(() => ({}));
      return {
        id,
        ok: true,
        pid: process.pid,
        status: res.status,
        setCookie: res.headers.get("set-cookie"),
        body: data,
      };
    }

    if (action === "session") {
      const headers = { ...(payload.headers || {}) };
      const req = new Request(payload.url || "http://localhost/api/auth/session", {
        method: "GET",
        headers,
      });
      const res = await sessionGET(req);
      const data = await res.json().catch(() => ({}));
      return {
        id,
        ok: true,
        pid: process.pid,
        status: res.status,
        body: data,
      };
    }

    if (action === "workspace_get") {
      const headers = { ...(payload.headers || {}) };
      const req = new Request(payload.url || "http://localhost/api/workspace", {
        method: "GET",
        headers,
      });
      const res = await workspaceGET(req);
      const data = await res.json().catch(() => ({}));
      return {
        id,
        ok: true,
        pid: process.pid,
        status: res.status,
        body: data,
      };
    }

    if (action === "workspace_post") {
      let backendCalled = false;
      let capturedBackendHeaders = null;
      const origFetch = globalThis.fetch;
      globalThis.fetch = async (_url, init) => {
        backendCalled = true;
        capturedBackendHeaders = init && init.headers ? init.headers : {};
        return new Response(
          JSON.stringify(payload.mockBackendResponse ?? { ok: true, items: [] }),
          {
            status: payload.mockBackendStatus ?? 200,
            headers: { "Content-Type": "application/json" },
          }
        );
      };
      try {
        const headers = {
          "Content-Type": "application/json",
          ...(payload.headers || {}),
        };
        const req = new Request(payload.url || "http://localhost/api/workspace", {
          method: "POST",
          headers,
          body: JSON.stringify(payload.body || {}),
        });
        const res = await workspacePOST(req);
        const data = await res.json().catch(() => ({}));
        return {
          id,
          ok: true,
          pid: process.pid,
          status: res.status,
          backendCalled,
          backendHeaders: capturedBackendHeaders,
          body: data,
        };
      } finally {
        globalThis.fetch = origFetch;
      }
    }

    if (action === "revoke_session") {
      security.revokeSession(payload.sid, payload.expiresAt);
      return { id, ok: true, pid: process.pid };
    }

    if (action === "is_revoked") {
      const revoked = security.isSessionRevoked(payload.sid);
      return { id, ok: true, pid: process.pid, revoked };
    }

    if (action === "upsert_user") {
      security.upsertRuntimeWorkspaceUser(payload.user);
      return { id, ok: true, pid: process.pid };
    }

    if (action === "set_user_disabled") {
      security.setRuntimeUserDisabled(payload.user_id, payload.disabled);
      return { id, ok: true, pid: process.pid };
    }

    if (action === "delete_user") {
      if (typeof security.deleteRuntimeWorkspaceUser === "function") {
        security.deleteRuntimeWorkspaceUser(payload.user_id);
      } else {
        throw new Error("deleteRuntimeWorkspaceUser is not implemented");
      }
      return { id, ok: true, pid: process.pid };
    }

    if (action === "set_user_roles") {
      security.setRuntimeUserTenantRoles(
        payload.user_id,
        payload.tenant_id,
        payload.roles
      );
      return { id, ok: true, pid: process.pid };
    }

    return { id, ok: false, pid: process.pid, error: `Unknown action: ${action}` };
  } catch (err) {
    return {
      id,
      ok: false,
      pid: process.pid,
      error: err && err.message ? err.message : String(err),
    };
  }
}

const rl = readline.createInterface({
  input: process.stdin,
  terminal: false,
});

rl.on("line", async (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let parsed;
  try {
    parsed = JSON.parse(trimmed);
  } catch (err) {
    process.stdout.write(
      JSON.stringify({ ok: false, error: "Invalid JSON line" }) + "\n"
    );
    return;
  }
  const resp = await handleCommand(parsed);
  process.stdout.write(JSON.stringify(resp) + "\n");
});
