from nonebot import require, get_bot
from nonebot.rule import Rule
from nonebot import get_plugin_config, on_message, on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, PrivateMessageEvent, GroupMessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from datetime import datetime, timedelta, UTC
from nonebot_plugin_orm import async_scoped_session, get_session
from sqlalchemy import select
from asyncio import sleep
# 获取中国时区
from pytz import timezone
cst = timezone('Asia/Shanghai')

from .config import Config
from .model import Ticket
from .utils import send_forward_msg, print_ticket_info

from nonebot import require

require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="CSTS",
    description="客服工单系统",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

# 定义规则
async def is_engineer(event: MessageEvent) -> bool: # 名单或通知群内的人员为工程师
    if isinstance(event, GroupMessageEvent):
        return event.group_id == config.notify_group
    return event.get_user_id() in config.engineers

async def is_customer(event: PrivateMessageEvent) -> bool:
    return await is_engineer(event) is False

# 定义响应器
customer_message = on_message(rule=is_customer & to_me(), priority=100)
engineer_message = on_message(rule=is_engineer & to_me(), priority=100)
get_alive_ticket_matcher = on_command("alive", rule=is_engineer, aliases={"活跃工单", "工单"}, priority=10, block=True)
get_pending_ticket_matcher = on_command("pending", rule=is_engineer, aliases={"未接工单"}, priority=10, block=True)
get_all_ticket_matcher = on_command("all", rule=is_engineer, aliases={"所有工单"}, priority=10, block=True)
get_my_alive_ticket_matcher = on_command("my", rule=is_engineer, aliases={"我的工单"}, priority=10, block=True)
get_my_all_ticket_matcher = on_command("myall", rule=is_engineer, aliases={"我的所有工单"}, priority=10, block=True)
take_ticket_matcher = on_command("take", rule=is_engineer, aliases={"接单"}, priority=10, block=True)
untake_ticket_matcher = on_command("untake", rule=is_engineer, aliases={"放单"}, priority=10, block=True)
close_ticket_matcher = on_command("close", rule=is_engineer, aliases={"关闭工单"}, priority=10, block=True)

# 回复客户消息
@customer_message.handle()
async def reply_customer_message(bot: Bot, event: PrivateMessageEvent, session: async_scoped_session):
    customer_id = event.get_user_id()
    # 根据客户id获取最新的未关闭工单
    ticket = await session.execute(select(Ticket).filter(Ticket.customer_id == customer_id, Ticket.status != 'closed').order_by(Ticket.created_at.desc()).limit(1))
    ticket = ticket.scalars().first()
    if ticket is None: # 如果没有工单
        # 创建工单
        ticket = Ticket(customer_id=customer_id, begin_at=datetime.fromtimestamp(event.time, cst), creating_expired_at=datetime.now() + timedelta(seconds=config.ticket_creating_alive_time))
        session.add(ticket)
        await session.commit()
        # 延时3秒，用于模拟工程师接单
        await sleep(3)
        await customer_message.send("您好，欢迎联系咨询，请详细描述您的问题，我们会尽快为您解答。")
    elif ticket.status == 'creating':
        # 更新工单的创建过期时间
        ticket.creating_expired_at = datetime.now() + timedelta(seconds=config.ticket_creating_alive_time)
        await session.commit()
    elif ticket.status == 'alarming':
        # 更新工单的报警过期时间
        ticket.alarming_expired_at = datetime.now() + timedelta(seconds=config.ticket_alarming_alive_time)
        await session.commit()
    elif ticket.status == 'pending': # 如果没有工程师接单，设置为催单状态
        ticket.status = 'alarming'
        ticket.alarming_expired_at = datetime.now() + timedelta(seconds=config.ticket_alarming_alive_time)
        await session.commit()
    elif ticket.status == 'processing':
        # 转发消息给工程师
        await bot.send_private_msg(user_id=ticket.engineer_id, message=event.message)

@engineer_message.handle()
async def reply_engineer_message(bot: Bot, event: MessageEvent, session: async_scoped_session):
    engineer_id = event.get_user_id()
    plain_message = event.get_plaintext()

@scheduler.scheduled_job(trigger="interval", seconds=config.ticket_checking_interval)
async def ticket_check():
    bot = get_bot()
    session = get_session()
    # 筛选出所有处于creating但是已经过期的工单
    async with session.begin():
        tickets = await session.execute(select(Ticket).filter(Ticket.status == 'creating', Ticket.creating_expired_at < datetime.now()))
        tickets = tickets.scalars().all()
        for ticket in tickets:
            ticket_id = ticket.id
            # 将工单状态更新为pending
            ticket.status = 'pending'
            await session.commit()
            # 转发消息给通知群
            await send_forward_msg(bot, await print_ticket_info(ticket_id), target_group_id=config.notify_group)
            await bot.send_group_msg(group_id=config.notify_group, message=config.new_ticket_notify)
    # 筛选出所有处于alarming但是已经过期的工单
    async with session.begin():
        tickets = await session.execute(select(Ticket).filter(Ticket.status == 'alarming', Ticket.alarming_expired_at < datetime.now()))
        tickets = tickets.scalars().all()
        for ticket in tickets:
            ticket_id = ticket.id
            # 将工单状态更新为pending
            ticket.status = 'pending'
            await session.commit()
            # 转发消息给通知群
            await send_forward_msg(bot, await print_ticket_info(ticket_id), target_group_id=config.notify_group)
            await bot.send_group_msg(group_id=config.notify_group, message=config.alarm_ticket_notify)
            