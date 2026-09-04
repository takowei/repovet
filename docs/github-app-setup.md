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

## ⚡ 2026-09-05 實查：現況與縮短後的步驟

Everything below was verified live on bongo and from the public internet on
2026-09-05, so most of the fiddly parts are already settled:

| 項目 | 實查結果 |
| --- | --- |
| **Webhook URL（現行）** | **`https://ministries-foster-duty-offerings.trycloudflare.com/webhook`** — 實測 `POST` 回 **401**（＝簽章驗證正在運作，伺服器活著）、`GET /health` 回 `{"status": "ok"}`。⚠️ 這是 quick tunnel，**容器重啟就會換**。 |
| **Webhook secret** | ✅ **伺服器上已經有了**（`~/docker/Repovet/app/.env` 的 `REPOVET_WEBHOOK_SECRET`，64 hex＝`openssl rand -hex 32` 的長度）。**不要重新產生**——重生會讓兩邊不一致。 |
| **App ID / private key** | ❌ 還是 11 字元的**佔位符**，不是真值。**這兩個就是唯一缺的東西。** |
| **伺服器容器** | `repovet-app` / `repovet-scan-cron` / `repovet-trending-cron` / `repovet-tunnel` 皆 Up 5 days（bongo 25 容器全 Up） |
| **App 名稱是否被佔用** | `github.com/apps/repovet` 與 `github.com/apps/repovet-trust-check` 皆回 **404**＝兩個名字都還沒被建立、可用 |

**所以實際只剩三步**：

1. 到 <https://github.com/settings/apps/new> 建 App，Webhook URL 填上面那個，
   Webhook secret 欄位貼**伺服器上已存在的那組**——在 bongo 上讀出來：
   ```bash
   grep '^REPOVET_WEBHOOK_SECRET=' ~/docker/Repovet/app/.env
   ```
   權限與事件訂閱照下面第 1 節的表。
2. 建完後在 App 設定頁拿 **App ID**、按 **Generate a private key** 下載 `.pem`。
3. 把這兩個值寫回 `~/docker/Repovet/app/.env`（覆蓋 `REPOVET_APP_ID` 與
   `REPOVET_APP_PRIVATE_KEY` 那兩行的佔位符），然後
   `docker compose -f ~/docker/Repovet/docker-compose.yml up -d --force-recreate app`。

> 🔴 **設計上的隱憂，建 App 前先知道**：現在的 Webhook URL 是 cloudflared
> **quick tunnel**，網址在 `repovet-tunnel` 容器每次重啟時都會變，而 GitHub App 的
> Payload URL 是寫死在 App 設定裡的——**容器一重啟，webhook 就靜默失效**。
> 這不是「以後再說」的問題，是這個 App 的地基。兩個修法：
> ① 部署 `cloudflare-worker/`（本 repo 內，免費 `*.workers.dev` 是**固定網址**，
>    不需要買網域；需要 Root 跑一次互動式 `npx wrangler login`），把 Worker 當
>    穩定入口再轉發到 bongo；② 用 Cloudflare **named tunnel**（需 Cloudflare 帳號）。
> 兩者都比「每次重啟就回 GitHub 改設定」實際。

---

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
