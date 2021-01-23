import requests


__all__ = ["UserTokenClient"]


class Client:
    """ API Client to interact with discogs server. Taken & modified from https://github.com/joalla/discogs_client. """

    _base_url = 'https://api.discogs.com'
    _request_token_url = 'https://api.discogs.com/oauth/request_token'
    _authorize_url = 'https://www.discogs.com/oauth/authorize'
    _access_token_url = 'https://api.discogs.com/oauth/access_token'

    def __init__(self, user_agent, *args, **kwargs):
        self.user_agent = user_agent
        self.verbose = False  # ???
        self.rate_limit = None
        self.rate_limit_used = None
        self.rate_limit_remaining = None

    def _request(self, method, url, data=None, headers=None):
        raise NotImplementedError

    def _get(self, url):
        return self._request("GET", url)

    def _delete(self, url):
        return self._request('DELETE', url)

    def _patch(self, url, data):
        return self._request('PATCH', url, data=data)

    def _post(self, url, data):
        return self._request('POST', url, data=data)

    def _put(self, url, data):
        return self._request('PUT', url, data=data)

    def get_release(self, release_id):
        """

        :param release_id:
        :return:
        """

        url = f'{self._base_url}/releases/{release_id}' # to get all info about a release
        # url = f'{self._base_url}/marketplace/price_suggestions/{release_id}'
        # url = f'{self._base_url}/marketplace/stats/{release_id}'  # can use this to find out if any are for sale
        url = f'{self._base_url}/marketplace/listings/{1216266153}'  # NICE this works well, =>
        return self._get(url)


class UserTokenClient(Client):
    """ """

    def __init__(self, user_agent, user_token, *args, **kwargs):
        super().__init__(user_agent, *args, **kwargs)
        self.user_token = user_token

    def _request(self, method, url, data=None, headers=None):
        resp = requests.request(method, url, params={'token': self.user_token}, data=data, headers=headers)
        self.rate_limit = resp.headers.get('X-Discogs-Ratelimit')
        self.rate_limit_used = resp.headers.get('X-Discogs-Ratelimit-Used')
        self.rate_limit_remaining = resp.headers.get('X-Discogs-Ratelimit-Remaining')
        return resp.content, resp.status_code
