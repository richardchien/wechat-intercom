import os
import re
import base64
import hmac

from requests import Session
from flask import Flask, request

from wechat import WeChat
from utils import upload_image, remove_tags

app = Flask(__name__)
app.config.from_object(os.getenv('FLASK_SETTINGS', 'settings'))

session = Session()
session.headers.update({
    'Authorization': 'Bearer ' + app.config['INTERCOM_ACCESS_TOKEN'],
    'Accept': 'application/json',
    'Connection': 'Keep-Alive'
})

wechat = WeChat(app.config['WECHAT_API_BASE_URL'])


def api(path):
    return 'https://api.intercom.io/' + path.lstrip('/')


@app.route('/wechat', methods=['POST'])
def wechat_entry():
    ctx = request.json
    if ctx['post_type'] == 'receive_message' \
            and ctx['type'] == 'friend_message':
        handle_friend_message(ctx)
    return '', 204


def handle_friend_message(ctx):
    user_id = ctx.get('sender_id')
    if not user_id:
        return

    if user_id:
        avatar_url = None
        resp = wechat.get_avatar.get(params={
            'id': user_id
        }, stream=True)
        if resp.ok:
            avatar_url = upload_image(resp.raw)

        payload = {
            'user_id': user_id
        }
        if 'sender_name' in ctx:
            payload['name'] = ctx['sender_name']
        if avatar_url:
            payload['avatar'] = {
                'type': 'avatar',
                'image_url': avatar_url
            }

        resp = session.post(api('users'), json=payload)

        if not resp.ok:
            return

        image_url = None
        if ctx.get('format') == 'media' \
                and ctx.get('media_mime', '').startswith('image'):
            image_url = upload_image(base64.b64decode(ctx['media_data']))

        payload = {
            'type': 'user',
            'message_type': 'comment',
            'user_id': user_id,
            'body': ctx['content']
        }
        if image_url:
            payload['body'] = '[图片](%s)' % image_url
        resp = session.post(api('conversations/last/reply'), json=payload)
        if not resp.ok and resp.status_code == 422:
            session.post(api('messages'), json={
                'from': {
                    'type': 'user',
                    'user_id': user_id
                },
                'body': payload['body']
            })


@app.route('/intercom', methods=['POST'])
def intercom_entry():
    ctx = request.json

    if 'X-Hub-Signature' in request.headers:
        sig = hmac.new(app.config['INTERCOM_WEBHOOK_SECRET'].encode('ascii'),
                       request.get_data(),
                       'sha1').hexdigest()
        if 'sha1=' + sig != request.headers['X-Hub-Signature']:
            return '', 401

    if ctx['type'] == 'notification_event':
        if ctx['topic'] == 'conversation.admin.replied':
            handle_conversation_replied(ctx)
        elif ctx['topic'] == 'conversation.admin.closed':
            handle_conversation_closed(ctx)

    return '', 204


def handle_conversation_replied(ctx):
    user_id = ctx['data']['item']['user']['user_id']
    message = ctx['data']['item'][
        'conversation_parts']['conversation_parts'][0]

    image_urls = [
        m.group(1)
        for m in re.finditer(r'<\s*img\s+src="(http.+?)"\s*>', message['body'])
    ]

    for url in image_urls:
        wechat.send_friend_message(id=user_id,
                                   media_path=url)

    wechat.send_friend_message(id=user_id,
                               content=remove_tags(message['body']).strip())


def handle_conversation_closed(ctx):
    user_id = ctx['data']['item']['user']['user_id']
    session.delete(api('users'), params={
        'user_id': user_id
    })


if __name__ == '__main__':
    app.run(host=app.config['HOST'], port=app.config['PORT'])
