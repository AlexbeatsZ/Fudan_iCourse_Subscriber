// Run with: node test_frontend_crypto.js
// WebCrypto compatibility checks without a browser or school credentials.
const assert = require("node:assert/strict");
const { createHash, webcrypto } = require("node:crypto");
const fs = require("node:fs");
const vm = require("node:vm");

const context = vm.createContext({
  window: { crypto: webcrypto },
  TextEncoder, TextDecoder, Uint8Array, ArrayBuffer,
  location: { protocol: "https:", host: "example.github.io" },
});
vm.runInContext(fs.readFileSync("frontend/js/crypto.js", "utf8"), context);
const crypt = context.window.ICS.crypto;
const sha = (s) => createHash("sha256").update(s).digest("hex");

(async () => {
  const independent = { dbPassword: "independent-for-test" };
  const expected = sha("ICSdb:independent-for-test");
  assert.equal(await crypt.buildDatabasePassword(independent), expected);

  const plaintext = new TextEncoder().encode('{"shards":[]}');
  const encrypted = await crypt.encrypt(plaintext, expected);
  const opened = await crypt.decryptWithFallback(
    encrypted, independent, crypt.isJsonObj,
  );
  assert.equal(opened.version, "custom");
  assert.deepEqual(Array.from(opened.data), Array.from(plaintext));

  const old = { stuid: "student", uispsw: "password" };
  const oldCiphertext = await crypt.encrypt(
    plaintext, await crypt.buildPasswordV2(old),
  );
  const migrated = await crypt.decryptWithFallback(
    oldCiphertext, { ...old, dbPassword: "new-password" }, crypt.isJsonObj,
  );
  assert.equal(migrated.version, "v2");
  await assert.rejects(
    () => crypt.decryptWithFallback(encrypted, { dbPassword: "wrong" }, crypt.isJsonObj),
    /解密失败/,
  );
  console.log("Frontend independent password, old-key fallback, and wrong-key tests passed.");
})().catch((error) => { console.error(error); process.exitCode = 1; });
