#!/usr/bin/env node
/**
 * Operator password utility for DeepAudit Crosswalk.
 * Generates and verifies modern salted scrypt password hashes for WORKSPACE_USERS_JSON.
 *
 * Usage:
 *   node scripts/hash_password.js "<password>"
 *   node scripts/hash_password.js --verify "scrypt$<salt>$<hash>" "<candidate-password>"
 */

const crypto = require("crypto");

function hashPassword(password) {
  if (!password || typeof password !== "string") {
    throw new Error("Password must be a non-empty string");
  }
  const salt = crypto.randomBytes(16).toString("hex");
  const derived = crypto.scryptSync(password, salt, 64, {
    N: 16384,
    r: 8,
    p: 1,
  });
  return `scrypt$${salt}$${derived.toString("hex")}`;
}

function verifyPassword(password, storedHash) {
  if (!storedHash || !storedHash.startsWith("scrypt$")) {
    return false;
  }
  const parts = storedHash.split("$");
  if (parts.length !== 3) {
    return false;
  }
  const [, salt, expectedHashHex] = parts;
  const derived = crypto.scryptSync(password, salt, 64, {
    N: 16384,
    r: 8,
    p: 1,
  });
  const bufExpected = Buffer.from(expectedHashHex, "hex");
  if (derived.length !== bufExpected.length) {
    return false;
  }
  return crypto.timingSafeEqual(derived, bufExpected);
}

function printUsage() {
  console.log("DeepAudit Crosswalk - Password Hashing Utility\n");
  console.log("Generate a secure password hash:");
  console.log('  node scripts/hash_password.js "your-secure-password"\n');
  console.log("Verify a password hash:");
  console.log('  node scripts/hash_password.js --verify "scrypt$<salt>$<hash>" "your-secure-password"\n');
}

if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.length === 0 || args[0] === "--help" || args[0] === "-h") {
    printUsage();
    process.exit(0);
  }

  if (args[0] === "--verify") {
    if (args.length < 3) {
      console.error('Error: --verify requires <hash> and <password>');
      process.exit(1);
    }
    const hash = args[1];
    const candidate = args[2];
    const match = verifyPassword(candidate, hash);
    if (match) {
      console.log("Password MATCHES stored hash.");
      process.exit(0);
    } else {
      console.error("Password DOES NOT MATCH stored hash.");
      process.exit(1);
    }
  }

  const pwd = args[0];
  const hash = hashPassword(pwd);
  console.log("================================================================================");
  console.log("DeepAudit Crosswalk - Generated Password Hash (scrypt)");
  console.log("================================================================================");
  console.log(`Hash: ${hash}\n`);
  console.log("Example WORKSPACE_USERS_JSON entry:");
  const exampleUser = [
    {
      user_id: "usr-admin-01",
      username: "admin",
      display_name: "Workspace Administrator",
      password_hash: hash,
      tenants: {
        "your-tenant-id": ["admin", "reviewer"],
      },
    },
  ];
  console.log(JSON.stringify(exampleUser, null, 2));
  console.log("================================================================================");
}

module.exports = { hashPassword, verifyPassword };
