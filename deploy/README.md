# Deploying Aria

The laptop plus a cloudflared quick tunnel got a demo working, but the tunnel
minted a new hostname on every `run.bat`, so nothing could be written down —
not a link to hand someone, and not a server address to bake into an APK.
This puts the whole stack on one Oracle box behind a domain that does not
move.

**Target:** `aria-server`, VM.Standard.A1.Flex, Ubuntu 24.04 **aarch64**,
ap-mumbai-1.

All four images the stack needs (`espocrm/espocrm`, `mariadb:11`, `caddy:2`,
plus the Python and Node bases) publish arm64, so the ARM shape needs no
special handling — verified with `docker manifest inspect`.

---

## What runs where

One hostname serves the console *and* the API, split by path in
[`Caddyfile`](Caddyfile). That is deliberate: same origin means the browser
never makes a cross-origin request, so CORS stops being something that can
break.

```
                    internet
                       |
              :80 / :443 only
                       |
                   +---v---+
                   | Caddy |  automatic TLS, renews itself
                   +---+---+
      aria.aroice.in   |   crm.aria.aroice.in
        +--------------+--------------+
        |                             |
   /api  /agent  /rep  /healthz       +--> espocrm  (+ websocket, daemon)
        |            everything else                        |
   +----v----+        +----v-----+                    +-----v-----+
   | backend |        | frontend |                    |  mariadb  |
   |  :8000  |        |  :3000   |                    +-----------+
   +---------+        +----------+
```

Only 80 and 443 are published. The backend, the database and Espo's HTTP port
are on the compose network and unreachable from outside the box. Espo is
additionally bound to `127.0.0.1:8080` so the provisioning script can reach it
from the host — loopback, not `0.0.0.0`, because an unauthenticated CRM on a
public port is an open CRM.

**The backend runs `--workers 1`, and that is not a resource decision.**
Sessions live in an in-process dict (`backend/app/sessions/store.py`), so a
second worker gets its own empty copy: a call started on one worker is
invisible to the other, and Agora's next webhook for that call lands on a
process that has never heard of it. Scaling out means moving sessions to Redis
first — no autoscaling, no replicas, no `--workers 4`.

---

## Before you start

You need, in this order:

1. **A public IP on the instance.** It currently shows `-`, which means
   nothing can reach it.
2. **Ports 80 and 443 open** — in the VCN security list *and* on the instance
   itself. Oracle's Ubuntu image ships iptables rules that reject everything
   but SSH, so the console alone is not enough. Missing the second one makes
   the connection *hang* rather than be refused, which reads exactly like a
   DNS problem and sends you looking in the wrong place.
3. **Two DNS A records**, both pointing at that IP.

### 1 · Assign the public IP

Oracle console → **Compute → Instances → aria-server → Networking** tab →
under *Primary VNIC*, click the subnet's **IPv4 addresses** → on the private
IP row, **⋮ → Edit** → **Public IP: Ephemeral** (or *Reserved* if you want it
to survive a stop/start) → **Update**.

Then confirm the subnet is public: **Networking → Virtual Cloud Networks →
aria-vcn → Subnets →** your subnet. If it says *Private*, no public IP can be
assigned to anything in it and the subnet has to be replaced.

Write the IP down. Everything below uses it.

### 2 · Open the ports in the VCN

**aria-vcn → Subnets →** your subnet **→ Security Lists →** the default list
**→ Add Ingress Rules.** Two rules, both stateless **No**:

| Source CIDR | IP Protocol | Destination Port |
|-------------|-------------|------------------|
| `0.0.0.0/0` | TCP         | `80`             |
| `0.0.0.0/0` | TCP         | `443`            |

Port 80 is not optional — Let's Encrypt validates over it before Caddy can
serve 443.

### 3 · Point the domain at it (Cloudflare)

Cloudflare dashboard → **aroice.in → DNS → Records → Add record**, twice:

| Type | Name       | IPv4 address     | Proxy status          | TTL  |
|------|------------|------------------|-----------------------|------|
| A    | `aria`     | *your public IP* | **DNS only** (grey)   | Auto |
| A    | `crm.aria` | *your public IP* | **DNS only** (grey)   | Auto |

**The proxy status must be DNS only — the grey cloud, not the orange one.**
This is the setting that quietly breaks everything if it is wrong, and the
failure does not look like a DNS failure:

- Cloudflare's default SSL mode is **Flexible**, which speaks plain HTTP to
  your server while telling the browser the connection is secure. Caddy
  redirects that HTTP to HTTPS, Cloudflare follows it back to itself, and the
  browser gets `ERR_TOO_MANY_REDIRECTS` on a stack that is working perfectly.
- With the orange cloud on, Cloudflare answers the Let's Encrypt HTTP-01
  challenge itself instead of passing it to Caddy, so **no certificate is
  ever issued** and Caddy retries until it hits the rate limit.

Grey cloud means Cloudflare is a nameserver and nothing else: the request
reaches Caddy directly, Caddy gets a real certificate from Let's Encrypt, and
renewal happens on its own forever.

The trade is that your origin IP is public and you get no Cloudflare DDoS
shield. For this project that is the right trade — it works today with zero
configuration and no failure modes hidden behind someone else's proxy.

*If you later want the orange cloud on*: set **SSL/TLS → Overview → Full
(strict)** first (never Flexible), and switch Caddy to the DNS-01 challenge,
which needs a Cloudflare API token and a Caddy image built with the
`caddy-dns/cloudflare` plugin. Do not do this before the stack is up and
working — debugging two TLS terminators at once is miserable.

Note that `crm.aria.aroice.in` is a second-level subdomain, which Cloudflare's
free universal certificate does **not** cover (it covers `*.aroice.in`, one
level only). That costs nothing while the proxy is off, because Caddy issues
its own certificate directly from Let's Encrypt. It only becomes a problem if
the orange cloud is ever switched on for that record.

Check it resolves before going further. Caddy cannot get a certificate for a
name that does not point here yet:

```bash
dig +short aria.aroice.in
dig +short crm.aria.aroice.in
```

Both must print your Oracle public IP. If they print Cloudflare addresses
(104.x, 172.67.x), the proxy is still on — set both records to DNS only.

---

## Deploy

SSH in as `ubuntu`, then:

```bash
curl -fsSL https://raw.githubusercontent.com/Aryan-Techie/aria/main/deploy/bootstrap.sh | bash
```

That installs Docker, opens 80/443 on the instance firewall, and clones the
repo to `~/aria`. Log out and back in once, so the `docker` group applies.

Then fill in the environment — by hand, because it holds every secret:

```bash
cd ~/aria
cp deploy/.env.production.example deploy/.env.production
nano deploy/.env.production
```

Generate the passwords rather than inventing them:

```bash
openssl rand -base64 24
```

**`ESPOCRM_ADMIN_PASSWORD` must not be the local demo password.** That login
is on the public internet the moment `crm.aria.aroice.in` resolves.

Copy the model, voice and Agora keys across from your local `backend/.env` —
same names, same values. Leave `ESPOCRM_API_KEY` and
`ESPOCRM_ASSIGNED_USER_ID` blank for now; they do not exist yet.

Then:

```bash
bash deploy/up.sh
```

First run builds both images and waits for EspoCRM to install itself, which
takes a couple of minutes on one OCPU.

### Provision the CRM

Run on the **host**, not in a container — it installs Espo layouts with
`docker cp` and so needs the Docker socket:

```bash
cd ~/aria
set -a; . deploy/.env.production; set +a
ESPOCRM_BASE_URL=http://localhost:8080 python3 scripts/provision_crm.py
```

This creates the Lead custom fields, the `CAriaProduct` stock entity and its
layouts, the role, the rep user and the API user — idempotently, so it is safe
to re-run. It prints two values. Put both into `deploy/.env.production`:

```
ESPOCRM_API_KEY=...
ESPOCRM_ASSIGNED_USER_ID=...
```

EspoCRM returns the API key **only** in the response that creates the user, so
if you lose it, re-run with `--recreate` to mint a new one.

Restart the backend to pick them up:

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.production up -d backend
```

### Check it

```bash
curl -fsS https://aria.aroice.in/healthz
```

Then open `https://aria.aroice.in` for the console and
`https://crm.aria.aroice.in` for the CRM, and confirm **Products** lists
four rows with stock, price and lead time.

---

## Updating

```bash
cd ~/aria && git pull && bash deploy/up.sh
```

A change to `ARIA_DOMAIN` needs a **frontend rebuild**, not just a restart:
`NEXT_PUBLIC_BACKEND_URL` is inlined into the client bundle at build time.
`up.sh` always passes `--build`, so this is handled.

## When something is wrong

```bash
# what is actually running
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.production ps

# logs, one service at a time
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.production logs -f backend
```

**The site hangs instead of refusing the connection** — the instance firewall,
not the VCN. Run `sudo iptables -L INPUT -n --line-numbers` and check 80/443
are accepted. `bootstrap.sh` does this, but a reboot without
`iptables-persistent` installed loses it.

**Caddy will not issue a certificate** — the DNS record does not point here
yet, or port 80 is closed. Let's Encrypt validates over 80 before it will
issue for 443. `docker compose ... logs caddy` says which.

**EspoCRM returns 500 "No database params in config"** — the webroot got
mounted whole. Only `data`, `custom` and `client/custom` may be persisted; an
empty volume over `/var/www/html` shadows the shipped application and the
entrypoint bails with "LEGACY INSTALLATION METHOD DETECTED".

**The console loads but cannot reach the API** — the frontend was built with
the wrong `NEXT_PUBLIC_BACKEND_URL`. Rebuild it: it is baked in, not read at
runtime.

---

## One OCPU is the constraint, and you have three more free

The instance is running 1 OCPU / 6 GB. Oracle's Always Free ARM allowance is
**4 OCPU and 24 GB** across all A1 instances, so three quarters of what you
are entitled to is sitting unused while EspoCRM, MariaDB, a PHP daemon, a
websocket server, FastAPI and Next.js share a single core.

Raising it costs nothing: **Instances → aria-server → Edit → Edit shape**,
set OCPUs to 4 and memory to 24 GB. It needs a reboot, and builds and first
page loads get dramatically faster.

---

## The APK

Build it **after** the stack is live, not before. `EXPO_PUBLIC_API_BASE` is
inlined into the JS bundle at build time, so an APK built against a dead
hostname makes whoever installs it open Settings and paste a URL before
anything works. `mobile/eas.json`'s `preview` profile already carries
`https://aria.aroice.in`, so a build made now points at the real server and
works on first launch.

```bash
cd mobile
npx eas login          # interactive, once
npx eas build -p android --profile preview
```

EAS builds it in the cloud, handles the signing keystore, and hands back a
download URL when it finishes.

It does **not** go in the repo tree. The debug build is 477 MB and even a
release build with ABI splits is tens of megabytes — a binary that size in git
is paid for by every clone, forever, and GitHub rejects anything over 100 MB
outright. Attach it to a **Release** instead, which is repo-hosted, gives a
clean download link, and stays out of the history:

```bash
gh release create v1.0.0 ./aria-1.0.0.apk \
  --title "Aria 1.0.0" \
  --notes "Android app. Points at https://aria.aroice.in by default; the server address can be changed in Settings."
```

Without the `gh` CLI, do the same thing in the browser: **repo → Releases →
Draft a new release → Attach binaries**.
