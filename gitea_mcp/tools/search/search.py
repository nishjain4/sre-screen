"""Bounded commit and repository file search tools."""

from collections import deque
from typing import Any, TypedDict

from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.common import path_segment, provided, request


class RepositoryTarget(TypedDict): 
    owner: str | None
    reponame: str | None
    url: str | None


def register_search_tools(mcp: FastMCP, client: GiteaClient) -> None:
    @mcp.tool()
    def search_commits(query: str | None = None, sha: str | None = None, path: str | None = None, author: str | None = None, since: str | None = None, until: str | None = None, page: int = 1, limit: int = 50, owner: str | None = None, reponame: str | None = None, url: str | None = None) -> list:
        """Search repository commits using API filters and optional text matching."""
        params = provided(sha=sha, path=path, author=author, since=since, until=until, page=page, limit=limit)
        commits = request(client, "GET", "/commits", owner=owner, reponame=reponame, url=url, params=params)
        if not query:
            return commits
        needle = query.casefold()
        return [
            commit for commit in commits
            if needle in str(commit.get("sha", "")).casefold()
            or needle in str(commit.get("commit", {}).get("message", "")).casefold()
            or needle in str(commit.get("commit", {}).get("author", {}).get("name", "")).casefold()
        ]

    @mcp.tool()
    def search_repository(
        query: str,
        ref: str | None = None,
        include_content: bool = True,
        max_depth: int = 6,
        max_entries: int = 2000,
        max_files: int = 25,
        max_file_size: int = 262144,
        max_results: int = 100,
        owner: str | None = None,
        reponame: str | None = None,
        url: str | None = None,
    ) -> dict[str, Any]:
        """Search paths and bounded text content within a repository tree."""
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= max_depth <= 12:
            raise ValueError("max_depth must be between 1 and 12")
        if not 1 <= max_entries <= 5000:
            raise ValueError("max_entries must be between 1 and 5000")
        if not 0 <= max_files <= 100:
            raise ValueError("max_files must be between 0 and 100")
        if not 1 <= max_file_size <= 1048576:
            raise ValueError("max_file_size must be between 1 and 1048576 bytes")
        if not 1 <= max_results <= 500:
            raise ValueError("max_results must be between 1 and 500")

        target: RepositoryTarget = {"owner": owner, "reponame": reponame, "url": url}
        selected_ref = ref
        if selected_ref is None:
            repository = request(client, "GET", "", **target)
            selected_ref = repository["default_branch"]

        if len(selected_ref) == 40 and all(char in "0123456789abcdefABCDEF" for char in selected_ref):
            commit_id = selected_ref
        else:
            branch = request(client, "GET", f"/branches/{path_segment(selected_ref)}", **target)
            commit_id = branch["commit"]["id"]

        commit = request(client, "GET", f"/git/commits/{path_segment(commit_id)}", **target)
        root_tree_sha = commit["tree"]["sha"]
        pending = deque([(root_tree_sha, "", 0)])
        visited: set[str] = set()
        results: list[dict[str, Any]] = []
        entries_seen = 0
        content_files_read = 0
        truncated = False
        needle = query.casefold()

        while pending and entries_seen < max_entries and len(results) < max_results:
            tree_sha, prefix, depth = pending.popleft()
            if tree_sha in visited:
                continue
            visited.add(tree_sha)
            tree = request(client, "GET", f"/git/trees/{path_segment(tree_sha)}", **target)
            truncated = truncated or bool(tree.get("truncated", False))

            for entry in tree.get("tree", []):
                if entries_seen >= max_entries or len(results) >= max_results:
                    truncated = True
                    break
                entries_seen += 1
                entry_path = f"{prefix}/{entry['path']}" if prefix else entry["path"]
                entry_type = entry.get("type")
                if entry_type == "tree":
                    if depth < max_depth:
                        pending.append((entry["sha"], entry_path, depth + 1))
                    else:
                        truncated = True
                    continue

                if entry_type != "blob":
                    continue
                if needle in entry_path.casefold():
                    results.append({"path": entry_path, "match": "path", "sha": entry.get("sha"), "size": entry.get("size")})
                    if len(results) >= max_results:
                        truncated = True
                        break
                    continue

                size = entry.get("size")
                if not include_content:
                    continue
                if not isinstance(size, int) or size > max_file_size:
                    truncated = True
                    continue
                if content_files_read >= max_files:
                    truncated = True
                    continue
                content_files_read += 1
                text = request(
                    client,
                    "GET",
                    f"/raw/{path_segment(entry_path, allow_slashes=True)}",
                    **target,
                    params={"ref": commit_id},
                    response_format="text",
                )
                if "\x00" in text:
                    continue
                match_index = text.casefold().find(needle)
                if match_index >= 0:
                    start = max(0, match_index - 80)
                    end = min(len(text), match_index + len(query) + 80)
                    results.append({"path": entry_path, "match": "content", "snippet": text[start:end]})

        if pending or entries_seen >= max_entries:
            truncated = True
        return {
            "query": query,
            "ref": selected_ref,
            "results": results,
            "entries_scanned": entries_seen,
            "content_files_read": content_files_read,
            "truncated": truncated,
        }