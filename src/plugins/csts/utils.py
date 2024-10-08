from nonebot.adapters.onebot.v11 import Bot, MessageEvent, PrivateMessageEvent, Message
from .model import Ticket
from nonebot import require
require("nonebot_plugin_chatrecorder")
from nonebot_plugin_chatrecorder import get_message_records
from nonebot_plugin_orm import get_session
from datetime import timedelta

async def send_forward_msg(
        bot: Bot,
        msgs: list[Message],
        event: MessageEvent = None,
        target_group_id: str = None,
        target_user_id: str = None,
        block_event: bool = False,
):
    """
    发送合并转发消息。
    * `bot`: Bot 实例
    * `event`: 消息事件
    * `msgs`: 消息列表
    * `target_group_id`: 目标群号
    * `target_user_id`: 目标用户号
    * `block_event`: 是否阻止用event返回消息
    """

    def to_node(msg: Message):
        return {"type": "node", "data": {"name": "name", "uin": "10010", "content": msg}}

    messages = [to_node(msg) for msg in msgs]
    if target_group_id:
        await bot.call_api(
            "send_group_forward_msg", group_id=target_group_id, messages=messages
        )
    if target_user_id:
        await bot.call_api(
            "send_private_forward_msg", user_id=target_user_id, messages=messages
        )
    if not block_event and event:
        is_private = isinstance(event, PrivateMessageEvent)
        if(is_private):
            await bot.call_api(
                "send_private_forward_msg", user_id=event.user_id, messages=messages
            )
        else:
            await bot.call_api(
                "send_group_forward_msg", group_id=event.group_id, messages=messages
            )

async def print_ticket_info(ticket_id: int) -> list[Message]:
    session = get_session()
    msgs = []
    async with session.begin():
        ticket = await session.get(Ticket, ticket_id)
        msgs.append(Message(f"工单号: {ticket.id:0>3}"))
        msgs.append(Message(f"状态: {ticket.status}"))
        msgs.append(Message("创建时间: " + ticket.begin_at.strftime("%Y-%m-%d %H:%M:%S")))
        if ticket.end_at:
            msgs.append(Message("结束时间: " + ticket.end_at.strftime("%Y-%m-%d %H:%M:%S")))
        msgs.append(Message(f"机主名片[CQ:contact,type=qq,id={ticket.customer_id}]"))
        if ticket.engineer_id:
            msgs.append(Message(f"工程师名片[CQ:contact,type=qq,id={ticket.engineer_id}]"))
        # 下面打印历史消息
        message_records = await get_message_records(id1s=[ticket.customer_id], time_start=ticket.begin_at - timedelta(hours=8), time_stop=None if ticket.end_at is None else ticket.end_at - timedelta(hours=8))
        print(message_records)
        if not message_records:
            return msgs
        if message_records[0].type == "message_sent":
            msgs.append(Message("~~~~~Engineer~~~~~"))
        else:
            msgs.append(Message("-----Customer-----"))
        msgs.append(message_records[0].message)
        for i in range(1, len(message_records)):
            if message_records[i].type != message_records[i-1].type:
                if message_records[i].type == "message_sent":
                    msgs.append(Message("~~~~~Engineer~~~~~"))
                else:
                    msgs.append(Message("-----Customer-----"))
            msgs.append(message_records[i].message)
        return msgs