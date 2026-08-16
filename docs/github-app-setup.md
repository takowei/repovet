# GitHub App setup — Root's manual checklist

Everything code-side is already built and tested (`src/repovet/app_server.py`,
`app_webhook.py`, `app_auth.py`, `webhook_security.py`, `plan_store.py`, all
covered by `tests/test_app_*.py` + `tests/test_webhook_security.py`, 181
tests green as of this doc). The server is already deployed and running on
bongo (`docker-compose.bongo.yml`, service `app`, port `8002` behind a
cloudflared quick tunnel).

**What's left is entirely GitHub-account-level actions only Root can take**
(creating an App is tied to a GitHub account/org and can't be done from a
sandboxed agent). This doc is the copy-paste checklist for that.

## 1. Create the App

Go to <https://github.com/settings/apps/new> and fill in:

| Field                | Value                                                                                                                                                                                                                                                                                                                                                                                                  |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **GitHub App name**  | `repovet` (or `repovet-trust-check` if `repovet` is taken — App names are globally unique across all of GitHub)                                                                                                                                                                                                                                                                                        |
| **Homepage URL**     | `https://github.com/takowei/repovet`                                                                                                                                                                                                                                                                                                                                                                   |
| **Webhook → Active** | checked                                                                                                                                                                                                                                                                                                                                                                                                |
| **Webhook URL**      | the current bongo cloudflared tunnel URL + `/webhook` (e.g. `https://<random>.trycloudflare.com/webhook`) — **get the live URL from the server first** (`docker compose -f docker-compose.bongo.yml logs tunnel` on bongo, or check `~/docker/Repovet/Server.md`), it changes if the `tunnel` container restarts. The server also accepts `/webhooks/github` as an alias if that's easier to remember. |
| **Webhook secret**   | generate with `openssl rand -hex 32` **on the server itself**, paste the same value into both this field and the server's `.env` (`REPOVET_WEBHOOK_SECRET`) — see step 3                                                                                                                                                                                                                               |
| **SSL verification** | leave enabled (cloudflared terminates TLS)                                                                                                                                                                                                                                                                                                                                                             |

### Permissions (Repository permissions section)

| Permission        | Level        | Why                                                                                                             |
| ----------------- | ------------ | --------------------------------------------------------------------------------------------------------------- |
| **Pull requests** | Read & write | read PR metadata, write the scan-result comment                                                                 |
| **Issues**        | Read & write | PR comments are posted through the Issues API (`post_issue_comment` in `bot.py`, reused by the webhook handler) |
| **Contents**      | Read-only    | S2/S3/S4 signals read repo files (commits, manifests, README)                                                   |
| **Metadata**      | Read-only    | mandatory baseline permission GitHub requires for every App                                                     |

Do not grant anything beyond this list — no Actions, no Admin, no Checks.
The engine never writes to repo contents or settings.

### Subscribe to events

Check these boxes under "Subscribe to events" (only shows options matching
the permissions granted above):

- `Pull request`
- `Marketplace purchase` (wired up now — dormant until the App has 100+
  installs and a paid plan is added later; see README "GitHub App /
  Marketplace")
- `Installation`
- `Installation repositories`

### Where can this GitHub App be installed?

Choose **"Any account"** if the goal is public Marketplace distribution.
Choose "Only on this account" for private testing first, then flip it later
in the App's settings page — this is not a one-time irreversible choice.

Click **Create GitHub App**.

## 2. After creation — collect the three secrets

On the new App's settings page:

1. **App ID** — shown at the top of the page. Copy it.
2. **Generate a private key** — scroll to "Private keys" → "Generate a
   private key". This downloads a `.pem` file **once** (GitHub does not
   store a copy) — save it somewhere safe, never commit it to git.
3. **Webhook secret** — the value you generated in step 1 with
   `openssl rand -hex 32`.

## 3. Wire the secrets into the running server

On bongo, in `~/docker/Repovet/.env` (the file `deploy-env.sample` in this
repo is the template — copy it there and fill in real values, it's already
gitignored):

```bash
REPOVET_APP_ID=<App ID from step 2.1>
REPOVET_APP_PRIVATE_KEY=<paste the full .pem contents, keep the literal newlines>
REPOVET_WEBHOOK_SECRET=<the same value pasted into the GitHub App's webhook secret field>
```

Then restart the `app` service so it picks up the new env:

```bash
docker compose -f docker-compose.bongo.yml up -d --build app
```

Sanity check: `GET https://<tunnel-url>/health` should return
`{"status": "ok"}`. GitHub also sends a `ping` event immediately after the
App is created if the webhook URL was reachable at creation time — check
"Recent Deliveries" on the App's "Advanced" tab; a `200` there confirms the
signature verification round-trip works end to end.

## 4. Install the App on a test repo

On the App's public page (`https://github.com/apps/<app-slug>`) or via
"Install App" in the left sidebar of the App's settings, install it on one
of your own repos first (not `takowei/repovet` itself — that already has
the opt-in Action bot; pick a throwaway test repo). Open a PR there and
confirm repovet posts a scan comment automatically, matching the existing
`--reply` output format.

## 5. (Later, not now) List on GitHub Marketplace

Only after the App has been running stably for a while and Root wants
public distribution:

1. On the App's settings page → "Marketplace" tab → agree to the
   Marketplace Developer Agreement.
2. Fill in listing copy, a logo/icon, a short + long description,
   screenshots or a short demo.
3. Add a pricing plan — **free plan only for stage 1** (the
   `marketplace_purchase` webhook and `plan_store.py` are already wired up
   for a future paid tier, but GitHub requires the App to reach 100+
   installations before a paid plan can go live at all).
4. Submit for review. This is a manual review by a real GitHub person —
   community reports ~2-6 weeks turnaround, no published SLA.

## Known limitation to flag to Root before relying on this

The webhook URL depends on the cloudflared **quick** tunnel, which issues a
new random URL every time the `tunnel` container restarts — if that
happens, the App's webhook URL in its GitHub settings page needs a manual
update or deliveries will 404/timeout. Buying a domain (queued elsewhere,
see `moneymaking-line-status` memory) removes this fragility by giving the
tunnel/App a stable hostname. Not a blocker for testing on a throwaway repo,
but worth fixing before a real Marketplace listing goes live.
