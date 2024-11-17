from asyncio import sleep
from pytz import timezone
from ..utils import get_backend_bot, get_front_bot, send_combined_msg
from ..matcher import customer_message
from ..model import Ticket, Status
from ..config import plugin_config
from nonebot_plugin_orm import async_scoped_session
from nonebot.adapters.onebot.v11 import Bot, PrivateMessageEvent, Message
from nonebot import logger
from sqlalchemy import select
from datetime import datetime, timedelta

cst = timezone('Asia/Shanghai')

# 回复客户消息


@customer_message.handle()
async def reply_customer_message(bot: Bot, event: PrivateMessageEvent, session: async_scoped_session):
    if event.message.extract_plain_text() in "请求添加你为好友":
        await customer_message.finish()
    customer_id = event.get_user_id()
    # 根据客户id获取最新的未关闭工单
    ticket = await session.execute(
        select(Ticket).filter(Ticket.customer_id == customer_id, Ticket.status != Status.CLOSED).order_by(
            Ticket.begin_at.desc()).limit(1))
    ticket = ticket.scalars().first()
    if ticket is None:  # 如果没有工单
        # 检查是否存在最近刚刚关闭的工单
        logger.info("发生关单后发消息")
        last_ticket = (await session.execute(
            select(Ticket).filter(Ticket.customer_id == customer_id, Ticket.status == Status.CLOSED).order_by(
                Ticket.begin_at.desc()).limit(1)
        )).scalars().first()

        # 如果有上一次的工单则进行判断
        if last_ticket:
            if last_ticket.end_at:
                # 如果小于预定时间
                if last_ticket.end_at > datetime.now() - timedelta(
                    seconds=plugin_config.ticket_create_interval
                ):
                    await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group), message=Message(f"{customer_id}在工单{last_ticket.id}结束后说:"))
                    await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group), message=event.message)
                    await customer_message.finish()

        # 获取客户第一次回复的消息内容并判断字数
        first_reply_text = event.message.extract_plain_text()
        if len(first_reply_text) <= plugin_config.len_first_reply:
            to_send_first_reply = plugin_config.first_reply_S
        else:
            to_send_first_reply = plugin_config.first_reply_L

        # 如果没有则直接创建
        # 创建工单
        ticket = Ticket(customer_id=customer_id, begin_at=datetime.fromtimestamp(event.time, cst),
                        creating_expired_at=datetime.now() + timedelta(
                            seconds=plugin_config.ticket_creating_alive_time))
        session.add(ticket)
        await session.commit()
        logger.info("创建工单已经提交到数据库")
        # 延时n秒，用于模拟工程师接单
        try:
            await get_front_bot(bot).call_api("set_input_status", user_id=customer_id)
        except:
            logger.warning("不支持set_input_status api")
        await sleep(plugin_config.first_reply_delay)
        await customer_message.send(to_send_first_reply)
    elif ticket.status == Status.CREATING:
        # 更新工单的创建过期时间
        ticket.creating_expired_at = datetime.now(
        ) + timedelta(seconds=plugin_config.ticket_creating_alive_time)
        await session.commit()
    elif ticket.status == Status.ALARMING:
        # 更新工单的报警过期时间
        ticket.alarming_expired_at = datetime.now(
        ) + timedelta(seconds=plugin_config.ticket_alarming_alive_time)
        await session.commit()
    elif ticket.status == Status.PENDING:  # 如果没有工程师接单，设置为催单状态
        ticket.status = Status.ALARMING
        ticket.alarming_expired_at = datetime.now(
        ) + timedelta(seconds=plugin_config.ticket_alarming_alive_time)
        await session.commit()
        logger.info("发生催单")
        try:
            await bot.call_api("set_input_status", user_id=customer_id)
        except:
            logger.warning("不支持set_input_status api")
    elif ticket.status == Status.PROCESSING:
        # 转发消息给工程师
        # is_focus = focus_ticket_map.get(ticket.engineer_id) == ticket.id
        await send_combined_msg(
            get_backend_bot(bot),
            [
                Message("接收到来自以下客户的消息" + f" {ticket.id:0>3} " + "！"),
                Message(f"[CQ:contact,type=qq,id={customer_id}]"),
                event.message
            ],
            target_user_id=ticket.engineer_id
        )
    elif ticket.status == Status.SCHEDULED:
        await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group), message=f"预定过的{ticket.id} {ticket.customer_id}说:")
        await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group), message=event.message)
