# 在chatrecord解决问题之前用这个
from nonebot_plugin_chatrecorder.adapters.onebot_v11 import record_send_msg
from nonebot.compat import model_dump, type_validate_python
from nonebot import on
from nonebot.adapters.onebot.v11 import Bot, Event

on_message_sent = on("message_sent", priority=0,block=True)
@on_message_sent.handle()
async def record_sent(bot: Bot, event: Event):
    data = model_dump(event)
    # 插件中的message应当与data中的raw_message一致
    data['message']=data["raw_message"]
    # 使用的message_record的result参数可以从data中获取
    await record_send_msg(bot,None,"send_msg",data,data)