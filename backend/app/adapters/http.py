"""Small HTTP helpers with a stdlib fallback for local refresh jobs."""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class HttpStatusError(RuntimeError):
    def __init__(self, status_code: int, body: str):
        super().__init__(f"HTTP {status_code}: {body[:200]}")
        self.status_code = status_code


def get_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 30):
    return json.loads(get_text(url, params=params, headers=headers, timeout=timeout))


def get_text(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: int = 30) -> str:
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(url, headers=headers or {})
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HttpStatusError(exc.code, body) from exc
    if status >= 400:
        raise HttpStatusError(status, body)
    return body
