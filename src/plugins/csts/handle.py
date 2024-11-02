from argparse import Namespace
from typing import Annotated
from .matcher import *
from datetime import datetime, timedelta, UTC
from nonebot.typing import T_State
from nonebot_plugin_orm import async_scoped_session
from nonebot.params import CommandArg, ShellCommandArgs, ArgPlainText
from nonebot.exception import ParserExit
from nonebot import logger, on_notice
from asyncio import sleep
from .config import plugin_config
from pytz import timezone
from .utils import send_combined_msg, print_ticket_info, print_ticket, get_backend_bot, get_front_bot, send_forward_message, print_ticket_history
from nonebot.matcher import Matcher
from nonebot.permission import Permission, User
from nonebot.adapters import MessageTemplate
from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, PrivateMessageEvent, GroupMessageEvent, Message, MessageSegment, FriendRequestEvent
from .model import Engineer, Ticket
# 获取中国时区
cst = timezone('Asia/Shanghai')

default_schedule = "周六下午"

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
                    await customer_message.finish(event.message)

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
        await customer_message.send(plugin_config.first_reply)
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


# 捕获未能解析的工程师命令
@engineer_message.handle()
async def reply_engineer_message(bot: Bot, event: MessageEvent, session: async_scoped_session):
    await engineer_message.finish("输入 help 或 帮助 来获取帮助")


@help_matcher.handle()
async def help_message(bot: Bot, event: MessageEvent, session: async_scoped_session):
    await engineer_message.finish(
        """指令列表：(中文英文都可操作)
list(列出)|get(获取)|qq(搜索)
take(接单)|untake(放单)
close(关单)|qclose(qq关单)|fclose(强制关单)
scheduled(预约)|set_schedule(设置默认预约)
send(留言)
"""
    )


# 所有指定一个id函数共同进行处理
@close_ticket_matcher.handle()
@force_close_ticket_mathcer.handle()
@untake_ticket_matcher.handle()
@get_ticket_matcher.handle()
@take_ticket_matcher.handle()
@scheduled_ticket_matcher.handle()
@send_ticket_matcher.handle()
async def _(matcher: Matcher, session: async_scoped_session, args: Message = CommandArg()):
    if args.extract_plain_text():
        ticket_id = await validate_ticket_id(args.extract_plain_text(), matcher)
        ticket = await session.get(Ticket, ticket_id)
        if ticket:
            matcher.set_arg("id", args)
        else:
            await matcher.finish("工单不存在")

# 所有指定qq号的函数共同处理


@qid_close_ticket_matcher.handle()
@search_qq_matcher.handle()
async def _(matcher: Matcher, session: async_scoped_session, args: Message = CommandArg()):
    if args.extract_plain_text():
        ticket = await qq_get_db_ticket(args.extract_plain_text(), matcher, session)
        if ticket:
            matcher.set_arg("qid", args)
        else:
            await matcher.finish("工单不存在")


async def limit_mathcer_backend_bot(event: Event):
    if plugin_config.backend_bot:
        if event.self_id == int(plugin_config.backend_bot):
            return True
        else:
            return False
    else:
        return True


@close_ticket_matcher.permission_updater
@force_close_ticket_mathcer.permission_updater
@untake_ticket_matcher.permission_updater
@get_ticket_matcher.permission_updater
@take_ticket_matcher.permission_updater
@scheduled_ticket_matcher.permission_updater
@send_ticket_matcher.permission_updater
@qid_close_ticket_matcher.permission_updater
@help_matcher.permission_updater
@search_qq_matcher.permission_updater
@set_schedule_matcher.permission_updater
# 群内确认响应者是后端
async def _(event: Event, matcher: Matcher) -> Permission:
    return Permission(User.from_event(event=event, perm=Permission(limit_mathcer_backend_bot)))


@scheduled_ticket_matcher.got("id", prompt="单号？")
@send_ticket_matcher.got("id", "单号？")
@force_close_ticket_mathcer.got("id", prompt="单号？")
# 多级获取命令中途检查单号合法性
async def _(matcher: Matcher, session: async_scoped_session, id: str = ArgPlainText()):
    ticket = await get_db_ticket(id, matcher, session)


# 获取某一单的信息
@get_ticket_matcher.got("id", prompt="单号？")
async def get_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText()):
    ticket = await get_db_ticket(id, matcher, session)
    await matcher.send(await print_ticket(ticket))
    try:
        await send_forward_message(get_front_bot(bot), await print_ticket_history(ticket), event=event)
    except:
        await send_combined_msg(get_backend_bot(bot), await print_ticket_info(ticket), event=event)


# 处理接单
@take_ticket_matcher.got("id", prompt="单号？")
async def take_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText()):
    ticket = await get_db_ticket(id, matcher, session)
    engineer_id = event.get_user_id()
    if not ticket:
        await take_ticket_matcher.finish()
    if ticket.status not in [Status.PENDING, Status.SCHEDULED]:
        await take_ticket_matcher.finish("该工单尚未创建完成或已被接单")
    ticket.status = Status.PROCESSING
    ticket.engineer_id = engineer_id
    await session.commit()
    await session.refresh(ticket)
    # 通知客户
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id),
                                              message=f"工程师{engineer_id}已接单！您可以直接用此会话与工程师沟通，也可以添加工程师为好友！")
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id),
                                              message=f"[CQ:contact,type=qq,id={engineer_id}]")
    await take_ticket_matcher.send(f"接单成功！请添加客户为好友！解决后及时关单！")
    await take_ticket_matcher.finish(Message(f"[CQ:contact,type=qq,id={ticket.customer_id}]"))


# 处理放单
@untake_ticket_matcher.got("id", prompt="单号？")
async def untake_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText()):
    ticket = await get_db_ticket(id, matcher, session)
    engineer_id = event.get_user_id()
    if not ticket:
        await untake_ticket_matcher.finish()
    if ticket.status != Status.PROCESSING or ticket.engineer_id != engineer_id:
        await untake_ticket_matcher.finish("您未接单或不是该工单的工程师")
    ticket.status = Status.PENDING
    ticket.engineer_id = None
    customer_id = int(ticket.customer_id)
    await session.commit()
    # 通知客户
    await get_front_bot(bot).send_private_msg(user_id=customer_id,
                                              message=f"工程师{engineer_id}有事暂时无法处理您的工单，您的工单已重新进入待接单状态！我们将优先为您安排其他工程师！")
    # 通知接单群
    await matcher.send(await print_ticket(ticket))
    try:
        await send_forward_message(get_front_bot(bot), await print_ticket_history(ticket),
                                   target_group_id=plugin_config.notify_group)
    except:
        await send_combined_msg(get_backend_bot(bot), await print_ticket_info(ticket), target_group_id=plugin_config.notify_group)
    await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group),
                                              message=f"工程师{engineer_id}有事暂时无法处理工单 {id:0>3} ，工单已重新进入待接单状态！")
    await untake_ticket_matcher.finish("放单成功！")


# 处理关单
@close_ticket_matcher.got("id", prompt="单号？")
async def close_ticket_front(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText()):
    ticket = await get_db_ticket(id, matcher, session)
    engineer_id = event.get_user_id()
    if ticket.status == Status.SCHEDULED:
        ticket.engineer_id = engineer_id
        await session.commit()
        await close_ticket_matcher.send("完成本预定")
    elif ticket.status != Status.PROCESSING or ticket.engineer_id != engineer_id:
        await close_ticket_matcher.finish("您未接单或不是该工单的工程师")


@qid_close_ticket_matcher.got("qid", prompt="qq号？")
async def qid_close_ticket_front(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, qid: str = ArgPlainText()):
    ticket = await qq_get_db_ticket(qid, matcher, session)
    engineer_id = event.get_user_id()
    if ticket.status == Status.SCHEDULED:
        ticket.engineer_id = engineer_id
        await session.commit()
        await matcher.send("完成本预定")
    elif ticket.status != Status.PROCESSING or ticket.engineer_id != engineer_id:
        await matcher.finish("您未接单或不是该工单的工程师")


@qid_close_ticket_matcher.got("describe", prompt="请描述工单")
async def qclose_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, qid: str = ArgPlainText(),
                        describe: str = ArgPlainText()):
    if qid:
        ticket = await qq_get_db_ticket(qid, matcher, session)
    else:
        await matcher.finish("怎么会这样？")
    engineer_id = event.get_user_id()
    ticket.description = describe
    ticket.status = Status.CLOSED
    ticket.end_at = datetime.fromtimestamp(event.time, cst)

    await session.commit()
    await session.refresh(ticket)

    # 这玩意太吵了
    # await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group),
    #                                           message=await print_ticket(ticket))
    # 通知客户
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id),
                                              message=f"工程师{engineer_id}已处理完您的工单，感谢您的信任和支持！")
    # 通知接单群
    await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group),
                                              message=f"工程师{engineer_id}已处理完{id}！")
    await matcher.finish()


@close_ticket_matcher.got("describe", prompt="请描述工单")
async def close_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText(),
                       describe: str = ArgPlainText()):
    if id:
        ticket = await get_db_ticket(id, matcher, session)
    else:
        await matcher.finish("怎么会这样？")
    engineer_id = event.get_user_id()
    ticket.description = describe
    ticket.status = Status.CLOSED
    ticket.end_at = datetime.fromtimestamp(event.time, cst)

    await session.commit()
    await session.refresh(ticket)

    # 这玩意太吵了
    # await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group),
    #                                           message=await print_ticket(ticket))
    # 通知客户
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id),
                                              message=f"工程师{engineer_id}已处理完您的工单，感谢您的信任和支持！")
    # 通知接单群
    await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group),
                                              message=f"工程师{engineer_id}已处理完{id}！")
    await matcher.finish()


# 强制关单
@force_close_ticket_mathcer.got("describe", prompt="为什么强制关单？")
async def force_close_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText(),
                             describe: str = ArgPlainText()):
    ticket = await get_db_ticket(id, matcher, session)
    engineer_id = event.get_user_id()

    ticket.status = Status.CLOSED
    ticket.end_at = datetime.fromtimestamp(event.time, cst)
    ticket.description = "强制关单:" + describe
    await session.commit()
    await session.refresh(ticket)

    # await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group),
    #                                           message=await print_ticket(ticket))
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id), message=f"感谢您的支持与信任，再见。")
    await force_close_ticket_mathcer.finish(f"强制关单{ticket.id}")


# 处理预定
@scheduled_ticket_matcher.handle()
async def _(matcher:Matcher):
    await matcher.send("默认时间："+default_schedule)
    

@scheduled_ticket_matcher.got("usedefault", prompt=MessageTemplate("使用默认时间?(是/否)"))
async def schedule_use_default(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, usedefault: str = ArgPlainText()):
    if usedefault == "是":
        matcher.set_arg("scheduled_time", Message(default_schedule))


@scheduled_ticket_matcher.got("scheduled_time", prompt="预约时间地点？（会直接转发给机主）")
async def scheduled_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText(),
                           scheduled_time: str = ArgPlainText()):
    ticket = await get_db_ticket(id, matcher, session)
    if ticket.status == Status.CLOSED:
        await scheduled_ticket_matcher.finish("工单已经关闭，不能再次预约")
    ticket.status = Status.SCHEDULED
    ticket.scheduled_time = scheduled_time

    await session.commit()
    await session.refresh(ticket)
    # 发给顾客
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id), message=f"为您预约：{scheduled_time}")
    await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group), message=f"添加预约:{id}")

    await scheduled_ticket_matcher.finish()


# 留言处理
@send_ticket_matcher.got("send_msg", "留言内容？(输入一个q退出)")
async def send_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText(),
                      send_msg: str = ArgPlainText()):
    if send_msg == 'q':
        await matcher.finish()
    ticket = await get_db_ticket(id, matcher, session)
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id), message=send_msg)
    await matcher.finish("已转发留言")


# 按qq号搜索处理
@search_qq_matcher.got("qid", "qq号？")
async def search_qq(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, qid: str = ArgPlainText()):
    ticket = await qq_get_db_ticket(qid, matcher, session)
    await matcher.finish(await print_ticket(ticket))


@op_engineer_matcher.handle()
async def _(bot: Bot, event: MessageEvent, session: async_scoped_session,
            args: Annotated[ParserExit, ShellCommandArgs()]):
    await op_engineer_matcher.finish(engineer_parser.format_help())


@op_engineer_matcher.handle()
async def _(bot: Bot, event: MessageEvent, session: async_scoped_session,
            args: Annotated[Namespace, ShellCommandArgs()]):
    if args.sub == "add":
        if args.a:
            users = await bot.get_group_member_list(group_id=int(plugin_config.notify_group))
            for user in users:
                if str(user['user_id']) not in [str(plugin_config.backend_bot), str(plugin_config.front_bot)]:
                    engineer = Engineer(engineer_id=str(user['user_id']))
                    session.add(engineer)
        else:
            if not args.ids:
                await op_engineer_matcher.finish(engineer_parser_add.format_help())
            for id in args.ids:
                engineer = Engineer(engineer_id=id)
                session.add(engineer)
        await session.commit()
    elif args.sub == "del":
        if not args.ids:
            await op_engineer_matcher.finish(engineer_parser_del.format_help())
        for id in args.ids:
            engineer = (await session.execute(select(Engineer).where(Engineer.engineer_id == id))).scalar_one_or_none()
            if engineer:
                await session.delete(engineer)
        await session.commit()
    elif args.sub == "list":
        engineers = (await session.execute(select(Engineer))).scalars().all()
        msg = []
        for engineer in engineers:
            msg += Message(engineer.engineer_id)
        await send_combined_msg(get_backend_bot(bot), msgs=msg, event=event)
    else:
        await op_engineer_matcher.finish(engineer_parser.format_usage())


# list 错误处理
@list_ticket_matcher.handle()
async def _(bot: Bot, event: MessageEvent, session: async_scoped_session,
            args: Annotated[ParserExit, ShellCommandArgs()]):
    await list_ticket_matcher.finish(list_parser.format_help())


# 处理list
@list_ticket_matcher.handle()
async def list_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session,
                      args: Annotated[Namespace, ShellCommandArgs()]):
    if args.type not in Types_Ticket.keys():
        await list_ticket_matcher.finish(list_parser.format_help())
    tickets = (await session.execute(Types_Ticket[args.type](event.get_user_id()))).scalars().all()
    if not tickets:
        await list_ticket_matcher.finish("没有")
    if args.a:
        for ticket in tickets:
            await list_ticket_matcher.send(await print_ticket(ticket))
            try:
                await send_forward_message(get_front_bot(bot), await print_ticket_history(ticket),
                                           target_group_id=plugin_config.notify_group)
            except:
                await send_combined_msg(get_backend_bot(bot), await print_ticket_info(ticket), target_group_id=plugin_config.notify_group)
    else:
        msgs = []
        for ticket in tickets:
            msgs.append(await print_ticket(ticket))
        await send_combined_msg(get_backend_bot(bot), msgs=msgs, event=event)


@set_schedule_matcher.handle()
@set_schedule_matcher.got("time", "输入时间地点")
async def set_schedule(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, time: str = ArgPlainText()):
    global default_schedule
    default_schedule = time
    await matcher.finish("设置完成")


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


@who_asked_matcher.handle()
# 谁问你了
async def who_asked(bot: Bot, event: MessageEvent):
    await who_asked_matcher.finish(Message(f"[CQ:at,qq={event.get_user_id()}] 谁问你了"))


# 处理好友添加请求
async def _friend_request(bot: Bot, event: Event, state: T_State) -> bool:
    return isinstance(event, FriendRequestEvent)
friend_request = on_notice(_friend_request, priority=1, block=True)


@friend_request.handle()
async def _(bot: Bot, event: FriendRequestEvent):
    await event.approve(bot)
