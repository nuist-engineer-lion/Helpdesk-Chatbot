import nonebot
from nonebot.rule import to_me
from nonebot.plugin import on_message
from nonebot import get_bot
from nonebot.adapters import Event
import lark_oapi as lark
import json
import os
from dotenv import load_dotenv

load_dotenv()
feishu_group: str = os.getenv('FEISHU_GROUP')
app_id:str = os.getenv('APP_ID')
app_secret:str = os.getenv('APP_SECRET')

lark_client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()

test = on_message(rule=to_me(), priority=10)

@test.handle()
async def handle_function(event: Event):
    msg = f'{event.get_session_id()} says:{event.get_plaintext()}'
    msg_json= json.dumps({"text":msg,"type":"template"},ensure_ascii=False)
    request: lark.api.im.v1.CreateMessageRequest = lark.api.im.v1.CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(lark.api.im.v1.CreateMessageRequestBody.builder()
            .receive_id(feishu_group)
            .msg_type("text")
            .content(msg_json)
            .build()) \
        .build()

    # 发起请求
    response = lark_client.im.v1.message.create(request)
    if not response.success():
        lark.logger.error(
        f"client.request failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}")