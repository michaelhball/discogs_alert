# ruff: noqa: E402
import os

# to prevent the webdriver manager from polluting logs
os.environ["WDM_LOG"] = "0"

import json
import logging
import sys
from typing import Union

import requests
from fake_useragent import UserAgent
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager

from discogs_alert import scrape as da_scrape, types as da_types

logger = logging.getLogger(__name__)


class Client:
    """API Client to interact with discogs server. Taken & modified from https://github.com/joalla/discogs_client."""

    _base_url = "https://api.discogs.com"
    _base_url_non_api = "https://www.discogs.com"
    _request_token_url = "https://api.discogs.com/oauth/request_token"
    _authorise_url = "https://www.discogs.com/oauth/authorize"
    _access_token_url = "https://api.discogs.com/oauth/access_token"

    def __init__(self, user_agent, *args, **kwargs):
        self.user_agent = user_agent
        self.verbose = False
        self.rate_limit = None
        self.rate_limit_used = None
        self.rate_limit_remaining = None

    def _request(self, method, url, data=None, headers=None):
        raise NotImplementedError

    def _get(self, url: str, is_api: bool = True):
        response_content, status_code = self._request("GET", url, headers=None)
        if status_code != 200:
            logger.info(f"ERROR: status_code: {status_code}, content: {response_content}")
            return False
        return json.loads(response_content) if is_api else response_content

    def _delete(self, url: str, is_api: bool = True):
        return self._request("DELETE", url)

    def _patch(self, url: str, data, is_api: bool = True):
        return self._request("PATCH", url, data=data)

    def _post(self, url: str, data, is_api: bool = True):
        return self._request("POST", url, data=data)

    def _put(self, url: str, data, is_api: bool = True):
        return self._request("PUT", url, data=data)

    def get_list(self, list_id: int) -> da_types.UserList:
        user_list_dict = self._get(f"{self._base_url}/lists/{list_id}")
        user_list_dict["items"] = [da_types.Release(**item) for item in user_list_dict["items"]]
        return da_types.UserList(**user_list_dict)

    def get_listing(self, listing_id: int) -> da_types.Listing:
        listing_dict = self._get(f"{self._base_url}/marketplace/listings/{listing_id}")
        return da_types.Listing(**listing_dict)

    def get_release(self, release_id: int) -> da_types.Release:
        release_dict = self._get(f"{self._base_url}/releases/{release_id}")
        return da_types.Release(**release_dict)

    def get_release_stats(self, release_id: int) -> Union[da_types.ReleaseStats, bool]:
        release_stats_dict = self._get(f"{self._base_url}/marketplace/stats/{release_id}")
        return da_types.ReleaseStats(**release_stats_dict) if isinstance(release_stats_dict, dict) else False

    def get_wantlist(self, username: str):
        # TODO: add entities to deserialise this correctly
        url = f"{self._base_url}/users/{username}/wants"
        return self._get(url)


class UserTokenClient(Client):
    """A client for sending requests with a user token (for non-oauth authentication)."""

    def __init__(self, user_agent: str, user_token: str, *args, **kwargs):
        super().__init__(user_agent, *args, **kwargs)
        self.user_token = user_token

    def _request(self, method: str, url: str, data=None, headers=None):
        params = {"token": self.user_token}
        resp = requests.request(method, url, params=params, data=data, headers=headers)
        self.rate_limit = int(resp.headers.get("X-Discogs-Ratelimit"))
        self.rate_limit_used = int(resp.headers.get("X-Discogs-Ratelimit-Used"))
        self.rate_limit_remaining = int(resp.headers.get("X-Discogs-Ratelimit-Remaining"))
        return resp.content, resp.status_code


class AnonClient(Client):
    """A Client for anonymous scraping requests (when not using the Discogs API, i.e. for the marketplace)."""

    def __init__(self, user_agent: str, *args, **kwargs):
        super().__init__(user_agent, *args, **kwargs)

        self.user_agent = UserAgent()  # can pull up-to-date user agents from any modern browser

        self.options = webdriver.ChromeOptions()
        options_arguments = [
            "no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-infobars",
            "--headless",
            "--incognito",
            f"--user-agent={self.user_agent.random}",  # initialize with random user-agent
        ]
        for argument in options_arguments:
            self.options.add_argument(argument)

        self.driver_manager = ChromeDriverManager().install()
        unix = {"linux", "linux2", "darwin"}
        self.driver = webdriver.Chrome(
            self.driver_manager, options=self.options, service_log_path="/dev/null" if sys.platform in unix else "NUL"
        )  # disable logs

    def get_marketplace_listings(self, release_id: int) -> da_types.Listings:
        """Get list of listings currently for sale for particular release.

        Args:
            release_id: discogs ID of release whose listings we want.

        Returns: list of Listing objects if successful, False otherwise.
        """

        # update user_agent (don't need because we choose a new one on instantiation, every loop).
        # self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": user_agent})

        # pull & scrape page content
        url = f"{self._base_url_non_api}/sell/release/{release_id}?ev=rb&sort=price%2Casc"
        self.driver.get(url)
        return da_scrape.scrape_listings_from_marketplace(self.driver.page_source, release_id)
