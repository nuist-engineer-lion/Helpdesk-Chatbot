from datetime import datetime, timedelta
import uuid

from nonebot.adapters.onebot.v11 import Bot, MessageEvent, PrivateMessageEvent, Message
from nonebot_plugin_chatrecorder import get_messages
from nonebot.adapters import Event
from nonebot import require
from nonebot.params import Depends
import random
from asyncio import sleep
from . import model

from sqlalchemy import select

require("nonebot_plugin_orm")
from nonebot_plugin_orm import SQLDepends, async_scoped_session


async def send_forward_msg(
        bot: Bot,
        event: MessageEvent,
        name: str,
        uin: str,
        msgs: list[Message],
        target_group_id: str = None,
):
    """
    发送合并转发消息。
    * `bot`: Bot 实例
    * `event`: 消息事件
    * `name`: 呢称
    * `uin`: QQ UID
    * `msgs`: 消息列表
    """

    def to_node(msg: Message):
        return {"type": "node", "data": {"name": name, "uin": uin, "content": msg}}

    messages = [to_node(msg) for msg in msgs]
    if target_group_id:
        await bot.call_api(
            "send_group_forward_msg", group_id=target_group_id, messages=messages
        )
    is_private = isinstance(event, PrivateMessageEvent)
    if(is_private):
        await bot.call_api(
            "send_private_forward_msg", user_id=event.user_id, messages=messages
        )
    else:
        await bot.call_api(
            "send_group_forward_msg", group_id=event.group_id, messages=messages
        )

sample_ticket = {
    "ticket_id": str(uuid.uuid4()),
    "begin_at": datetime.now(),
    "end_at": datetime.now(),
    "status": "creating",
    "creating_expired_at": datetime.now(),
    "processing_expired_at": datetime.now(),
    "engineer_id": "",
    "customer_id": "",
}

tickets = {}

async def init_tickets(sess: async_scoped_session):
    # not empty then not init
    if tickets:
        return
    # add all
    db_tickets = (await sess.execute(select(model.Ticket))).scalars()
    for ticket in db_tickets:
        create_mem_ticket(ticket.uid,ticket.customer_id,ticket.begin_at)

def create_mem_ticket(ticket_id: str,customer_id: str, begin_at: datetime):
    tickets[ticket_id] = {
        "ticket_id": ticket_id,
        "begin_at": begin_at,
        "end_at": begin_at + timedelta(days=9999),
        "status": "creating",
        "creating_expired_at": begin_at,
        "processing_expired_at": begin_at,
        "engineer_id": "",
        "customer_id": customer_id,
    }
    return tickets

async def create_ticket(customer_id: str, begin_at: datetime,
    sess: async_scoped_session) -> str:
    ticket_id = str(uuid.uuid4())
    create_mem_ticket(ticket_id,customer_id,begin_at)
    db_ticket = model.Ticket(uid=ticket_id,
                               customer_id=customer_id,
                               begin_at=begin_at,
                               end_at=begin_at + timedelta(days=9999),
                               creating_expired_at=begin_at,
                               processing_expired_at=begin_at,
                               )
    try:
        sess.add(db_ticket)
        await sess.commit()
    finally:
        print(tickets)
        return ticket_id

async def get_ticket(ticket_id: str,sess: async_scoped_session) -> dict|None:
    try:
        return tickets[ticket_id]
    except:
        return None

async def update_ticket(ticket_id: str,sess: async_scoped_session, **kwargs):
    tickets[ticket_id].update(kwargs)
    
    db_ticket = (await sess.execute(select(model.Ticket).where(model.Ticket.uid==ticket_id))).scalar()
    # magic!
    for k,v in kwargs.items():
        setattr(db_ticket,k,v)
    await sess.commit()
    
    print(tickets)

def get_all_tickets() -> list:
    return tickets.keys()

def get_ticket_by_engineer_id(engineer_id: str) -> str|None:
    for ticket_id in tickets.keys():
        if tickets[ticket_id]['engineer_id'] == engineer_id:
            return ticket_id
    return None

def get_latest_active_ticket_by_user_id(user_id: str) -> str|None:
    # 先把对应user_id的活跃工单找出来
    active_tickets = []
    for ticket_id in tickets.keys():
        if tickets[ticket_id]['customer_id'] == user_id and tickets[ticket_id]['status'] != 'closed':
            active_tickets.append(ticket_id)
    # 没有活跃工单
    if len(active_tickets) == 0:
        return None
    # 有活跃工单
    # 找出最新的工单，按照begin_at排序
    return sorted(active_tickets, key=lambda x: tickets[x]['begin_at'], reverse=True)[0]

async def print_ticket(event, bot, ticket_id,sess: async_scoped_session, target_group_id=None, delay=0):
    # 延时3~5秒，用于模拟工程师接单
    print("被调用")
    await sleep(delay)
    ticket = await get_ticket(ticket_id,sess)
    msgs = []
    msgs.append(Message(ticket_id))
    msgs.append(Message("状态：" + ticket['status']))
    msgs.append(Message("创建时间：" + ticket['begin_at'].strftime("%Y-%m-%d %H:%M:%S")))
    msgs.append(Message("结束时间：" + ticket['end_at'].strftime("%Y-%m-%d %H:%M:%S")))
    msgs.append(Message("客户id：" + ticket['customer_id']))
    msgs.append(Message("工程师id：" + ticket['engineer_id']))
    msgs.extend(await get_messages(id1s=[ticket["customer_id"]], time_start=ticket["begin_at"] - timedelta(minutes=2), time_stop=ticket["end_at"] + timedelta(minutes=2)))
    await send_forward_msg(bot, event, f"客户{ticket['customer_id']}", ticket['customer_id'], msgs, target_group_id)