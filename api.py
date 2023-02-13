from typing import Any, Dict, List
from datetime import datetime
import re
from jira import JIRA
import json
from my_fake_security import get_secret, is_production

"""
This is used by the minty to manage jira tickets.
"""
import logging

USING_JIRA_STAGE = False  # update this value to true to hit the staging server, highly recomended while developing
USERNAME = "user@company.com"
PASSWORD = "MY_PASSWORD"
PROD_SERVER = "https://api-jira.my_company.net"  # production server
STAGE_SERVER = "https://api-jira-stage.my_company.net"  # staging server
PROJECT = "EXAMPLE"
JIRA_HTTPS_PROXY = "my_proxy"

now = datetime.now().strftime("%m/%d/%Y, %H:%M:%S UTC")

# `generated_code_tag` is used to parse the database, any changes will break the ability to find historical data
generated_code_tag = (
    f"generated code: This json text was generated on {now}. Do not modify! \n"
)

logger = logging.getLogger(__name__)

# READ ME
# Custom fields get a custom id in Jira. Every time a new field is added
# its issued a new custom field.
# The easiest way to find fields is to do something like:
# jira.issue(some_ticket_id)
# allFields = jira.fields()
# for field in allFields:
#     print("name: {}, id: {}".format(field['name'], field['id']))


class JiraAPI(object):
    def __init__(self) -> None:
        self.username = USERNAME
        self.password = get_secret(PASSWORD)
        # sets up Jira to only use a proxy in production
        self.proxies = {}
        if is_production():
            self.proxies = {"https": JIRA_HTTPS_PROXY}

        # sets up auth for jira stage using the username/password auth used for jira stage
        if USING_JIRA_STAGE:
            self.options = {"server": STAGE_SERVER}

        self.jira = JIRA(
            basic_auth=(self.username, self.password),
            options=self.options,
            proxies=self.proxies,
        )

    def get_jira_details(self, jira_key: str) -> Dict[str, Any]:
        """
        Used to get details of jira ticket
        """
        logger.info("get_jira_details: {}".format(jira_key))
        results = {}

        issue = self.jira.issue(jira_key)

        results["summary"] = issue.fields.summary

        re_message = re.compile(
            "generated code: This json text was generated on+Do not modify!"
        )

        item_data: List[Dict[str, Any]] = []
        jobs = {}
        if issue.fields.customfield_14000 == None:
            timestamp = "not available"
        else:
            # remove the generated_code_tag from data
            issue_data = re.sub(re_message, "", issue.fields.customfield_1400)
            # check if any data has been stored on this field
            if issue_data == "":
                timestamp = "not available"
            # parse data from custom field
            elif is_json(issue_data):
                json_issue_data = json.loads(issue_data)
                item_data = json_issue_data.get("items", [])
                jobs = json_issue_data.get("jobs", {})
                timestamp = json_issue_data.get(
                    "timestamp", "unknown, 'timestamp' not stored on ticket"
                )
            else:
                raise Exception(
                    f"Custom Field is not Valid JSON and cannot be read. Go to https://jira.my_project.net/browse/{jira_key} and check the format of the JSON under the 'Additional Fields Tab`."
                )
        results["jobs"] = jobs
        results["items"] = item_data
        results["timestamp"] = timestamp

        # add comments to response
        results["comments"] = []
        comments = issue.fields.comment.comments
        for unedited_comment in comments:
            comment = {}

            comment["body"] = unedited_comment.body
            comment["created"] = unedited_comment.created
            comment["timestamp"] = unedited_comment.timestamp
            comment["authorName"] = unedited_comment.author.displayName
            comment["email"] = unedited_comment.author.name
            results["comments"].append(comment)
        return results

    def get_open_tickets(self) -> Dict[str, Any]:
        """
        Used to get all open EXAMPLE ticekts
        """
        logger.info("get_open_tickets")
        results: Dict[str, Any] = {}
        results["issues"] = []
        issues = self.jira.search_issues("project = EXAMPLE")
        for issue in issues:
            title_string = issue.key + ": " + issue.fields.summary
            results["issues"].append(title_string)
        return results

    def add_job(
        self, job_id: str, jira_key: str, description: str, item: str
    ) -> Dict[str, Any]:
        """
        appends job_id and description to list of jobs
        """
        logger.info(f"add_job {job_id} to {jira_key}")
        issue = self.get_jira_details(jira_key)
        jobs: Dict[str, Dict[str, str]] = issue.get("jobs", {})
        jobs[job_id] = {"description": description, "item": item}
        issue["jobs"] = jobs
        updated_issue = self.overwrite_job_data(jobs, jira_key)
        return updated_issue

    def post_comment(self, comment: str, jira_key: str) -> Any:
        """
        Posts a comment on jira
        """
        posted_comment = self.jira.add_comment(jira_key, comment)
        comment_id = posted_comment.id
        logger.info("post_comment id: {}".format(comment_id))
        return comment_id

    def update_comment(self, comment_id: str, comment: str) -> None:
        """
        Updates a comment on jira
        """
        comment = self.jira.get_comment(comment_id)
        comment.update(comment)

    def update_custom_field_item(self, item_data: str, jira_key: str) -> Dict[str, Any]:
        """
        Overwrites only the `items` key of the json data stored on custom_field_1400
        """
        logger.info("update_custom_field_item")
        issue = self.get_jira_details(jira_key)
        jobs = self.get_jira_details(jira_key).get("jobs", {})
        updated_item_data = self._generate_json_data(item_data, jobs)

        payload = f"{generated_code_tag}{updated_item_data}"
        custom_field_json = self._update_issue_data(payload, jira_key=jira_key)
        updated_issue = issue.update(custom_field_json)
        return updated_issue

    def update_custom_field_job(
        self, jobs: Dict[str, Dict[str, str]], jira_key: str
    ) -> Dict[str, Any]:
        """
        Overwrites only the `jobs` key of the json data stored on custom_field_1400

        """
        logger.info("update_custom_field_job")
        issue = self.get_jira_details(jira_key)
        item_data = self.get_jira_details(jira_key).get("items", [])
        updated_item_data = self._generate_json_data(json.dumps(item_data), jobs)
        payload = f"{generated_code_tag}{updated_item_data}"
        custom_field_json = self._update_issue_data(payload, jira_key)
        updated_issue = issue.update(custom_field_json)
        return updated_issue

    def append_item_data(self, item: Dict[Any, Any], jira_key: str) -> Dict[str, Any]:
        """
        Appends the list of "items" stored in the description of a jira ticket
        """
        logger.info("append_item_data")
        issue = self.get_jira_details(jira_key)
        jobs = issue.get("jobs", [])
        old_item_data = issue.get("items", "none")
        old_item_data.append(item)
        updated_item_data = self._generate_json_data(json.dumps(old_item_data), jobs)
        payload = f"{generated_code_tag}{updated_item_data}"

        custom_field_json = self._update_issue_data(payload, jira_key)
        updated_issue = issue.update(custom_field_json)
        return updated_issue

    def _generate_custom_field_json(self, description: str) -> None:
        """
        Updates a the affected items field of a jira issue, aka `customfield_14000`

        """
        return json.dumps({"fields": {"customfield_1400": f"{description}"}})

    def _generate_json_data(
        self, item_data: str, jobs: Dict[str, Dict[str, str]]
    ) -> str:
        """
        generates a correctly formatted json string, with single quotes around the json object and double quotes around
        internal strings. Incorrect formatting leads to `/` characters leading up to single quotes surrounding the json
        internal strings because the json is not recognized and it is read as a string.
        """
        now = datetime.now().strftime("%m/%d/%Y, %H:%M:%S UTC")
        stringified_json = json.dumps(
            {"updated": f"{now}", "items": json.loads(item_data), "jobs": jobs},
            indent=4,
        )
        return stringified_json


def is_json(string: str) -> bool:
    try:
        json.loads(string)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    print(JiraAPI().get_jira_details(jira_key="EXAMPLE-1"))
