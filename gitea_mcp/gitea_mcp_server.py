from fastmcp import FastMCP

from gitea_client import GiteaClient
from tools.actions.actions import register_action_tools
from tools.branches.branches import register_branch_tools
from tools.code_reviews.reviews import register_review_tools
from tools.commits_status.commits import register_commit_tools
from tools.files_and_trees.files import register_file_tools
from tools.issues_comments.issues import register_issue_tools
from tools.labels_milestones.labels import register_label_milestone_tools
from tools.pull_requests.pull_requests import register_pull_request_tools
from tools.repository_context.get_repository import register_repository_tools
from tools.search.search import register_search_tools
from tools.tags_releases.releases import register_release_tools
from tools.webhooks.webhooks import register_webhook_tools

client = GiteaClient()
mcp = FastMCP(name="Gitea MCP")

for register_tools in (
    register_repository_tools,
    register_file_tools,
    register_branch_tools,
    register_commit_tools,
    register_pull_request_tools,
    register_review_tools,
    register_issue_tools,
    register_label_milestone_tools,
    register_release_tools,
    register_webhook_tools,
    register_action_tools,
    register_search_tools,
):
    register_tools(mcp, client)


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="localhost", port = 8001
    )