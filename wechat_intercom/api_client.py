import requests


class APIClient(object):
    def __init__(self, base_url):
        self.__url = base_url

    def __getattr__(self, item):
        return self.__class__(self.__url.rstrip('/') + '/' + item.lstrip('/'))

    def get(self, **kwargs):
        return requests.get(self.__url, **kwargs)

    def post(self, **kwargs):
        return requests.post(self.__url, **kwargs)

    def __call__(self, **kwargs):
        return self.get(params=kwargs)
