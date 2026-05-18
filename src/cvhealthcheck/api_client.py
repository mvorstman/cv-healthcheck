from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import requests
from requests import Response, Session
from urllib3.exceptions import InsecureRequestWarning

from .auth import load_token
from .config import Settings, load_settings, warn_if_ssl_verification_disabled


class ConfigurationError(RuntimeError):
    pass


class ApiError(RuntimeError):
    pass


@dataclass
class ApiResult:
    ok: bool
    status_code: int | None
    url: str
    data: Any
    text: str
    error: str | None = None
    elapsed_seconds: float | None = None


class CommvaultApiClient:
    def __init__(
        self,
        settings: Settings | None = None,
        token: str | None = None,
        session: Session | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.token = token if token is not None else load_token(self.settings.token_path)
        self.session = session or requests.Session()

        if not self.settings.verify_ssl:
            warn_if_ssl_verification_disabled(self.settings, component=self.__class__.__name__)
            requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

    @property
    def token_loaded(self) -> bool:
        return bool(self.token)

    def _url(self, path: str) -> str:
        if not self.settings.base_url:
            raise ConfigurationError("CV_BASE_URL is not set")
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{self.settings.base_url}{normalized_path}"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authtoken"] = self.token
        return headers

    def get(self, path: str, params: dict[str, Any] | None = None) -> ApiResult:
        try:
            url = self._url(path)
        except ConfigurationError as exc:
            return ApiResult(
                ok=False,
                status_code=None,
                url=path,
                data=None,
                text="",
                error=str(exc),
            )

        try:
            started = perf_counter()
            response = self.session.get(
                url,
                headers=self._headers(),
                params=params,
                verify=self.settings.verify_ssl,
                timeout=self.settings.timeout_seconds,
            )
            elapsed_seconds = perf_counter() - started
        except requests.RequestException as exc:
            return ApiResult(
                ok=False,
                status_code=None,
                url=url,
                data=None,
                text="",
                error=str(exc),
            )

        return self._result_from_response(response, elapsed_seconds=elapsed_seconds)

    def ping(self) -> ApiResult:
        return self.get("/commandcenter/api")

    def _result_from_response(
        self,
        response: Response,
        elapsed_seconds: float | None = None,
    ) -> ApiResult:
        data: Any
        try:
            data = response.json()
        except ValueError:
            data = None

        return ApiResult(
            ok=response.ok,
            status_code=response.status_code,
            url=response.url,
            data=data,
            text=response.text,
            error=None if response.ok else response.text,
            elapsed_seconds=elapsed_seconds,
        )
