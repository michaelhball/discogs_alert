import json
import requests
import sys

from fake_useragent import UserAgent
from selenium import webdriver

from discogs_alert.scrape import scrape_listings_from_marketplace

import os
os.environ['WDM_LOG_LEVEL'] = '0'
from webdriver_manager.chrome import ChromeDriverManager

__all__ = ["AnonClient", "UserTokenClient"]


class Client:
    """ API Client to interact with discogs server. Taken & modified from https://github.com/joalla/discogs_client. """

    _base_url = 'https://api.discogs.com'
    _base_url_non_api = 'https://www.discogs.com'
    _request_token_url = 'https://api.discogs.com/oauth/request_token'
    _authorise_url = 'https://www.discogs.com/oauth/authorize'
    _access_token_url = 'https://api.discogs.com/oauth/access_token'

    def __init__(self, user_agent, *args, **kwargs):
        self.user_agent = user_agent
        self.verbose = False  # ???
        self.rate_limit = None
        self.rate_limit_used = None
        self.rate_limit_remaining = None
        # TODO: use these limits to give myself / customers notifications

    def _request(self, method, url, data=None, headers=None):
        """

        @param method
        @param url
        @param data
        @param headers
        :return:
        """

        raise NotImplementedError

    def _get(self, url, is_api=True):
        response_content, status_code = self._request("GET", url, headers=None)
        if status_code != 200:
            print(f"ERROR: status_code: {status_code}, content: {response_content}")
            return False
        return json.loads(response_content) if is_api else response_content

    def _delete(self, url, is_api=True):
        return self._request('DELETE', url)

    def _patch(self, url, data, is_api=True):
        return self._request('PATCH', url, data=data)

    def _post(self, url, data, is_api=True):
        return self._request('POST', url, data=data)

    def _put(self, url, data, is_api=True):
        return self._request('PUT', url, data=data)

    def get_list(self, list_id):
        """ Get user-created list.

        :param list_id:
        :return:
        """

        url = f'{self._base_url}/lists/{list_id}'
        return self._get(url)

    def get_listing(self, listing_id):
        """

        @param listing_id
        :return:
        """

        url = f'{self._base_url}/marketplace/listings/{listing_id}'
        return self._get(url)

    def get_release(self, release_id):
        """ Get all info about a given release, returned as a bytes blob.

        :param release_id:
        :return:
        """

        url = f'{self._base_url}/releases/{release_id}'
        return self._get(url)

    def get_release_stats(self, release_id):
        """ Get number of items that are for sale, lowest listed price, & for provided release.

        @param release_id
        :return:
        """

        url = f'{self._base_url}/marketplace/stats/{release_id}'
        return self._get(url)

    def get_wantlist(self, username):
        url = f'{self._base_url}/users/{username}/wants'
        return self._get(url)


class UserTokenClient(Client):
    """ A client for sending requests with a user token (for non-oauth authentication). """

    def __init__(self, user_agent, user_token, *args, **kwargs):
        super().__init__(user_agent, *args, **kwargs)
        self.user_token = user_token

    def _request(self, method, url, data=None, headers=None):
        params = {'token': self.user_token}
        resp = requests.request(method, url, params=params, data=data, headers=headers)
        self.rate_limit = resp.headers.get('X-Discogs-Ratelimit')
        self.rate_limit_used = resp.headers.get('X-Discogs-Ratelimit-Used')
        self.rate_limit_remaining = resp.headers.get('X-Discogs-Ratelimit-Remaining')
        return resp.content, resp.status_code


class AnonClient(Client):
    """ A Client for anonymous scraping requests (when not using the Discogs API, i.e. for the marketplace). """

    def __init__(self, user_agent, *args, **kwargs):
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
            f"--user-agent={self.user_agent.random}"  # initialize with random user-agent
        ]
        for argument in options_arguments:
            self.options.add_argument(argument)

        self.driver_manager = ChromeDriverManager(log_level=0).install()
        unix = {'linux', 'linux2', 'darwin'}
        self.driver = webdriver.Chrome(self.driver_manager, options=self.options,
                                       service_log_path='/dev/null' if sys.platform in unix else 'NUL')  # disable logs

    def get_marketplace_listings(self, release_id):
        """ Get list of listings currently for sale for particular release.

        :param release_id: (int) discogs ID of release whose listings we want.
        :return: list of listings (dicts) if successful, False otherwise.
        """

        # update user_agent (don't need because we choose a new one on instantiation, every loop).
        # self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": user_agent})

        # pull & scrape page content
        url = f'{self._base_url_non_api}/sell/release/{release_id}?ev=rb&sort=price%2Casc'
        self.driver.get(url)
        response_content = self.driver.page_source
        return scrape_listings_from_marketplace(response_content)
