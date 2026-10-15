"""Tools for repository files and Git trees."""

import base64
from typing import Any

from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.common import path_segment, provided, request, require_confirmation


def _file_endpoint(filepath: str, *, allow_root: bool = False) -> str:
    normalized = filepath.replace("\\", "/").strip("/")
    if not normalized and allow_root:
        return "/contents"
    if not normalized or any(part in {".", ".."} for part in normalized.split("/")):
        raise ValueError("filepath must be a repository-relative path")
    return f"/contents/{path_segment(normalized, allow_slashes=True)}"


def register_file_tools(mcp: FastMCP, client: GiteaClient) -> None:
    @mcp.tool()
    def get_file_content(filepath: str = "", ref: str | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> Any:
        """Read file metadata and Base64 content, or list a directory."""
        return request(client, "GET", _file_endpoint(filepath, allow_root=True), owner=owner, reponame=reponame, url=url, params=provided(ref=ref))

    @mcp.tool()
    def list_git_tree(sha: str, recursive: bool = False, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """List Git tree entries by SHA; recursive output is bounded by Gitea."""
        params = {"recursive": "true"} if recursive else None
        return request(client, "GET", f"/git/trees/{path_segment(sha)}", owner=owner, reponame=reponame, url=url, params=params)

    @mcp.tool()
    def get_raw_file(filepath: str, ref: str | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> str:
        """Download raw file text at an optional branch, tag, or commit ref."""
        _file_endpoint(filepath)
        raw_path = path_segment(filepath.replace("\\", "/").strip("/"), allow_slashes=True)
        return request(client, "GET", f"/raw/{raw_path}", owner=owner, reponame=reponame, url=url, params=provided(ref=ref), response_format="text")

    @mcp.tool()
    def create_file(filepath: str, content: str, message: str, branch: str | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Create a file from UTF-8 text and commit it to a branch."""
        body = {"content": base64.b64encode(content.encode("utf-8")).decode("ascii"), "message": message, **provided(branch=branch)}
        return request(client, "POST", _file_endpoint(filepath), owner=owner, reponame=reponame, url=url, body=body)

    @mcp.tool()
    def update_file(filepath: str, content: str, sha: str, message: str, branch: str | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Update a file from UTF-8 text using its current blob SHA."""
        body = {"content": base64.b64encode(content.encode("utf-8")).decode("ascii"), "sha": sha, "message": message, **provided(branch=branch)}
        return request(client, "PUT", _file_endpoint(filepath), owner=owner, reponame=reponame, url=url, body=body)

    @mcp.tool()
    def delete_file(filepath: str, sha: str, message: str, confirm: bool = False, branch: str | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Delete a file by current blob SHA after explicit confirmation."""
        require_confirmation(confirm, "delete this file")
        return request(client, "DELETE", _file_endpoint(filepath), owner=owner, reponame=reponame, url=url, body={"sha": sha, "message": message, **provided(branch=branch)})