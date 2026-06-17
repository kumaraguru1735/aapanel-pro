# aaPanel Pro — Fully Unlocked & Self-Contained

The **entire panel ships inside this repo** — application source, all Pro plugins,
the DRM bypass, and the installer. A brand-new server is provisioned end-to-end
from this clone alone. The panel itself never contacts aapanel.com; only the
Python runtime (PyPI) and — optionally — the compiled LAMP stack are fetched
externally.

All plugins unlocked, all Pro features enabled, no license checks. Works on fresh
servers or existing aaPanel installs.

---

## Quick Install (New Server)

One command installs everything — base panel, runtime, pro unlock, and all plugins:

```bash
git clone https://github.com/kumaraguru1735/aapanel-pro.git
cd aapanel-pro
sudo bash install.sh
```

`install.sh` performs the full bootstrap from the bundled source:
1. Installs OS build dependencies (apt/dnf/yum)
2. Deploys the panel from `panel/` → `/www/server/panel`
3. Builds the Python runtime at `/www/server/panel/pyenv` from `panel/requirements.txt` (via pip)
4. Initializes config — port, random security entrance, random admin password
5. Installs the `/etc/init.d/bt` service and the `bt` CLI
6. Applies the pro patches (`patch.sh`) and installs all plugins
7. Starts the panel and prints the login URL / credentials

**Then install the web stack (PHP, Nginx, MySQL, phpMyAdmin, Redis, FTP):**
```bash
bash post_install.sh --all
```

Done. Login to your panel — all plugins will show as Pro, no Buy buttons anywhere.

### Install flags

```bash
sudo bash install.sh --port 8888 --user admin --password 'MyPass123'
sudo bash install.sh --pyenv-cdn      # use aapanel.com prebuilt Python instead of pip build
sudo bash install.sh --no-stack       # skip the LAMP-stack hint at the end
```

> **Python runtime note:** by default the runtime is built locally from the
> pinned `requirements.txt` using the system `python3` + pip — fully independent
> of aapanel.com. If a pinned wheel fails to build on your distro's Python, the
> installer automatically falls back to aapanel.com's prebuilt runtime. Force the
> prebuilt path with `--pyenv-cdn`.

---

## Patch Existing aaPanel

If you already have aaPanel installed and just need to apply the pro unlock:

```bash
git clone https://github.com/kumaraguru1735/aapanel-pro.git
cd aapanel-pro
bash patch.sh
```

---

## What Each Script Does

| Path | Purpose |
|--------|---------|
| `install.sh` | Full offline bootstrap — deploys the bundled panel, builds the runtime, initializes config, applies patches, installs plugins, starts the panel. |
| `patch.sh` | Smart patcher — finds JS patterns in any aaPanel version, applies fixes, restarts panel. Run standalone to patch an already-installed panel. |
| `post_install.sh` | Installs PHP 5.6–8.3, Nginx, MySQL 8.0, phpMyAdmin, Redis, Memcached, Pure-FTPd. |
| `panel/` | **Complete aaPanel application source** (the base install files) — `BTPanel/`, `class/`, `class_v2/`, `data/`, `init.sh`, `requirements.txt`, etc. |
| `plugin/` | All 20 Pro plugins, full source. |
| `patches/` | DRM-bypass `PluginLoader.py` + pre-patched frontend JS (fallback overlays). |
| `so/` | Original `PluginLoader` `.so` binaries for every architecture/Python combo. |

---

## What Gets Patched

### Backend — `patches/PluginLoader.py`
Python mock that replaces the `.so` DRM library. On every plugin list request:
- Sets `endtime` to year 2097 for all plugins with negative endtime
- Sets `pro = ltd = 2097...` on the list response
- Sets `status = True`
- Delegates all other calls (module loading, AES crypto) to the real `.so`

### Frontend — `patches/js/`

| File | What it patches |
|------|----------------|
| `index-CmkLJhc0.js` | `Rd=e=>!1` — disables "Buy now" indicator in App Store for all plugins |
| `index-Bwt6bvOM.js` | WAF install page always shows **Install** button, not "Buy now" |

### Plugins — `plugin/`
All 20 plugin directories pre-installed:
`bt_security`, `btapp`, `btwaf`, `btwaf_httpd`, `dns_manager`, `fail2ban`, `jumpserver`, `load_balance`, `mail_sys`, `monitor`, `mysql_replicate`, `nodejs`, `redis`, `rsync`, `ssl_verify`, `syssafe`, `tamper_core`, `tamper_proof`, `task_manager`, `total`

### PluginLoader `.so` files — `so/`
Original `.so` binaries for all architectures (used by the Python mock to delegate real calls):

| File | Architecture |
|------|-------------|
| `PluginLoader.x86_64.Python3.12.so` | x86_64, Python 3.12 |
| `PluginLoader.x86_64.Python3.7.so` | x86_64, Python 3.7 |
| `PluginLoader.x86_64.glibc214.Python3.7.so` | x86_64, old glibc |
| `PluginLoader.aarch64.Python3.12.so` | ARM64, Python 3.12 |
| `PluginLoader.aarch64.Python3.7.so` | ARM64, Python 3.7 |
| `PluginLoader.i686.Python3.7.so` | 32-bit x86 |
| `PluginLoader.loongarch64.Python3.7.so` | LoongArch64 |

---

## post_install.sh Options

```bash
bash post_install.sh --all      # Everything: PHP 5.6–8.3 + Nginx + MySQL + phpMyAdmin + Redis + FTP
bash post_install.sh --stack    # Core stack: Nginx + MySQL + PHP 5.6–8.3 + phpMyAdmin + Redis
bash post_install.sh --php      # PHP versions only (5.6, 7.0, 7.1, 7.2, 7.3, 7.4, 8.0, 8.1, 8.2, 8.3)
bash post_install.sh --nginx    # Nginx only
bash post_install.sh --mysql    # MySQL 8.0 only
bash post_install.sh --pma      # phpMyAdmin only
bash post_install.sh --redis    # Redis only
bash post_install.sh --plugins  # Run install.sh for each plugin directory
```

---

## WAF (Web Application Firewall)

WAF requires installation before use. After patching:

1. Go to **App Store → Security → aaPanel WAF**
2. Click **Install** (not "Buy" — the patch removes the buy gate)
3. After install completes, WAF overview becomes accessible

The WAF router guard is kept at its original logic:
- Not installed → shows WAF install page with **Install** button
- Installed → goes directly to WAF overview
- `isBuy` is always `true` from the endtime patch, so "Install" is shown instead of "Buy"

---

## How the DRM Bypass Works

aaPanel Pro checks plugin licenses through `PluginLoader.so`. This binary:
1. Contacts aaPanel auth servers to validate the license key
2. Returns `endtime = -1` for unlicensed plugins

Our `PluginLoader.py` is loaded instead (Python searches `class/` for `.py` before `.so`):
1. Loads the original `.so` as `PluginLoader_real.so` (for non-auth calls)
2. Intercepts `get_plugin_list()` and patches `endtime` from `-1` to `2097028838` (10 years)
3. The frontend sees `endtime >= 0` → `isBuy = true` → no license prompts

---

## Supported OS

| OS | Versions |
|----|---------|
| Ubuntu | 20.04, 22.04, 24.04 |
| Debian | 10, 11, 12 |
| CentOS | 7, 8 |
| AlmaLinux / Rocky | 8, 9 |

Architectures: x86_64, aarch64 (ARM64)

---

## Zero CDN — Serve Everything From Your Own Mirror

No script in this repo downloads from aapanel.com or bt.cn. Every external
artifact (compiled PHP/Nginx/MySQL, the Python runtime, Python wheels) is fetched
from **a local mirror that you control**, configured in `mirror.conf`:

```ini
BT_MIRROR="http://10.0.0.5:5050"   # your mirror server
```

`install.sh`, the panel's runtime software-installer (`install_soft.sh`),
`public.sh`, and the pyenv fallback all read this single value.

### One-time setup of the mirror

Run on any internet-connected machine (can be the mirror server itself). This is
the **only** step that ever touches a CDN — once, to fill your mirror:

```bash
bash mirror-pull.sh        # downloads soft-install scripts, source tarballs,
                           # prebuilt pyenv, and Python wheels into ./mirror
```

Then serve it (on your mirror server) and point installs at it:

```bash
bash mirror-serve.sh 5050               # serves ./mirror on :5050 (python http.server)
# edit mirror.conf -> BT_MIRROR="http://<mirror-ip>:5050"
sudo bash install.sh                    # installs entirely from your mirror, no CDN
```

You can also serve `./mirror` with nginx/apache instead of `mirror-serve.sh` —
just match the URL in `BT_MIRROR`.

> **Why a mirror and not git?** aaPanel's compiled software (PHP 5.6–8.3, Nginx,
> MySQL, …) is gigabytes of per-distro/per-arch binaries and the Python runtime is
> ~700 MB — far too large to commit to git. Mirroring them once to your own server
> gives you a permanent, CDN-independent source you fully control.
>
> A few soft-install scripts compute tarball filenames at runtime. If an install
> 404s against your mirror, copy that exact path into `mirror/` and re-serve —
> `mirror-pull.sh` prints any URLs it couldn't pre-fetch.

### Fully local (no PyPI either)

`mirror-pull.sh` also downloads all Python wheels into `mirror/pip`. When that
folder is present, `install.sh` builds the runtime with `pip --no-index`, so even
the Python packages come from your mirror, not PyPI.

---

## What ships in the repo vs. the mirror

| Local in repo (git) | From your mirror (one-time pull) |
|---------------------|----------------------------------|
| Full panel application source (`panel/`) | Compiled PHP / Nginx / MySQL / Redis / phpMyAdmin / FTP |
| All 20 Pro plugins (`plugin/`) | Prebuilt Python runtime (`pyenv`) — optional, pip build is default |
| DRM bypass + patched JS (`patches/`, `so/`) | Python wheels (`mirror/pip`) — optional, makes runtime PyPI-free |
| Mail config templates, `public.sh`, installers | — |
