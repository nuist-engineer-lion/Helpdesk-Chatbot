from nonebot.adapters.onebot.v11 import Bot, MessageEvent, PrivateMessageEvent, Message
from .model import Ticket
from nonebot import require
require("nonebot_plugin_chatrecorder")
from nonebot_plugin_chatrecorder import get_message_records
from nonebot_plugin_orm import get_session
from datetime import datetime
# 获取中国时区
from pytz import timezone
cst = timezone('Asia/Shanghai')

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
        ticket_id = ticket.id
        ticket_status = ticket.status
        ticket_begin_at = cst.localize(ticket.begin_at)
        ticket_end_at = None if not ticket.end_at else cst.localize(ticket.end_at)
        ticket_customer_id = ticket.customer_id
        ticket_engineer_id = ticket.engineer_id
    msgs.append(Message(f"工单号: {ticket_id:0>3}"))
    msgs.append(Message(f"状态: {ticket_status}"))
    msgs.append(Message("创建时间: " + ticket_begin_at.strftime("%Y-%m-%d %H:%M:%S")))
    if ticket_end_at:
        msgs.append(Message("结束时间: " + ticket_end_at.strftime("%Y-%m-%d %H:%M:%S")))
    msgs.append(Message(f"机主名片[CQ:contact,type=qq,id={ticket_customer_id}]"))
    if ticket_engineer_id:
        msgs.append(Message(f"工程师名片[CQ:contact,type=qq,id={ticket_engineer_id}]"))
    # 下面打印历史消息
    message_records = await get_message_records(id1s=[ticket_customer_id], time_start=ticket_begin_at, time_stop=ticket_end_at)
    # Python
    if not message_records:
        return msgs
    
    for i, record in enumerate(message_records):
        if i == 0 or record.type != message_records[i-1].type:
            if record.type == "message_sent":
                msgs.append(Message("~~~~~~~Engineer~~~~~~~"))
            else:
                msgs.append(Message("---------Customer---------"))
        msgs.append(record.message)
    return msgs