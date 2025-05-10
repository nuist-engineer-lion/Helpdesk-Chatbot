from nonebot_plugin_apscheduler import scheduler
from .config import plugin_config
from nonebot import get_bot, require
from .utils import gen_message_node_by_ticket, get_backend_bot, get_front_bot, print_ticket, get_messages_records, gen_message_node_by_msgs, print_ticket_info, gen_message_node_by_id, send_forward_msg
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
        if tickets:
            await backend_bot.send_group_msg(group_id=plugin_config.notify_group,
                                             message=plugin_config.new_ticket_notify)
        for ticket in tickets:
            # 将工单状态更新为pending
            ticket.status = Status.PENDING
            # 转发消息给通知群
            await backend_bot.send_group_msg(group_id=int(plugin_config.notify_group),message = print_ticket(ticket))
            try:
                await send_forward_msg(backend_bot,await gen_message_node_by_ticket(get_front_bot(bot).self_id,ticket),target_group_id=plugin_config.notify_group)
            except:
                await send_forward_msg(backend_bot, await gen_message_node_by_ticket(get_front_bot(bot).self_id, ticket,True), target_group_id=plugin_config.notify_group)
        

    # 筛选出所有处于alarming但是已经过期的工单
    async with session.begin():
        tickets = await session.execute(
            select(Ticket).filter(Ticket.status == Status.ALARMING, Ticket.alarming_expired_at < datetime.now()))
        tickets = tickets.scalars().all()
        if tickets:
            await backend_bot.send_group_msg(group_id=plugin_config.notify_group,
                                             message=plugin_config.alarm_ticket_notify)

        for ticket in tickets:
            # 将工单状态更新为pending
            ticket.status = Status.PENDING
            # 转发消息给通知群
            await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group),message = print_ticket(ticket))
            try:
                await send_forward_msg(backend_bot,await gen_message_node_by_ticket(get_front_bot(bot).self_id,ticket),target_group_id=plugin_config.notify_group)
            except:
                await send_forward_msg(backend_bot, await gen_message_node_by_ticket(get_front_bot(bot).self_id, ticket,True), target_group_id=plugin_config.notify_group)
