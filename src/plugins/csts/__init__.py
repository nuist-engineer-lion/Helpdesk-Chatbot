from nonebot import require, get_bot
from nonebot.rule import Rule
from nonebot import get_plugin_config, on_message, on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, PrivateMessageEvent, GroupMessageEvent, Message
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot.params import CommandArg
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

plugin_config = get_plugin_config(Config)

# 定义规则
async def is_engineer(event: MessageEvent) -> bool: # 名单或通知群内的人员为工程师
    if isinstance(event, GroupMessageEvent):
        return event.group_id == plugin_config.notify_group
    return event.get_user_id() in plugin_config.engineers

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
focus_ticket_matcher = on_command("focus", rule=is_engineer, aliases={"关注工单"}, priority=10, block=True)
unfocus_ticket_matcher = on_command("unfocus", rule=is_engineer, aliases={"取消关注工单"}, priority=10, block=True)

focus_ticket_map = {}

# 回复客户消息
@customer_message.handle()
async def reply_customer_message(bot: Bot, event: PrivateMessageEvent, session: async_scoped_session):
    customer_id = event.get_user_id()
    # 根据客户id获取最新的未关闭工单
    ticket = await session.execute(select(Ticket).filter(Ticket.customer_id == customer_id, Ticket.status != 'closed').order_by(Ticket.begin_at.desc()).limit(1))
    ticket = ticket.scalars().first()
    if ticket is None: # 如果没有工单
        # 创建工单
        ticket = Ticket(customer_id=customer_id, begin_at=datetime.fromtimestamp(event.time, cst), creating_expired_at=datetime.now() + timedelta(seconds=plugin_config.ticket_creating_alive_time))
        session.add(ticket)
        await session.commit()
        # 延时n秒，用于模拟工程师接单
        await bot.call_api("set_input_status", user_id=customer_id)
        await sleep(plugin_config.first_reply_delay)
        await customer_message.send(plugin_config.first_reply)
    elif ticket.status == 'creating':
        # 更新工单的创建过期时间
        ticket.creating_expired_at = datetime.now() + timedelta(seconds=plugin_config.ticket_creating_alive_time)
        await session.commit()
    elif ticket.status == 'alarming':
        # 更新工单的报警过期时间
        ticket.alarming_expired_at = datetime.now() + timedelta(seconds=plugin_config.ticket_alarming_alive_time)
        await session.commit()
    elif ticket.status == 'pending': # 如果没有工程师接单，设置为催单状态
        ticket.status = 'alarming'
        ticket.alarming_expired_at = datetime.now() + timedelta(seconds=plugin_config.ticket_alarming_alive_time)
        await session.commit()
        await bot.call_api("set_input_status", user_id=customer_id)
    elif ticket.status == 'processing':
        # 转发消息给工程师
        is_focus = focus_ticket_map.get(ticket.engineer_id) == ticket.id
        await send_forward_msg(
            bot, 
            [
                Message("接收到来自以下客户的消息" + ("" if is_focus else f"，请先focus此工单 {ticket.id:0>3} 后回复") + "！"),
                Message(f"[CQ:contact,type=qq,id={customer_id}]"), 
                event.message
            ], 
            target_user_id=ticket.engineer_id
        )

@scheduler.scheduled_job(trigger="interval", seconds=plugin_config.ticket_checking_interval)
async def ticket_check():
    bot = get_bot()
    session = get_session()
    # 筛选出所有处于creating但是已经过期的工单
    async with session.begin():
        tickets = await session.execute(select(Ticket).filter(Ticket.status == 'creating', Ticket.creating_expired_at < datetime.now()))
        tickets = tickets.scalars().all()
        for ticket in tickets:
            ticket_id = ticket.id
            ticket_customer_id = ticket.customer_id
            # 将工单状态更新为pending
            ticket.status = 'pending'
            await session.commit()
            # 转发消息给通知群和客户
            await send_forward_msg(bot, await print_ticket_info(ticket_id), target_group_id=plugin_config.notify_group, target_user_id=ticket_customer_id)
            await bot.send_private_msg(user_id=ticket_customer_id, message=plugin_config.second_reply)
        if tickets:
            await bot.send_group_msg(group_id=plugin_config.notify_group, message=plugin_config.new_ticket_notify)
    # 筛选出所有处于alarming但是已经过期的工单
    async with session.begin():
        tickets = await session.execute(select(Ticket).filter(Ticket.status == 'alarming', Ticket.alarming_expired_at < datetime.now()))
        tickets = tickets.scalars().all()
        for ticket in tickets:
            ticket_id = ticket.id
            ticket_customer_id = ticket.customer_id
            # 将工单状态更新为pending
            ticket.status = 'pending'
            await session.commit()
            # 转发消息给通知群
            await bot.send_private_msg(user_id=ticket_customer_id, message=plugin_config.third_reply)
            await send_forward_msg(bot, await print_ticket_info(ticket_id), target_group_id=plugin_config.notify_group)
        if tickets:
            await bot.send_group_msg(group_id=plugin_config.notify_group, message=plugin_config.alarm_ticket_notify)

@engineer_message.handle()
async def reply_engineer_message(bot: Bot, event: MessageEvent, session: async_scoped_session):
    engineer_id = event.get_user_id()
    if engineer_id not in focus_ticket_map:
        await engineer_message.finish("您未focus任何工单！可用指令列表：[alive|pending|all|my|myall|take|untake|close|focus|unfocus]")
    else:
        ticket_id = focus_ticket_map[engineer_id]
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            # no ticket record
            raise(ValueError)
        await bot.send_private_msg(user_id=int(ticket.customer_id), message=event.message) # 转发消息给客户

@get_alive_ticket_matcher.handle()
async def get_alive_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session):
    tickets = await session.execute(select(Ticket).filter(Ticket.status != 'closed').order_by(Ticket.begin_at.desc()))
    tickets = tickets.scalars().all()
    for ticket in tickets:
        await send_forward_msg(bot, await print_ticket_info(ticket.id), event=event)
    if not tickets:
        await get_alive_ticket_matcher.finish("没有活跃工单")

@get_pending_ticket_matcher.handle()
async def get_pending_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session):
    tickets = await session.execute(select(Ticket).filter(Ticket.status == 'pending').order_by(Ticket.begin_at.desc()))
    tickets = tickets.scalars().all()
    for ticket in tickets:
        await send_forward_msg(bot, await print_ticket_info(ticket.id), event=event)
    if not tickets:
        await get_pending_ticket_matcher.finish("没有未接工单")

@get_all_ticket_matcher.handle()
async def get_all_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session):
    tickets = await session.execute(select(Ticket).order_by(Ticket.begin_at.desc()))
    tickets = tickets.scalars().all()
    for ticket in tickets:
        await send_forward_msg(bot, await print_ticket_info(ticket.id), event=event)
    if not tickets:
        await get_all_ticket_matcher.finish("没有工单")

@get_my_alive_ticket_matcher.handle()
async def get_my_alive_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session):
    engineer_id = event.get_user_id()
    tickets = await session.execute(select(Ticket).filter(Ticket.engineer_id == engineer_id, Ticket.status != 'closed').order_by(Ticket.begin_at.desc()))
    tickets = tickets.scalars().all()
    for ticket in tickets:
        await send_forward_msg(bot, await print_ticket_info(ticket.id), event=event)
    if not tickets:
        await get_my_alive_ticket_matcher.finish("没有您的活跃工单")

@get_my_all_ticket_matcher.handle()
async def get_my_all_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session):
    engineer_id = event.get_user_id()
    tickets = await session.execute(select(Ticket).filter(Ticket.engineer_id == engineer_id).order_by(Ticket.begin_at.desc()))
    tickets = tickets.scalars().all()
    for ticket in tickets:
        await send_forward_msg(bot, await print_ticket_info(ticket.id), event=event)
    if not tickets:
        await get_my_all_ticket_matcher.finish("没有您的工单")

async def validate_ticket_id(args: Message, matcher, error_message: str = "请输入正确的工单号") -> int:
    arg = args.extract_plain_text().strip()
    try:
        ticket_id = int(arg)
    except:
        await matcher.finish(error_message)
    return ticket_id

@take_ticket_matcher.handle()
async def take_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session, args: Message = CommandArg()):
    engineer_id = event.get_user_id()
    ticket_id = await validate_ticket_id(args, take_ticket_matcher)
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await take_ticket_matcher.finish("工单不存在")
    if ticket.status != 'pending':
        await take_ticket_matcher.finish("该工单尚未创建完成或已被接单")
    ticket.status = 'processing'
    ticket.engineer_id = engineer_id
    await session.commit()
    # 通知客户
    await bot.send_private_msg(user_id=int(ticket.customer_id), message=f"工程师{engineer_id}已接单！您可以直接用此会话与工程师沟通，也可以添加工程师为好友！")
    await bot.send_private_msg(user_id=int(ticket.customer_id), message=f"[CQ:contact,type=qq,id={engineer_id}]")
    await take_ticket_matcher.send(f"接单成功！如需与客户沟通，可先focus此工单后直接回复我，我会将消息转发给客户！也可以添加客户为好友！")
    await take_ticket_matcher.finish(Message(f"[CQ:contact,type=qq,id={ticket.customer_id}]"))

@untake_ticket_matcher.handle()
async def untake_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session, args: Message = CommandArg()):
    engineer_id = event.get_user_id()
    ticket_id = await validate_ticket_id(args, untake_ticket_matcher)
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await untake_ticket_matcher.finish("工单不存在")
    if ticket.status != 'processing' or ticket.engineer_id != engineer_id:
        await untake_ticket_matcher.finish("您未接单或不是该工单的工程师")
    ticket.status = 'pending'
    ticket.engineer_id = None
    customer_id = int(ticket.customer_id)
    await session.commit()
    # 检查focus列表，如果有工程师focus此工单，则自动unfocus
    if focus_ticket_map.get(engineer_id) == ticket_id:
        focus_ticket_map.pop(engineer_id)
    # 通知客户
    await bot.send_private_msg(user_id=customer_id, message=f"工程师{engineer_id}有事暂时无法处理您的工单，您的工单已重新进入待接单状态！我们将优先为您安排其他工程师！")
    # 通知接单群
    await send_forward_msg(bot, await print_ticket_info(ticket_id), target_group_id=plugin_config.notify_group)
    await bot.send_group_msg(group_id=int(plugin_config.notify_group), message=f"工程师{engineer_id}有事暂时无法处理工单 {ticket_id:0>3} ，工单已重新进入待接单状态！")
    await untake_ticket_matcher.finish("放单成功！")

@close_ticket_matcher.handle()
async def close_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session, args: Message = CommandArg()):
    engineer_id = event.get_user_id()
    ticket_id = await validate_ticket_id(args, close_ticket_matcher)
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await close_ticket_matcher.finish("工单不存在")
    if ticket.status != 'processing' or ticket.engineer_id != engineer_id:
        await close_ticket_matcher.finish("您未接单或不是该工单的工程师")
    ticket.status = 'closed'
    ticket.end_at = datetime.fromtimestamp(event.time, cst)
    await session.commit()
    await send_forward_msg(bot, await print_ticket_info(ticket_id), target_group_id=plugin_config.notify_group, target_user_id=ticket.customer_id)
    # 通知客户
    await bot.send_private_msg(user_id=int(ticket.customer_id), message=f"工程师{engineer_id}已处理完您的工单，工单已关闭！")
    # 通知接单群
    await bot.send_group_msg(group_id=int(plugin_config.notify_group), message=f"工程师{engineer_id}已处理完工单{ticket_id}，工单已关闭！")
    await close_ticket_matcher.finish("关闭工单成功！")

@focus_ticket_matcher.handle()
async def focus_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session, args: Message = CommandArg()):
    engineer_id = event.get_user_id()
    ticket_id = await validate_ticket_id(args, focus_ticket_matcher)
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await focus_ticket_matcher.finish("工单不存在")
    if ticket.status != 'processing' or ticket.engineer_id != engineer_id:
        await focus_ticket_matcher.finish("您未接单或不是该工单的工程师")
    focus_ticket_map[engineer_id] = ticket_id
    await session.commit()
    await focus_ticket_matcher.finish("focus成功！接下啦请直接回复我，我会将消息转发给客户！")

@unfocus_ticket_matcher.handle()
async def unfocus_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session):
    engineer_id = event.get_user_id()
    if focus_ticket_map.get(engineer_id) is None:
        await unfocus_ticket_matcher.finish("您未focus任何工单")
    focus_ticket_map.pop(engineer_id)
    await unfocus_ticket_matcher.finish("unfocus成功！")