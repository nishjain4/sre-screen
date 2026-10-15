"""Shared helpers for repository-scoped Gitea tools."""

from typing import Any, Literal
from urllib.parse import quote

from fastmcp.server.dependencies import get_http_headers

from gitea_client import GiteaClient


def request(
    client: GiteaClient,
    method: str,
    endpoint: str,
    *,
    owner: str | None = None,
    reponame: str | None = None,
    url: str | None = None,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    response_format: Literal["json", "text"] = "json",
) -> Any:
    headers = get_http_headers()

    def header_value(name: str) -> str | None:
        value = next(
            (value.strip() for key, value in headers.items() if key.casefold() == name.casefold()),
            "",
        )
        return value or None

    token = next(
        (value.strip() for key, value in headers.items() if key.lower() == "gitea-token"),
        "",
    )
    if not token:
        raise ValueError("Missing required HTTP header: Gitea-Token")

    effective_owner = owner if owner is not None else header_value("Gitea-Owner")
    effective_repository = reponame if reponame is not None else header_value("Gitea-Repo")
    effective_url = url if url is not None else header_value("Gitea-URL")

    return client.request(
        method,
        endpoint,
        token=token,
        owner=effective_owner,
        reponame=effective_repository,
        url=effective_url,
        params=params,
        body=body,
        response_format=response_format,
    )


def provided(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def path_segment(value: str, *, allow_slashes: bool = False) -> str:
    return quote(value, safe="/" if allow_slashes else "")


def require_confirmation(confirmed: bool, operation: str) -> None:
    if not confirmed:
        raise ValueError(f"Set confirm=True to {operation}")