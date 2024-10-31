from nonebot_plugin_apscheduler import scheduler
from .config import plugin_config
from nonebot import get_bot, require
from .utils import get_backend_bot, get_front_bot, send_combined_msg, print_ticket_info
from nonebot_plugin_orm import get_session
from sqlalchemy import select
from .model import Ticket, Status
from datetime import datetime


@scheduler.scheduled_job(trigger="interval", seconds=plugin_config.ticket_checking_interval)
async def ticket_check():
    bot = get_bot()
    front_bot = get_front_bot(bot)
    backend_bot = get_backend_bot(bot)
    # 发通知用发通知的号
    session = get_session()
    # 筛选出所有处于creating但是已经过期的工单
    async with session.begin():
        tickets = await session.execute(
            select(Ticket).filter(Ticket.status == Status.CREATING, Ticket.creating_expired_at < datetime.now()))
        tickets = tickets.scalars().all()
        for ticket in tickets:
            ticket_id = ticket.id
            ticket_customer_id = ticket.customer_id
            # 将工单状态更新为pending
            ticket.status = Status.PENDING
            # 转发消息给通知群
            await send_combined_msg(backend_bot, await print_ticket_info(ticket),
                                    target_group_id=plugin_config.notify_group)
            # 不要告诉机主转发出去了
            # await front_bot.send_private_msg(user_id=ticket_customer_id, message=plugin_config.second_reply)
        if tickets:
            await backend_bot.send_group_msg(group_id=plugin_config.notify_group,
                                             message=plugin_config.new_ticket_notify)

    # 筛选出所有处于alarming但是已经过期的工单
    async with session.begin():
        tickets = await session.execute(
            select(Ticket).filter(Ticket.status == Status.ALARMING, Ticket.alarming_expired_at < datetime.now()))
        tickets = tickets.scalars().all()
        for ticket in tickets:
            ticket_id = ticket.id
            ticket_customer_id = ticket.customer_id
            # 将工单状态更新为pending
            ticket.status = Status.PENDING
            # 转发消息给通知群
            await send_combined_msg(backend_bot, await print_ticket_info(ticket),
                                    target_group_id=plugin_config.notify_group)
            # 不要告诉机主他在催单
            # await front_bot.send_private_msg(user_id=ticket_customer_id, message=plugin_config.third_reply)
        if tickets:
            await backend_bot.send_group_msg(group_id=plugin_config.notify_group,
                                             message=plugin_config.alarm_ticket_notify)
