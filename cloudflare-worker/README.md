# repovet-webhook-verify (Cloudflare Worker)

Minimal proof that a GitHub App webhook can be received on a
`*.workers.dev` URL (no custom domain purchase required). This is a
**verification stub only** — it does not run the real scan/comment logic
in `src/repovet/app_webhook.py`; it just proves the delivery path:

GitHub → HTTPS POST → this Worker → 200 response.

## Why this exists

`../CLAUDE.md` / README previously assumed a custom domain was needed
before submitting to GitHub Marketplace. That assumption was unverified.
GitHub's own docs (see citations in the dev-lead report that shipped this
file) only require an HTTPS endpoint for the webhook Payload URL — a
Cloudflare Workers free-tier `*.workers.dev` subdomain satisfies that.

## What it does

- Accepts `POST /` (any path)
- Reads the `X-GitHub-Event` and `X-Hub-Signature-256` headers
- Verifies HMAC-SHA256 signature against `GITHUB_WEBHOOK_SECRET` (if the
  secret is configured) — same algorithm as `webhook_security.py`,
  reimplemented in Workers' WebCrypto since Python isn't available here
- Responds `200 {"ok": true, "event": "..."}` on success, `401` on bad
  signature, `200 {"ok": true, "note": "ping"}` for GitHub's `ping` event
- Does **not** call the GitHub API, does **not** run a scan, does **not**
  touch `plan_store` — deliberately inert, so it's safe to leave attached
  to a real GitHub App during setup without triggering side effects

## Files

- `worker.js` — the Worker source (no build step, no dependencies)
- `wrangler.toml` — Cloudflare Workers config (name, compatibility date)

## Deploy (needs Root — requires interactive Cloudflare auth)

```bash
cd cloudflare-worker
npx wrangler login          # opens browser, one-time interactive auth
npx wrangler deploy         # publishes to <name>.<your-subdomain>.workers.dev
npx wrangler secret put GITHUB_WEBHOOK_SECRET   # paste the App's webhook secret
```

`wrangler` was not present in this sandbox (`which wrangler` → not found,
and this environment has no network path to `npm install -g` / Cloudflare
auth flows that need a browser). `npx wrangler` will fetch it on first run
if `npm`/`node` are available; otherwise install per
https://developers.cloudflare.com/workers/wrangler/install-and-update/.

After `wrangler deploy` prints the URL (e.g.
`https://repovet-webhook-verify.<subdomain>.workers.dev`), paste it into
the GitHub App's "Webhook URL" field and use "Redeliver" on a past
delivery (or trigger a real `ping`) to confirm a 200 response in the
App's "Recent Deliveries" tab.

## Not in scope here

This stub does not replace `app_server.py` / `app_webhook.py` for
production — those still need a real Python runtime (bongo, or a Workers
rewrite, which is a separate, larger task) to run scans and post PR
comments. This only unblocks the "do we need a domain first" question.
