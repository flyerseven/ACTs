from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

try:
    import keyring
except Exception:  # pragma: no cover
    keyring = None


@dataclass
class VaultEntry:
    alias: str
    value: str


class Vault:
    def __init__(self, vault_path: Path, service_name: str = "ACTs", use_keyring: bool | None = None) -> None:
        self.vault_path = vault_path
        self.service_name = service_name
        self.use_keyring = True if use_keyring is None else use_keyring
        self._data: dict[str, str] = {}
        self._key = self._load_master_key()

    def _load_master_key(self) -> bytes:
        if self.use_keyring and keyring is not None:
            try:
                stored = keyring.get_password(self.service_name, "master_key")
                if stored:
                    return base64.b64decode(stored.encode("ascii"))
                key = os.urandom(32)
                keyring.set_password(self.service_name, "master_key", base64.b64encode(key).decode("ascii"))
                return key
            except Exception:
                pass

        key_path = self.vault_path.with_suffix(".key")
        if key_path.exists():
            return base64.b64decode(key_path.read_text(encoding="utf-8"))
        key = os.urandom(32)
        key_path.write_text(base64.b64encode(key).decode("ascii"), encoding="utf-8")
        return key

    def load(self) -> None:
        if not self.vault_path.exists():
            self._data = {}
            return
        payload = json.loads(self.vault_path.read_text(encoding="utf-8"))
        token = payload.get("data", "")
        if not token:
            self._data = {}
            return
        raw = self._decrypt(token)
        self._data = json.loads(raw.decode("utf-8"))

    def save(self) -> None:
        raw = json.dumps(self._data, ensure_ascii=True).encode("utf-8")
        token = self._encrypt(raw)
        payload = {"version": 1, "data": token}
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self.vault_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    def list_keys(self) -> list[VaultEntry]:
        return [VaultEntry(alias=k, value=v) for k, v in sorted(self._data.items())]

    def set_key(self, alias: str, value: str) -> None:
        self._data[alias] = value
        self.save()

    def delete_key(self, alias: str) -> None:
        if alias in self._data:
            del self._data[alias]
            self.save()

    def resolve_key_ref(self, ref: str) -> str:
        if not ref:
            return ""
        if ref.startswith("vault:"):
            alias = ref.split(":", 1)[1]
            return self._data.get(alias, "")
        return ref

    def _encrypt(self, raw: bytes) -> str:
        nonce = os.urandom(12)
        cipher = AESGCM(self._key)
        encrypted = cipher.encrypt(nonce, raw, None)
        return base64.b64encode(nonce + encrypted).decode("ascii")

    def _decrypt(self, token: str) -> bytes:
        data = base64.b64decode(token.encode("ascii"))
        nonce, encrypted = data[:12], data[12:]
        cipher = AESGCM(self._key)
        return cipher.decrypt(nonce, encrypted, None)
