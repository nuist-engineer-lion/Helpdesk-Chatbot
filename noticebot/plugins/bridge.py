import nonebot
from nonebot.rule import to_me
from nonebot.plugin import on_message
from nonebot.adapters.feishu import Bot as FeishuBot
from nonebot.adapters.onebot.v11 import Bot as OneBot
from nonebot import get_bot
from nonebot.adapters import Event
import os


feishu_group: str = os.getenv('FEISHU_GROUP')

feishu_bot_id = nonebot.get_driver().config.feishu_bots[0]['app_id']
test = on_message(rule=to_me(),priority=10)

@test.handle()
async def handle_function(event:Event):
    feishu:FeishuBot = get_bot(feishu_bot_id)
    feishu.send_msg(receive_id_type="chat_id",
                    receive_id=feishu_group,
                    content=f"{event.get_session_id} says:\n{event.get_message}",
                    msg_type='text'
                    )