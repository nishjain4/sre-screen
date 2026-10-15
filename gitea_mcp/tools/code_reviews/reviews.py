"""Tools for reviewing pull requests."""

from typing import Any

from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.common import provided, request


_REVIEW_EVENTS = {"APPROVED", "REQUEST_CHANGES", "COMMENT"}


def register_review_tools(mcp: FastMCP, client: GiteaClient) -> None:
    @mcp.tool()
    def list_reviews(index: int, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """List reviews on a pull request."""
        return request(client, "GET", f"/pulls/{index}/reviews", owner=owner, reponame=reponame, url=url)

    @mcp.tool()
    def create_review(index: int, event: str, body: str | None = None, commit_id: str | None = None, comments: list[dict[str, Any]] | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Create a review with an event and optional inline comments."""
        if event not in _REVIEW_EVENTS:
            raise ValueError("event must be APPROVED, REQUEST_CHANGES, or COMMENT")
        payload = {"event": event, **provided(body=body, commit_id=commit_id, comments=comments)}
        return request(client, "POST", f"/pulls/{index}/reviews", owner=owner, reponame=reponame, url=url, body=payload)

    @mcp.tool()
    def submit_review(index: int, review_id: int, event: str, body: str | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Submit or update a pending review with an explicit event."""
        if event not in _REVIEW_EVENTS:
            raise ValueError("event must be APPROVED, REQUEST_CHANGES, or COMMENT")
        return request(client, "POST", f"/pulls/{index}/reviews/{review_id}", owner=owner, reponame=reponame, url=url, body={"event": event, **provided(body=body)})

    @mcp.tool()
    def approve_pr(index: int, body: str | None = None, commit_id: str | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Submit an approval review for a pull request."""
        payload = {"event": "APPROVED", **provided(body=body, commit_id=commit_id)}
        return request(client, "POST", f"/pulls/{index}/reviews", owner=owner, reponame=reponame, url=url, body=payload)

    @mcp.tool()
    def request_changes(index: int, body: str, commit_id: str | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Submit a request-changes review for a pull request."""
        payload = {"event": "REQUEST_CHANGES", "body": body, **provided(commit_id=commit_id)}
        return request(client, "POST", f"/pulls/{index}/reviews", owner=owner, reponame=reponame, url=url, body=payload)

    @mcp.tool()
    def comment_review(index: int, body: str, commit_id: str | None = None, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> dict:
        """Submit a comment-only review for a pull request."""
        payload = {"event": "COMMENT", "body": body, **provided(commit_id=commit_id)}
        return request(client, "POST", f"/pulls/{index}/reviews", owner=owner, reponame=reponame, url=url, body=payload)