# aaPanel Pro — Fully Unlocked

All plugins unlocked, all Pro features enabled, no license checks. Works on fresh servers or existing aaPanel installs.

---

## Quick Install (New Server)

**Step 1 — Install aaPanel** (official installer, only needed once):
```bash
bash <(curl -s https://www.aapanel.com/script/install_7.0_en.sh)
```
> Note the panel URL, port, username and password shown at the end of install.

**Step 2 — Clone and patch:**
```bash
git clone https://github.com/kumaraguru1735/aapanel-pro.git
cd aapanel-pro
bash install.sh
```

**Step 3 — Install software (PHP, Nginx, MySQL, phpMyAdmin, Redis, FTP):**
```bash
bash post_install.sh --all
```

Done. Login to your panel — all plugins will show as Pro, no Buy buttons anywhere.

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

| Script | Purpose |
|--------|---------|
| `install.sh` | Applies all patches + copies plugin directories. Run after aaPanel is installed. |
| `patch.sh` | Smart patcher — finds JS patterns in any aaPanel version, applies fixes, restarts panel. |
| `post_install.sh` | Installs PHP 5.6–8.3, Nginx, MySQL 8.0, phpMyAdmin, Redis, Memcached, Pure-FTPd. |

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

## No External Dependencies

All scripts in this repo are self-contained. No calls to aaPanel/bt.cn servers:
- `public.sh` (shared install lib) is bundled locally
- Mail server config templates (dovecot/postfix/rspamd) bundled in `plugin/mail_sys/mail_conf/`
- PHP/Nginx/MySQL packages are installed from system package managers (apt/yum)
