# Deploying CHAOS OS

This puts CHAOS OS on a cloud server, online 24/7 at an HTTPS address with a
login. One command does the setup (Ansible); re-running it updates the server.

```
internet ──HTTPS──► Caddy (login, certificates) ──► dashboard
                                              └──► /grafana
       everything else (API, Redis, Postgres, Toxiproxy, Prometheus) stays private
```

Jenkins is **not** deployed: CI keeps running on your laptop. The dashboard can
run experiments and spend the OpenAI key, so it is never served without a login.

Two ways to put it online:

| | Share from your laptop | Your own server |
|---|---|---|
| Needs | Docker Desktop, `deploy/secrets.yml` | A cloud VM (usually a card or student credit) |
| Address | random `https://<words>.trycloudflare.com`, new each time | fixed `https://<ip>.sslip.io` or your domain |
| Online | while your laptop is awake | 24/7 |
| Command | `.\deploy\share.ps1` | `.\deploy\deploy.ps1 -Server <ip>` |

## Share from your laptop (no server, account or card)

1. Fill in the secrets (section 2 below). Only the two passwords are needed.
2. With Docker Desktop running:
   ```powershell
   .\deploy\share.ps1
   ```
   It ends with `CHAOS OS is shared at https://<words>.trycloudflare.com`. Send
   that link and the login to whoever should see it.
3. When you are done: `.\deploy\share.ps1 -Stop` (back to the normal local lab).

The lab runs on Docker Desktop as usual, now with the history you already
have and the OpenAI key from your local `.env`. A free Cloudflare quick tunnel
dials out to Cloudflare, so no router or firewall port is opened. Keep the
laptop plugged in with sleep off during a demo. If the link stops working, run
the command again to get a new one.

## No card for a server?

- **Azure for Students:** $100 credit, verified with your college email and no
  card (https://azure.microsoft.com/free/students). Create an Ubuntu 24.04 VM
  of size `B2s` (4 GB) or larger, allow inbound SSH, HTTP and HTTPS, then use the
  same deploy with Azure's user name:
  `.\deploy\deploy.ps1 -Server <ip> -User azureuser`. Stop the VM when you
  don't need it to make the credit last.
- **Oracle Cloud** (below) often accepts a Visa or Mastercard *debit* card with
  online/international payments switched on. It is only used for verification.

## 1. Create a free server (Oracle Cloud, about 15 minutes)

1. **SSH key** (once, on your laptop, in PowerShell). Press Enter at every question:
   ```powershell
   ssh-keygen -t ed25519
   Get-Content $HOME\.ssh\id_ed25519.pub   # copy this line for step 3
   ```
2. **Account:** sign up at https://cloud.oracle.com ("Always Free"). A card is
   asked for verification; Always Free resources are not charged.
3. **Server:** Menu → Compute → Instances → **Create instance**:
   - **Image:** Canonical Ubuntu 24.04 (pick the *aarch64* build)
   - **Shape:** Ampere → `VM.Standard.A1.Flex`, **4 OCPU, 24 GB** (Always Free)
   - **Networking:** keep the default public subnet; *Assign a public IPv4 address* = yes
   - **SSH keys:** *Paste public keys* → paste the line from step 1
   - Create, wait until it says **Running**, copy the **Public IP address**.

   *"Out of capacity"?* Try another availability domain, or 2 OCPU / 12 GB, or
   retry later; Ampere capacity comes and goes.
4. **Open ports 80 and 443:** on the instance page → the subnet link →
   **Default Security List** → **Add Ingress Rules**, twice:
   source `0.0.0.0/0`, protocol TCP, destination port `80`, then `443`.
5. **Check SSH works:** `ssh ubuntu@<public-ip>` → type `yes`, then `exit`.

Other clouds work the same way: any Ubuntu 22.04/24.04 server with 4 GB+ RAM,
your SSH key, and ports 22/80/443 open (for example DigitalOcean, free credit
with the GitHub Student Developer Pack).

## 2. Fill in the secrets

```powershell
Copy-Item deploy\secrets.example.yml deploy\secrets.yml
code deploy\secrets.yml
```

Set a long `dashboard_password` and `grafana_password` (12+ characters; the
deploy refuses placeholders). Add `openai_api_key` only after setting a monthly
spending limit on it. `deploy/secrets.yml` is git-ignored.

## 3. (Optional) Bring your experiment results

Without this the server starts with an empty history. To copy your local
results (all trials and the trained bandit):

```powershell
New-Item -ItemType Directory -Force deploy\seed | Out-Null
docker run --rm -v chaosos_results:/results -v "${PWD}\deploy\seed:/out" alpine:3.20 sh -c "cp /results/chaos.db /results/bandit.json /out/"
```

The deploy copies them over once and never overwrites newer server data.

## 4. Deploy

From the project folder, with Docker Desktop running:

```powershell
.\deploy\deploy.ps1 -Server <public-ip>
```

It opens the firewall, installs Docker, pulls the code from GitHub, writes the
secrets, starts everything and waits until HTTPS and the login work. The first
run takes about 10–15 minutes (it builds the images on the server). It ends with:

```
CHAOS OS is live at https://<public-ip>.sslip.io (log in as 'admin')
```

`sslip.io` is a free DNS name that points at your IP, so you get a real HTTPS
certificate without buying a domain. To use your own domain, point its DNS
A record at the server and set `domain:` in `secrets.yml`.

## Updating

Push changes to GitHub, then run the same command again. It pulls the latest
`main` and rebuilds only what changed.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `UNREACHABLE` / SSH timeout | Wrong IP, instance not running, or port 22 closed |
| `Permission denied (publickey)` | Use the key whose `.pub` you pasted: `-Key $HOME\.ssh\<name>` |
| Stuck at "Wait for HTTPS" | Ports 80/443 not open in the Security List (step 1.4) |
| Browser says "not secure" for a minute | The certificate is being issued; refresh |
| Need to look at the server | `ssh ubuntu@<ip>` then `cd /opt/chaos-os && sudo docker compose ps` |

## Security notes

- Only Caddy (ports 80/443) is reachable from the internet; everything else is
  on Docker's private network.
- Every page and API call needs the login, over HTTPS.
- The dashboard and controller can control Docker on the server (that is how
  they inject faults), so keep the password strong and private.
- Secrets live only in `deploy/secrets.yml` on your laptop and in
  `/opt/chaos-os/.env` (owner-only) on the server.
