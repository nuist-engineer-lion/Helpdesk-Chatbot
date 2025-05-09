from email import message
from pytz import timezone
from datetime import datetime
from nonebot_plugin_orm import async_scoped_session, get_session
from nonebot_plugin_chatrecorder import get_message_records
from typing import Optional
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent, PrivateMessageEvent, Message, GroupMessageEvent
from nonebot.internal.adapter.bot import Bot
from nonebot_plugin_chatrecorder import MessageRecord
from sqlalchemy import select
from nonebot import get_bot, require
from .config import plugin_config
from .model import Ticket


# 获取中国时区
cst = timezone('Asia/Shanghai')

def to_node(name:str,user_id:int|str,msg: MessageRecord|Message|list[dict]|str):
    return {"type": "node", "data": {"name": name, "user_id": user_id, "content": msg}}

async def send_forward_msg(
        bot: Bot,
        messages_nodes:list[dict],
        event: Optional[MessageEvent] = None,
        target_group_id: Optional[str | int] = None,
        target_user_id: Optional[str | int] = None,block_event: bool = False):
    if target_group_id:
        await bot.call_api(
            "send_group_forward_msg", group_id=target_group_id, messages=messages_nodes
        )
    if target_user_id:
        await bot.call_api(
            "send_private_forward_msg", user_id=target_user_id, messages=messages_nodes
        )
    if not block_event and event:
        if isinstance(event, PrivateMessageEvent):
            await bot.call_api(
                "send_private_forward_msg", user_id=event.user_id, messages=messages_nodes
            )
        elif isinstance(event, GroupMessageEvent):
            await bot.call_api(
                "send_group_forward_msg", group_id=event.group_id, messages=messages_nodes
            )

async def gen_message_node_by_ticket(
        self_id: int|str,
        ticket: Ticket,
        plaintext: bool=False
        ) -> list[dict]:
    message_records=await get_messages_records(ticket)
    messages = []
    if not plaintext:
        for msg in message_records:
            if msg.type=="message_sent":
                messages.append(to_node("工程师",self_id, msg.message))
            else:
                messages.append(to_node("机主",ticket.customer_id,msg.message))
    else:
        for msg in message_records:
            if msg.type=="message_sent":
                messages.append(to_node("工程师",self_id, msg.plain_text))
            else:
                messages.append(to_node("机主",ticket.customer_id,msg.plain_text))        
    return messages

def gen_message_node_by_msgs(
        msgs: list[Message],
) -> list[dict]:
    message_nodes = [to_node("CM",str(plugin_config.front_bot),msg) for msg in msgs]
    return message_nodes
    
def gen_message_node_by_id(msgs: list[MessageRecord]) -> list[dict]:
    def to_node(msg: MessageRecord):
        return {"type": "node", "data": {"id": msg.message_id}}
    message_nodes = [to_node(msg) for msg in msgs]
    return message_nodes


def print_ticket(ticket: Ticket) -> Message:
    if not ticket:
        # no ticket record
        raise (ValueError)
    msg = f'工单:{ticket.id}\n状态:{ticket.status}\n机主:{ticket.customer_id}\n'
    if ticket.engineer_id:
        msg = msg+f'工程师:{ticket.engineer_id}\n'
    if ticket.begin_at:
        msg = msg+f'创建时间:{ticket.begin_at.strftime("%Y-%m-%d %H:%M:%S")}\n'
    if ticket.end_at:
        msg = msg+f'结束时间:{ticket.end_at.strftime("%Y-%m-%d %H:%M:%S")}\n'
    if ticket.scheduled_time:
        msg = msg+f'预约时间:{ticket.scheduled_time}\n'
    if ticket.description:
        msg = msg+f'描述:{ticket.description}'
    return Message(msg)


async def get_messages_records(ticket: Ticket) -> list[MessageRecord]:
    if not ticket:
        raise (ValueError)
    # 下面打印历史消息
    if plugin_config.front_bot:
        bot_id = [str(plugin_config.front_bot)]
    else:
        bot_id = None
    ticket_end_at = None if not ticket.end_at else cst.localize(
        ticket.end_at)
    message_records = await get_message_records(id1s=[ticket.customer_id], time_start=cst.localize(ticket.begin_at), time_stop=ticket_end_at, id2s=[''], bot_ids=bot_id)
    return message_records


async def print_ticket_info(ticket: Ticket) -> list[Message]:
    msgs = []
    if not ticket:
        # no ticket record
        raise (ValueError)
    ticket_id = ticket.id
    ticket_status = ticket.status
    ticket_begin_at = cst.localize(ticket.begin_at)
    ticket_end_at = None if not ticket.end_at else cst.localize(
        ticket.end_at)
    ticket_customer_id = ticket.customer_id
    ticket_engineer_id = ticket.engineer_id
    ticket_scheduled_time = ticket.scheduled_time
    ticket_description = ticket.description
    msgs.append(Message(f"工单号: {ticket_id:0>3}"))
    msgs.append(Message(f"状态: {ticket_status}"))
    msgs.append(
        Message("创建时间: " + ticket_begin_at.strftime("%Y-%m-%d %H:%M:%S")))
    if ticket_end_at:
        msgs.append(
            Message("结束时间: " + ticket_end_at.strftime("%Y-%m-%d %H:%M:%S")))
    if ticket_scheduled_time:
        msgs.append(Message("预约时间: " + ticket_scheduled_time))
    msgs.append(Message(f"机主名片[CQ:contact,type=qq,id={ticket_customer_id}]"))
    if ticket_engineer_id:
        msgs.append(
            Message(f"工程师名片[CQ:contact,type=qq,id={ticket_engineer_id}]"))
    if ticket_description:
        msgs.append(
            Message(f'描述:{ticket_description}')
        )
    # 下面打印历史消息
    if plugin_config.front_bot:
        bot_id = [str(plugin_config.front_bot)]
    else:
        bot_id = None
    message_records = await get_message_records(id1s=[ticket_customer_id], time_start=ticket_begin_at, time_stop=ticket_end_at, id2s=[''], bot_ids=bot_id)
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


def get_backend_bot(bot):
    if plugin_config.backend_bot:
        return get_bot(str(plugin_config.backend_bot))
    else:
        return bot


def get_front_bot(bot):
    if plugin_config.front_bot:
        return get_bot(str(plugin_config.front_bot))
    else:
        return bot


async def validate_ticket_id(args: str, matcher: Matcher, error_message: str = "请输入正确的工单号") -> int:
    arg = args.strip()
    try:
        ticket_id = int(arg)
    except:
        await matcher.finish(error_message)
    return ticket_id


async def get_db_ticket(id: str, matcher: Matcher, session: async_scoped_session, error_message: str = "工单不存在"):
    ticket = await session.get(Ticket, id)
    if not ticket:
        await matcher.finish(error_message)
    else:
        return ticket


async def qq_get_db_ticket(qid: str, matcher: Matcher, session: async_scoped_session, error_message: str = "工单不存在"):
    ticket = (await session.execute(select(Ticket).where(Ticket.customer_id == qid).order_by(Ticket.begin_at.desc()).limit(1))).scalar_one_or_none()
    if not ticket:
        await matcher.finish(error_message)
    else:
        return ticket
