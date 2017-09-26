import re

import requests


def upload_image(file):
    r = requests.post(
        'https://sm.ms/api/upload?ssl=1&format=json',
        files={'smfile': file}
    )
    if r.ok and r.json().get('code') == 'success':
        return r.json()['data']['url']
    return None


def remove_tags(html):
    return re.sub(r'<\s*/?\s*[a-zA-Z0-9]+.*?>', '', html)
