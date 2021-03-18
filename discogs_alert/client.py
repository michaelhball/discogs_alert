import json
import re
import requests

from bs4 import BeautifulSoup
from oauthlib import oauth1
from urllib.parse import parse_qsl, urlencode

from discogs_alert.scrape import scrape_listings_from_marketplace
from discogs_alert.utils import CONDITION_SHORT, CURRENCIES

__all__ = ["UserOAuthClient", "UserTokenClient"]


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

    def _request(self, method, url, data=None, headers=None, is_api=True):
        """

        @param method
        @param url
        @param data
        @param headers
        @param is_api
        :return:
        """

        raise NotImplementedError

    def _get(self, url, is_api=True):
        response_content, status_code = self._request("GET", url, is_api=is_api)
        if status_code != 200:
            print(f"ERROR: status_code: {status_code}, content: {response_content}")
            return False
        return json.loads(response_content) if is_api else response_content

    def _delete(self, url, is_api=True):
        return self._request('DELETE', url, is_api=is_api)

    def _patch(self, url, data, is_api=True):
        return self._request('PATCH', url, data=data, is_api=is_api)

    def _post(self, url, data, is_api=True):
        return self._request('POST', url, data=data, is_api=is_api)

    def _put(self, url, data, is_api=True):
        return self._request('PUT', url, data=data, is_api=is_api)

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

    def get_marketplace_listings(self, release_id):
        """ Get list of listings currently for sale for particular release.

        :param release_id: (int) discogs ID of release whose listings we want.
        :return: list of listings (dicts) if successful, False otherwise.
        """

        url = f'{self._base_url_non_api}/sell/release/{release_id}?ev=rb&sort=price%2Casc'
        response_content = self._get(url, is_api=False)
        return scrape_listings_from_marketplace(response_content)


class UserOAuthClient(Client):
    """ Client class allowing my app to make requests on behalf of any user who logs in. """

    def __init__(self, user_agent, consumer_key, consumer_secret, token=None, secret=None, *args, **kwargs):
        super().__init__(user_agent, *args, **kwargs)
        self.client = oauth1.Client(consumer_key, client_secret=consumer_secret)
        if token and secret:
            self.set_token(token, secret)

    def set_token(self, token, secret):
        self.client.resource_owner_key = token
        self.client.resource_owner_secret = secret

    def forget_token(self): self.set_token(None, None)

    def set_token_from_qs(self, query_string):
        token_dict = dict(parse_qsl(query_string))
        token = token_dict[b'oauth_token'].decode('utf8')
        secret = token_dict[b'oauth_token_secret'].decode('utf8')
        self.set_token(token, secret)
        return token, secret

    def set_verifier(self, verifier):
        self.client.verifier = verifier

    def get_authorize_url(self, callback_url=None):
        """ Returns a tuple of (access_token, access_secret, authorise_url) --> send a Discogs user to the authorise
            URL to get the verifier for the access token.

        @param callback_url:
        :return:
        """

        self.forget_token()
        params = {
            'User-Agent': self.user_agent,
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        if callback_url is not None:
            params['oauth_callback'] =  callback_url
        postdata = urlencode(params)

        content, status_code = self._request('POST', self._request_token_url, data=postdata, headers=params,
                                             is_api=True)
        if status_code != 200:
            raise Exception(f'Could not get request token. status_code: {status_code}, content: {content}')

        token, secret = self.set_token_from_qs(content)
        params = {'oauth_token': token}
        query_string = urlencode(params)

        return token, secret, '?'.join((self._authorise_url, query_string))

    def get_access_token(self, verifier):
        """ Uses the verifier to exchange a request token for an access token. """

        self.set_verifier(verifier.decode('utf8') if isinstance(verifier, bytes) else verifier)
        params = {'User-Agent': self.user_agent}
        content, status_code = self._request('POST', self._access_token_url, headers=params)
        if status_code != 200:
            error_str = f'Invalid response from access token URL. status_code: {status_code}, content: {content}'
            raise Exception(error_str)
        token, secret = self.set_token_from_qs(content)

        return token, secret

    def _request(self, method, url, data=None, headers=None, is_api=True, json_format=True):
        body = json.dumps(data) if json_format and data else data  # TODO: does this need to be used?
        uri, headers, body = self.client.sign(url, http_method=method, body=data, headers=headers)
        resp = requests.request(method, uri, headers=headers, data=body)
        if is_api:
            self.rate_limit = resp.headers.get('X-Discogs-Ratelimit')
            self.rate_limit_used = resp.headers.get('X-Discogs-Ratelimit-Used')
            self.rate_limit_remaining = resp.headers.get('X-Discogs-Ratelimit-Remaining')
        return resp.content, resp.status_code

    def identity(self):
        resp = self._get(f'{self._base_url}/oauth/identity')
        return resp


class UserTokenClient(Client):
    """ """

    def __init__(self, user_agent, user_token, *args, **kwargs):
        super().__init__(user_agent, *args, **kwargs)
        self.user_token = user_token

    def _request(self, method, url, data=None, headers=None, is_api=True):
        params = {'token': self.user_token} if is_api else None
        resp = requests.request(method, url, params=params, data=data, headers=headers)
        if is_api:
            self.rate_limit = resp.headers.get('X-Discogs-Ratelimit')
            self.rate_limit_used = resp.headers.get('X-Discogs-Ratelimit-Used')
            self.rate_limit_remaining = resp.headers.get('X-Discogs-Ratelimit-Remaining')
        return resp.content, resp.status_code
