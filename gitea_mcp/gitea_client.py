import os
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlparse

import requests
from dotenv import load_dotenv

class GiteaClient:
    def __init__(self):
        load_dotenv(Path(__file__).with_name(".env"))
        self.gitea_url = os.getenv("GITEA_URL", "").strip().rstrip("/")
        self.owner = os.getenv("OWNER", "").strip()
        self.repository = os.getenv("REPO", "").strip()
        self._allowed_gitea_urls = set()
        if self.gitea_url:
            self._allowed_gitea_urls.add(
                self._base_url_identity(self.gitea_url, "GITEA_URL")
            )
        for allowed_url in os.getenv("GITEA_ALLOWED_URLS", "").split(","):
            allowed_url = allowed_url.strip()
            if allowed_url:
                self._allowed_gitea_urls.add(
                    self._base_url_identity(allowed_url, "GITEA_ALLOWED_URLS")
                )
        if not self._allowed_gitea_urls:
            raise ValueError("Set GITEA_URL or GITEA_ALLOWED_URLS")

        try:
            timeout = float(os.getenv("GITEA_TIMEOUT", "30"))
        except ValueError as error:
            raise ValueError("GITEA_TIMEOUT must be a positive number") from error
        if timeout <= 0:
            raise ValueError("GITEA_TIMEOUT must be a positive number")

        self.timeout = timeout
        self.read_only = os.getenv("GITEA_READ_ONLY", "").strip().lower() in {"1", "true", "yes"}
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
            }
        )

    @staticmethod
    def _origin(parsed_url):
        default_port = 443 if parsed_url.scheme.lower() == "https" else 80
        return (
            parsed_url.scheme.lower(),
            (parsed_url.hostname or "").lower(),
            parsed_url.port or default_port,
        )

    @classmethod
    def _base_url_identity(cls, url, setting_name):
        parsed_url = urlparse(url.strip().rstrip("/"))
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError(
                f"{setting_name} entries must be absolute HTTP or HTTPS base URLs"
            )
        try:
            origin = cls._origin(parsed_url)
        except ValueError as error:
            raise ValueError(f"{setting_name} contains an invalid port") from error
        return origin, parsed_url.path.rstrip("/")

    def request(
        self,
        method: str,
        endpoint: str = "",
        *,
        token: str,
        owner: str | None = None,
        reponame: str | None = None,
        url: str | None = None,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        response_format: Literal["json", "text"] = "json",
    ) -> Any:
        effective_url = (url if url is not None else self.gitea_url).strip().rstrip("/")
        effective_owner = (owner if owner is not None else self.owner).strip()
        effective_repository = (reponame if reponame is not None else self.repository).strip()
        effective_token = token.strip()
        missing = [
            name
            for name, value in (
                ("url (or GITEA_URL)", effective_url),
                ("owner (or OWNER)", effective_owner),
                ("reponame (or REPO)", effective_repository),
                ("Gitea token", effective_token),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing repository settings: {', '.join(missing)}")

        url_identity = self._base_url_identity(effective_url, "url")
        if url_identity not in self._allowed_gitea_urls:
            raise ValueError("url must match GITEA_URL or an entry in GITEA_ALLOWED_URLS")

        if endpoint and not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        base_url = (
            f"{effective_url}/api/v1/repos/"
            f"{quote(effective_owner, safe='')}/{quote(effective_repository, safe='')}"
        )
        response = self.session.request(
            method.upper(),
            f"{base_url}{endpoint}",
            params=params,
            json=body,
            timeout=self.timeout,
            headers={"Authorization": f"token {effective_token}"},
        )
        response.raise_for_status()
        if response_format == "text":
            return response.text
        if not response.content:
            return {"status": "success", "status_code": response.status_code}
        return response.json()

    def get(
        self,
        endpoint: str = "",
        *,
        token: str,
        owner: str | None = None,
        reponame: str | None = None,
        url: str | None = None,
        params: dict[str, Any] | None = None,
        response_format: Literal["json", "text"] = "json",
    ) -> Any:
        return self.request(
            "GET",
            endpoint,
            token=token,
            owner=owner,
            reponame=reponame,
            url=url,
            params=params,
            response_format=response_format,
        )