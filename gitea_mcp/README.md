# Local Gitea MCP server

This directory bundles the HTTP Gitea MCP server and its repository tools, so
no separate checkout, VS Code MCP configuration, or shared OAuth helper is needed.
The backend sends a user-provided Gitea personal access token in the
`Gitea-Token` header on each request. This HTTP edition does not implement OAuth.

From the repository root, using the activated Python environment:

```powershell
python -m pip install -r gitea_mcp\requirements.txt
Copy-Item gitea_mcp\.env.example gitea_mcp\.env
# Edit gitea_mcp\.env: set GITEA_URL to your own Gitea instance.
python gitea_mcp\gitea_mcp_server.py
```

The server listens at `http://localhost:8001/mcp`. Start it before the backend.
Set the same `GITEA_URL`, plus `GITEA_TOKEN`, `GITEA_OWNER`, and `GITEA_REPO`,
in `backend/.env`. Use a read-only token for repository investigation; write
tools are also registered and Gitea enforces the token's permissions.
Do not expose this local HTTP service to a public network. It accepts request
tokens only for the configured Gitea base URL (or an explicitly configured
`GITEA_ALLOWED_URLS` comma-separated allowlist).

To verify connectivity without a Gitea API request, use the activated environment:

```powershell
fastmcp list http://localhost:8001/mcp
```

Then start the backend and check `http://localhost:8000/api/config` and
`http://localhost:8000/api/tools`. The MCP connection must be successful and
Gitea tools must be listed. A repository overview in the UI verifies real Gitea
access; tool discovery alone does not prove the token or repository permissions.

Never commit local environment files or tokens. See the root
[README](../README.md) for the full application setup and offline validation.
