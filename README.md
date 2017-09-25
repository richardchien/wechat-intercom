# WeChat <=> Intercom

基于 [Mojo-Weixin](https://github.com/sjdy521/Mojo-Weixin)，将微信个人号的私聊消息转发到 [Intercom](https://www.intercom.com/) 客服后台，再将客服的回复转发到微信，从而实现多个客服通过单个微信号和多个客户沟通。

## 配置

1. 修改配置文件
    - `HOST` 监听地址
    - `PORT` 监听端口
    - `WECHAT_API_BASE_URL` Mojo-Weixin 的 Openwx 插件接口地址
    - `INTERCOM_ACCESS_TOKEN` Intercom 的 access token
    - `INTERCOM_WEBHOOK_SECRET` Intercom 的 webhook 的签名密钥
2. 运行 `app.py`（可以用其它部署 WSGI 的方法部署）
3. 在 Mojo-Weixin 配置上报地址为 `http://<IP>:<PORT>/wechat`，登录
4. 在 Intercom 添加一个接受 `Conversation closed`、`Reply from your teammates` 通知的 webhook，地址为 `http://<IP>:<PORT>/intercom`

## 局限

多媒体信息目前只能图片，Intercom 中发的图片，会以图片的形式发到微信，微信中发的图片会以外链的形式发到 Intercom。
