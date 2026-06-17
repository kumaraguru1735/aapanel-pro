# Encrypted / Compiled Files Audit

## 1. `class/PluginLoader.*.so` — Core Encrypted Plugin Engine (Most Significant)

7 compiled `.so` shared libraries for different architectures and Python versions:

| File | Arch | Python |
|------|------|--------|
| `PluginLoader.x86_64.Python3.12.so` | x86_64 | 3.12 |
| `PluginLoader.x86_64.Python3.7.so` | x86_64 | 3.7 |
| `PluginLoader.x86_64.glibc214.Python3.7.so` | x86_64 (glibc 2.14) | 3.7 |
| `PluginLoader.aarch64.Python3.12.so` | aarch64 | 3.12 |
| `PluginLoader.aarch64.Python3.7.so` | aarch64 | 3.7 |
| `PluginLoader.i686.Python3.7.so` | i686 | 3.7 |
| `PluginLoader.loongarch64.Python3.7.so` | loongarch64 | 3.7 |

**Internal symbols (from `strings`):**
- `_aes_encrypt_module` / `_aes_decrypt_module` — encrypts/decrypts plugin files
- `_check_auth` / `_check_plugin_auth` — license/auth validation
- `db_aes_encrypt` / `db_aes_decrypt` — database-level AES ops
- `auth_mac_sgin` — MAC-based signing
- `_get_sgin_key` / `get_aes_key` — key derivation

**Used via:** `import PluginLoader` in:
- `class/ftplog.py` — pro membership check
- `class/files.py` — tamper-proof plugin
- `class/panelController.py` — module runner
- `class/panelProjectController.py` — module runner
- `class/push/site_push.py` — syslog module
- `BTTask/task.py` — task runner

This is the DRM layer for paid plugins. Paid plugin files are AES-encrypted and can only be decrypted at runtime by this loader after auth validation.

---

## 2. `data/public.key` — RSA Public Key

```
-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDPgc1kwCIBUBR5oy37oR+ju/4N
TUaABHpMpxRu8CocShXz8eQbwYY6iNJk2/qSTkg53Jm9E1djiN2UWyDhmn7FTKTY
zHr+8gqLGorBg0rpK45LWiWtjw9kCyhvHFThs2MoQEQwVR2w72AInrpOp12KuEB8
2TvZuavkxIfQTK779QIDAQAB
-----END PUBLIC KEY-----
```

2048-bit RSA public key used for verifying plugin/license signatures from the aaPanel server.

---

## 3. `class/panelAes.py` — AES Utility (Plain Python, Not Encrypted)

Implements AES-ECB and AES-CBC encryption with three class variants (`aescrypt_py2`, `aescrypt_py3`, `AesCryptPy3`).

**Used for:**
- API form data encryption — `class/common.py:388`, `class_v2/common_v2.py:273`
- SSL private key storage — `class/ssl_manage.py:453`, `class/sslModel/certModel.py:1304`
- SSH terminal session data — `class/ssh_terminal.py:973,1072,1078`

---

## 4. Long Base64 Blobs in `class/filesModel/*.py`

Files containing long single-line base64 strings (>100 chars):
- `uploadModel.py`
- `sizeModel.py`
- `searchModel.py`
- `gzModel.py`
- `downModel.py`
- `rarModel.py`
- `zipModel.py`
- `logsModel.py`
- `class/logsModel/ftpModel.py`
- `class/monitorModel/process_managementModel.py`

These are embedded binary data (file magic bytes, templates, icons) — **not encrypted code**.

---

## 5. `plugin/` Directory — Empty

No encrypted plugin `.main` files present currently. When paid plugins are installed, their encrypted binaries would live here and be decrypted at runtime by `PluginLoader.so`.

---

## Summary

| Component | Type | Encrypted? |
|-----------|------|------------|
| `class/PluginLoader.*.so` | Compiled C++ binary | Yes — closed-source DRM |
| `data/public.key` | RSA key file | N/A (public key) |
| `class/panelAes.py` | Python source | No — plain text |
| `class/filesModel/*.py` base64 blobs | Embedded binary data | No — not code |
| `plugin/` | Plugin dir | Empty (no plugins installed) |

**Only truly encrypted/opaque components:** `PluginLoader.*.so` binaries (closed-source) and the RSA `public.key`. All panel source code is plain readable Python.
