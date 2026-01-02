import json
import requests
from requests.auth import HTTPBasicAuth


class JiraClient:
    """Client for Jira Enterprise (Server/Data Center) v9 API."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.auth = HTTPBasicAuth(username, password)
        self.headers = {"Content-Type": "application/json"}

    def search_issues(self, jql: str, max_results: int = 100) -> list[dict]:
        """
        Search for issues using JQL.
        Returns a list of parsed issue dictionaries.
        """
        url = f"{self.base_url}/rest/api/2/search"
        all_issues = []
        start_at = 0

        while True:
            params = {
                "jql": jql,
                "startAt": start_at,
                "maxResults": min(max_results - len(all_issues), 100),
                "fields": "*all",
            }

            response = requests.get(
                url,
                params=params,
                auth=self.auth,
                headers=self.headers,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            issues = data.get("issues", [])
            if not issues:
                break

            for issue in issues:
                parsed = self._parse_issue(issue)
                all_issues.append(parsed)

            start_at += len(issues)
            if start_at >= data.get("total", 0) or len(all_issues) >= max_results:
                break

        return all_issues

    def _parse_issue(self, issue: dict) -> dict:
        """Parse a Jira issue into a flat dictionary."""
        fields = issue.get("fields", {})

        # Extract nested values safely
        def get_nested(obj, *keys, default=None):
            for key in keys:
                if obj is None:
                    return default
                obj = obj.get(key) if isinstance(obj, dict) else default
            return obj if obj is not None else default

        # Parse labels and components as comma-separated strings
        labels = fields.get("labels", []) or []
        components = fields.get("components", []) or []

        return {
            "jira_ticket_id": issue.get("key"),
            "project": get_nested(fields, "project", "key"),
            "issue_type": get_nested(fields, "issuetype", "name"),
            "summary": fields.get("summary"),
            "description": fields.get("description"),
            "status": get_nested(fields, "status", "name"),
            "priority": get_nested(fields, "priority", "name"),
            "assignee": get_nested(fields, "assignee", "displayName"),
            "reporter": get_nested(fields, "reporter", "displayName"),
            "created": fields.get("created"),
            "updated": fields.get("updated"),
            "resolved": fields.get("resolutiondate"),
            "labels": ",".join(labels),
            "components": ",".join(c.get("name", "") for c in components),
            "raw_json": json.dumps(issue),
        }

    def test_connection(self) -> bool:
        """Test if the connection to Jira is valid."""
        try:
            url = f"{self.base_url}/rest/api/2/myself"
            response = requests.get(
                url,
                auth=self.auth,
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            return True
        except Exception:
            return False
