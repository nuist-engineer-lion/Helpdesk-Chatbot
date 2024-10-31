# 在chatrecord解决问题之前用这个
from datetime import datetime,timezone
from nonebot.compat import model_dump, type_validate_python
from nonebot import on
from nonebot.adapters.onebot.v11 import Bot, Event, Message, MessageEvent
from nonebot_plugin_orm import get_session
from nonebot_plugin_session import Session, SessionLevel
from nonebot_plugin_chatrecorder.consts import SupportedPlatform,SupportedAdapter
from nonebot_plugin_chatrecorder.utils import remove_timezone
from nonebot_plugin_chatrecorder.model import MessageRecord
from nonebot_plugin_chatrecorder.message import serialize_message
from nonebot_plugin_session_orm import get_session_persist_id


adapter = SupportedAdapter.onebot_v11

on_message_sent = on("message_sent", priority=0,block=True)
@on_message_sent.handle()
async def record_sent(bot: Bot, event: Event):
    data = model_dump(event)    

    if data.get("message_type") == "group" or (data.get("message_type") == None and data.get("group_id")):
        level = SessionLevel.LEVEL2
    else:
        level = SessionLevel.LEVEL1

    session = Session(
                bot_id=bot.self_id,
                bot_type=bot.type,
                platform=SupportedPlatform.qq,
                level=level,
                id1=str(data.get("target_id", "")) or None,
                id2=str(data.get("group_id", "")) or None,
                id3=None,
            )
    session_persist_id = await get_session_persist_id(session)

    message = Message(data["raw_message"])
    record = MessageRecord(
                session_persist_id=session_persist_id,
                time=remove_timezone(datetime.now(timezone.utc)),
                type="message_sent",
                message_id=str(data["message_id"]),
                message=serialize_message(adapter, message),
                plain_text=message.extract_plain_text(),
            )
    async with get_session() as db_session:
        db_session.add(record)
        await db_session.commit()