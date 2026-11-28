from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Principal:
    tenant: str
    user: str


class Access:
    cookie = "agent_session"

    def __init__(self):
        self.tokens: dict[bytes, Principal] = {}
        self.sessions: dict[bytes, tuple[Principal, float]] = {}
        self.lock = threading.Lock()
        self.origin = ""
        self.session_seconds = 3600

    def configure(self, path: str, workspace: Path) -> None:
        if not path:
            raise ValueError("Chat requires AGENT_CHAT_AUTH_CONFIG")
        source = Path(path).resolve()
        if source == workspace or workspace in source.parents:
            raise ValueError("Chat authentication configuration must be outside the workspace")
        config = json.loads(source.read_text(encoding="utf-8"))
        if (not isinstance(config, dict) or set(config) - {"tenant", "users", "origin", "session_seconds"}
                or not {"tenant", "users", "origin"} <= set(config)):
            raise ValueError("Invalid chat authentication configuration")
        tenant, users, origin = config["tenant"], config["users"], config["origin"]
        identity = r"[A-Za-z0-9_-]{1,64}"
        if not isinstance(tenant, str) or not re.fullmatch(identity, tenant):
            raise ValueError("Invalid tenant identity")
        if not isinstance(users, dict) or not users:
            raise ValueError("Chat requires configured users")
        if not isinstance(origin, str):
            raise ValueError("Invalid chat origin")
        parsed = urlsplit(origin)
        if (parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
                or origin != f"{parsed.scheme}://{parsed.netloc}"
                or (parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"})):
            raise ValueError("Chat origin requires HTTPS or loopback HTTP, without a path")
        parsed.port
        seconds = config.get("session_seconds", 3600)
        if type(seconds) is not int or not 60 <= seconds <= 86400:
            raise ValueError("Invalid chat session lifetime")
        tokens = {}
        for user, spec in users.items():
            if (not isinstance(user, str) or not re.fullmatch(identity, user)
                    or not isinstance(spec, dict) or set(spec) != {"token_env"}
                    or not isinstance(spec["token_env"], str)
                    or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", spec["token_env"])):
                raise ValueError("Invalid chat user configuration")
            token = os.environ.get(spec["token_env"], "")
            if not 32 <= len(token) <= 512 or any(not 33 <= ord(c) <= 126 for c in token):
                raise ValueError("Chat access tokens must contain 32 to 512 visible ASCII characters")
            key = self.digest(token)
            if key in tokens:
                raise ValueError("Chat users must have distinct access tokens")
            tokens[key] = Principal(tenant, user)
        with self.lock:
            self.tokens = tokens
            self.sessions.clear()
            self.origin = origin
            self.session_seconds = seconds

    @staticmethod
    def digest(token: str) -> bytes:
        return hashlib.sha256(token.encode("utf-8")).digest()

    def principal(self, key: bytes, browser: bool) -> Principal | None:
        with self.lock:
            if not browser:
                return self.tokens.get(key)
            row = self.sessions.get(key)
            if row and row[1] > time.monotonic():
                return row[0]
            self.sessions.pop(key, None)
            return None

    def authenticate(self, authorization: str | None, cookie: str | None):
        if authorization is not None:
            parts = authorization.split(" ")
            if len(parts) != 2 or parts[0].lower() != "bearer" or not 32 <= len(parts[1]) <= 512:
                return None
            key, browser = self.digest(parts[1]), False
        elif cookie and 32 <= len(cookie) <= 512:
            key, browser = self.digest(cookie), True
        else:
            return None
        principal = self.principal(key, browser)
        return (principal, key, browser) if principal else None

    def login(self, token: str) -> str | None:
        if not 32 <= len(token) <= 512:
            return None
        with self.lock:
            principal = self.tokens.get(self.digest(token))
            if not principal:
                return None
            now = time.monotonic()
            self.sessions = {key: row for key, row in self.sessions.items() if row[1] > now}
            owned = [key for key, row in self.sessions.items() if row[0] == principal]
            if len(owned) >= 8:
                self.sessions.pop(owned[0])
            session = secrets.token_urlsafe(32)
            self.sessions[self.digest(session)] = (principal, now + self.session_seconds)
            return session

    def logout(self, cookie: str | None) -> None:
        if cookie:
            with self.lock:
                self.sessions.pop(self.digest(cookie), None)

    def close(self):
        with self.lock:
            self.tokens.clear()
            self.sessions.clear()
            self.origin = ""
