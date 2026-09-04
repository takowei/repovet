/**
 * repovet-webhook-verify: minimal GitHub webhook receiver stub.
 *
 * Purpose: prove a *.workers.dev URL can receive a GitHub App webhook
 * delivery and respond 200 -- nothing more. See README.md in this
 * directory for why this exists and what it deliberately does NOT do.
 */

async function verifySignature(secret, payloadText, signatureHeader) {
  if (!signatureHeader || !signatureHeader.startsWith("sha256=")) {
    return false;
  }
  const expectedHex = signatureHeader.slice("sha256=".length);

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const mac = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payloadText),
  );
  const macHex = [...new Uint8Array(mac)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  // Constant-time-ish comparison (length-checked first).
  if (macHex.length !== expectedHex.length) return false;
  let diff = 0;
  for (let i = 0; i < macHex.length; i++) {
    diff |= macHex.charCodeAt(i) ^ expectedHex.charCodeAt(i);
  }
  return diff === 0;
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("repovet-webhook-verify: POST only", { status: 405 });
    }

    const event = request.headers.get("X-GitHub-Event") || "unknown";
    const signature = request.headers.get("X-Hub-Signature-256");
    const bodyText = await request.text();

    if (env.GITHUB_WEBHOOK_SECRET) {
      const ok = await verifySignature(
        env.GITHUB_WEBHOOK_SECRET,
        bodyText,
        signature,
      );
      if (!ok) {
        return new Response(
          JSON.stringify({ ok: false, error: "bad signature" }),
          {
            status: 401,
            headers: { "content-type": "application/json" },
          },
        );
      }
    }

    if (event === "ping") {
      return new Response(JSON.stringify({ ok: true, note: "ping" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }

    // Deliberately inert: log-only, no GitHub API calls, no side effects.
    return new Response(JSON.stringify({ ok: true, event }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  },
};
