# 003: Vault-Based API Key Management

**Date:** 2025 (Phase 1 MVP)

**Status:** Accepted

## Context

Users must provide their own LLM API keys. These keys must be:
- Stored securely (encrypted at rest)
- Referenced indirectly in configuration files (so configs can be shared without exposing keys)
- Managed through a simple UI

## Decision

Use an **AES-256-GCM encrypted vault** with **key references** (`vault:<alias>`):

1. Master key stored in OS keyring (via `keyring`), with `.key` file fallback
2. All API keys encrypted in `.vault.enc`
3. Config files store `vault:<alias>` references instead of raw keys
4. `Vault.resolve_key_ref()` resolves references at load time

## Rationale

- **Separation of concerns**: Configs (YAML) are portable; secrets (vault) stay local
- **Industry standard**: AES-256-GCM is authenticated encryption, preventing tampering
- **OS integration**: Keyring uses platform-native secure storage (Windows Credential Manager, macOS Keychain, Linux Secret Service)
- **Fallback chain**: If keyring fails, falls back to local `.key` file

## Key Reference Format

```yaml
# Agent YAML — safe to share/version-control
model:
  provider: openai
  api_key_ref: vault:openai_prod  # ← reference, not raw key
```

## Encryption Details

- **Algorithm**: AES-256-GCM (via `cryptography` library)
- **Nonce**: 12 random bytes per encryption
- **Format**: `base64(nonce + ciphertext)`
- **Key derivation**: Random 32-byte key, stored via keyring or `.key` file

## Consequences

- If the OS keyring is unavailable and the `.key` file is lost, vault data is irrecoverable
- `keyring` is an optional dependency (caught at import time)
- Vault must be explicitly `load()`ed and `save()`d; changes are immediately persisted on `set_key()`
