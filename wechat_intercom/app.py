import base64
import hmac
import os
import re
from urllib.parse import (
    quote as urlencode,
    unquote as urldecode
)

from flask import Flask, request, g
from requests import Session

from wechat_intercom.wechat import WeChat
from wechat_intercom.utils import upload_image, remove_tags

app = Flask(__name__)
app.config.from_object(os.getenv('FLASK_SETTINGS', 'settings'))

session = Session()
session.trust_env = False
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

    wechat_client = 'default'
    if 'client' in request.args:
        wechat_client = urldecode(request.args['client'])
    g.wechat_client = wechat_client
    g.wechat_client_encoded = urlencode(wechat_client)

    if ctx['post_type'] == 'receive_message' \
            and ctx['type'] == 'friend_message':
        handle_friend_message(ctx)
    elif ctx['post_type'] == 'event' \
            and 'INTERCOM_BOT_USER_ID' in app.config:
        if ctx['event'] == 'input_qrcode':
            qrcode_url = ctx['params'][-1]
            reply_or_initiate(
                user_id=app.config['INTERCOM_BOT_USER_ID'],
                body='%s 登录二维码：%s' % (g.wechat_client, qrcode_url)
            )
        elif ctx['event'] == 'login':
            reply_or_initiate(
                user_id=app.config['INTERCOM_BOT_USER_ID'],
                body='%s 登录成功，开始等待客人了～' % g.wechat_client
            )
    return '', 204


def handle_friend_message(ctx):
    wechat_id = ctx.get('sender_id')
    if not wechat_id:
        return

    user_id = '/'.join(('wechat', g.wechat_client, wechat_id))

    avatar_url = None
    resp = wechat.get_avatar.get(params={
        'client': g.wechat_client_encoded,
        'id': wechat_id
    }, stream=True)
    if resp.ok:
        avatar_url = upload_image(resp.raw)

    payload = {
        'user_id': user_id
    }
    if 'sender_name' in ctx:
        payload['name'] = g.wechat_client + ': ' + ctx['sender_name']
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

    body = ctx['content']
    if image_url:
        body = '[图片](%s)' % image_url
    reply_or_initiate(user_id, body)


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
    user_id_parts = user_id.split('/')

    message = ctx['data']['item'][
        'conversation_parts']['conversation_parts'][0]
    image_urls = [
        m.group(1)
        for m in re.finditer(r'<\s*img\s+src="(http.+?)"\s*>', message['body'])
    ]

    if user_id_parts[0] == 'wechat':
        wechat_client, wechat_id = user_id_parts[1:]
        wechat_client_encoded = urlencode(wechat_client)
        for url in image_urls:
            wechat.send_friend_message(
                client=wechat_client_encoded,
                id=wechat_id,
                media_path=url
            )
        wechat.send_friend_message(
            client=wechat_client_encoded,
            id=wechat_id,
            content=remove_tags(message['body']).strip()
        )
    elif 'INTERCOM_BOT_USER_ID' in app.config \
            and user_id == app.config['INTERCOM_BOT_USER_ID']:
        handle_admin_commands(app.config['INTERCOM_BOT_USER_ID'],
                              remove_tags(message['body']).strip())


def handle_conversation_closed(ctx):
    user_id = ctx['data']['item']['user']['user_id']
    if user_id.startswith('wechat/'):
        session.delete(api('users'), params={
            'user_id': user_id
        })


def handle_admin_commands(bot_id, command):
    cmd, *args = command.split()
    if cmd in ('上线', '下线'):
        wechat_client = 'default'
        if args:
            wechat_client = args[0]
        wechat_client_encoded = urlencode(wechat_client)

        if cmd == '上线':
            resp = wechat.start_client(client=wechat_client_encoded)
            if not resp.ok or resp.json()['code'] != 0:
                # failed
                reply_or_initiate(
                    user_id=bot_id,
                    body='%s 上线失败'
                )
            elif resp.json()['status'] == 'client already exists':
                reply_or_initiate(
                    user_id=bot_id,
                    body='%s 已在线上（有可能正在等待扫码登录）' % wechat_client
                )
        elif cmd == '下线':
            resp = wechat.stop_client(client=wechat_client_encoded)
            if not resp.ok or resp.json()['code'] != 0:
                reply_or_initiate(
                    user_id=bot_id,
                    body='%s 下线失败（可能当前不在线上）' % wechat_client
                )
            elif resp.json()['status'] == 'success':
                reply_or_initiate(
                    user_id=bot_id,
                    body='%s 已下线' % wechat_client
                )
    elif cmd == '查看':
        resp = wechat.check_client()
        if resp.ok and resp.json()['code'] == 0:
            reply_or_initiate(
                user_id=bot_id,
                body='\n'.join([urldecode(x['account']) + ': ' + x['state']
                                for x in resp.json()['client']])
            )


def reply_or_initiate(user_id, body, payload=None):
    if payload is None:
        payload = {
            'type': 'user',
            'message_type': 'comment',
            'user_id': user_id,
            'body': body
        }
    resp = session.post(api('conversations/last/reply'), json=payload)
    if not resp.ok and resp.status_code == 422:
        session.post(api('messages'), json={
            'from': {
                'type': 'user',
                'user_id': payload['user_id']
            },
            'body': payload['body']
        })


if __name__ == '__main__':
    try:
        from gevent.wsgi import WSGIServer
        has_gevent = True
    except ImportError:
        has_gevent = False

    if not app.debug and has_gevent:
        http_server = WSGIServer(
            (app.config['HOST'], app.config['PORT']), app)
        http_server.serve_forever()
    else:
        app.run(host=app.config['HOST'], port=app.config['PORT'])
