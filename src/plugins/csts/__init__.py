from nonebot_plugin_apscheduler import scheduler
from typing import Annotated
from nonebot import get_bots, logger, on_keyword, on_shell_command, require, get_bot, get_plugin_config, on_message, on_command
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, PrivateMessageEvent, GroupMessageEvent, Message
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me, ArgumentParser, Namespace
from nonebot.permission import SUPERUSER
from nonebot.params import CommandArg, ShellCommandArgs, ArgPlainText
from nonebot.exception import ParserExit
from datetime import datetime, timedelta, UTC
from nonebot_plugin_orm import async_scoped_session, get_session
from sqlalchemy import select
from asyncio import sleep
from pytz import timezone
from .config import Config
from .model import Ticket, Status, Engineer
from .utils import send_forward_msg, print_ticket_info, print_ticket

require("nonebot_plugin_apscheduler")


# 获取中国时区
cst = timezone('Asia/Shanghai')

__plugin_meta__ = PluginMetadata(
    name="CSTS",
    description="客服工单系统",
    usage="",
    config=Config,
)

plugin_config = get_plugin_config(Config)


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


# 定义规则

def is_front(event: MessageEvent) -> bool:
    # 没有配置前端一律视作前端
    if not plugin_config.front_bot:
        return True
    if event.self_id == int(plugin_config.front_bot):
        return True
    return False


def is_backend(event: MessageEvent) -> bool:
    if not plugin_config.backend_bot:
        return True
    if event.self_id == int(plugin_config.backend_bot):
        return True
    return False


async def is_engineer(event: MessageEvent) -> bool:
    # 避免自己给自己发消息反复触发
    if event.get_user_id() in get_bots():
        return False
    # 从后端工程师发来的消息
    if is_backend(event):
        if isinstance(event, GroupMessageEvent):
            return event.group_id == plugin_config.notify_group
        session = get_session()
        async with session.begin():
            return bool((await session.execute(
                select(Engineer).filter(Engineer.engineer_id == event.get_user_id()))).scalar_one_or_none())
    else:
        return False


async def is_customer(event: PrivateMessageEvent) -> bool:
    # 自己不会是机主
    if event.get_user_id() in get_bots():
        return False
    # 只要是前端发来的一律视作机主(方便整活了属于是)
    return is_front(event)


Types_Ticket = {
    "活动的": lambda id: select(Ticket).filter(Ticket.status != Status.CLOSED).order_by(Ticket.begin_at.desc()),
    "未接的": lambda id: select(Ticket).filter(Ticket.status == Status.PENDING).order_by(Ticket.begin_at.desc()),
    "完成的": lambda id: select(Ticket).filter(Ticket.status == Status.CLOSED).order_by(Ticket.begin_at.desc()),
    "我的": lambda engineer_id: select(Ticket).filter(Ticket.engineer_id == engineer_id,
                                                    Ticket.status != Status.CLOSED).order_by(Ticket.begin_at.desc()),
    "所有的": lambda id: select(Ticket).order_by(Ticket.begin_at.desc()),
    "所有我的": lambda engineer_id: select(Ticket).filter(Ticket.engineer_id == engineer_id).order_by(
        Ticket.begin_at.desc())
}

list_parser = ArgumentParser(prog="list")
list_parser.add_argument("type", help=f"工单种类:{' '.join(
    [key for key in Types_Ticket])}", type=str)
list_parser.add_argument("-a", help="用消息转发显示机主描述", action='store_true')

engineer_parser = ArgumentParser(prog="engineers", description="工程师名单操作")
engineer_parser_sub = engineer_parser.add_subparsers(
    dest="sub", help='subcommand help')

engineer_parser_add = engineer_parser_sub.add_parser("add", help="添加工程师")
engineer_parser_add.add_argument("-a", help="加入通知群聊的所有人", action='store_true')
engineer_parser_add.add_argument(
    "--ids", action="extend", nargs="+", type=str, help="列出id")

engineer_parser_del = engineer_parser_sub.add_parser("del", help="删除工程师")
engineer_parser_del.add_argument(
    "ids", action="extend", nargs="+", type=str, help="列出id")

engineer_parser_list = engineer_parser_sub.add_parser("list", help="列出全部工程师")

# 定义响应器
customer_message = on_message(rule=is_customer & to_me(), priority=100)
engineer_message = on_message(rule=is_engineer & to_me(), priority=100)
list_ticket_matcher = on_shell_command("list", parser=list_parser, rule=is_engineer & to_me(), aliases={"列出"},
                                       priority=10, block=True)
get_ticket_matcher = on_command("get", rule=is_engineer & to_me(), aliases={
                                "获取"}, priority=10, block=True)
take_ticket_matcher = on_command("take", rule=is_engineer & to_me(), aliases={
                                 "接单"}, priority=10, block=True)
untake_ticket_matcher = on_command(
    "untake", rule=is_engineer & to_me(), aliases={"放单"}, priority=10, block=True)
close_ticket_matcher = on_command("close", rule=is_engineer & to_me(), aliases={
                                  "关单"}, priority=10, block=True)
force_close_ticket_mathcer = on_command("fclose", rule=is_engineer & to_me(), aliases={"强制关单"}, priority=10,
                                        block=True)
scheduled_ticket_matcher = on_command("scheduled", rule=is_engineer & to_me(), aliases={"预约"}, priority=10,
                                      block=True)
send_ticket_matcher = on_command("send", rule=is_engineer & to_me(), aliases={
                                 "留言"}, priority=10, block=True)
op_engineer_matcher = on_shell_command("engineers", parser=engineer_parser, rule=to_me() & is_backend,
                                       permission=SUPERUSER, priority=10, block=True)
who_asked_matcher = on_keyword({"我恨你"},rule=is_engineer,priority=11)


# 回复客户消息
@customer_message.handle()
async def reply_customer_message(bot: Bot, event: PrivateMessageEvent, session: async_scoped_session):
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
                    # 将关单时间设为当前时间，通知群聊并结束处理
                    await send_forward_msg(get_backend_bot(bot),
                                           [
                        event.message
                    ],
                        target_group_id=plugin_config.notify_group)
                    await customer_message.finish()

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
        await send_forward_msg(
            get_backend_bot(bot),
            [
                Message("接收到来自以下客户的消息" + f" {ticket.id:0>3} " + "！"),
                Message(f"[CQ:contact,type=qq,id={customer_id}]"),
                event.message
            ],
            target_user_id=ticket.engineer_id
        )
    elif ticket.status == Status.SCHEDULED:
        await send_forward_msg(
            get_backend_bot(bot),
            [
                Message("接收到已经预约的来自以下客户的消息" + f" {ticket.id:0>3} " + "！"),
                Message(f"[CQ:contact,type=qq,id={customer_id}]"),
                event.message
            ],
            target_group_id=plugin_config.notify_group
        )


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
            await send_forward_msg(backend_bot, await print_ticket_info(ticket),
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
            await send_forward_msg(backend_bot, await print_ticket_info(ticket),
                                   target_group_id=plugin_config.notify_group)
            # 不要告诉机主他在催单
            # await front_bot.send_private_msg(user_id=ticket_customer_id, message=plugin_config.third_reply)
        if tickets:
            await backend_bot.send_group_msg(group_id=plugin_config.notify_group,
                                             message=plugin_config.alarm_ticket_notify)


# 捕获未能解析的工程师命令
@engineer_message.handle()
async def reply_engineer_message(bot: Bot, event: MessageEvent, session: async_scoped_session):
    await engineer_message.finish(
        "指令列表：\n[list(列出)|get(获取)|take(接单)|untake(放单)|close(关单)|fclose(强制关单)|scheduled(预定)|send(留言)|engineers(管理员操作)]")


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


# 获取某一单的信息
@get_ticket_matcher.got("id", prompt="单号？")
async def get_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText()):
    ticket = await check_backend_ticket(id, bot, matcher, session)
    await send_forward_msg(get_backend_bot(bot), await print_ticket_info(ticket), event=event)
    await get_ticket_matcher.finish()


# 处理接单
@take_ticket_matcher.got("id", prompt="单号？")
async def take_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText()):
    ticket = await check_backend_ticket(id, bot, matcher, session)
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
    ticket = await check_backend_ticket(id, bot, matcher, session)
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
    await send_forward_msg(get_backend_bot(bot), await print_ticket_info(ticket),
                           target_group_id=plugin_config.notify_group)
    await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group),
                                              message=f"工程师{engineer_id}有事暂时无法处理工单 {id:0>3} ，工单已重新进入待接单状态！")
    await untake_ticket_matcher.finish("放单成功！")


# 处理关单
@close_ticket_matcher.got("id", prompt="单号？")
@close_ticket_matcher.got("describe", prompt="请描述工单")
async def close_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText(),
                       describe: str = ArgPlainText()):
    ticket = await check_backend_ticket(id, bot, matcher, session)
    engineer_id = event.get_user_id()

    if ticket.status == Status.SCHEDULED:
        ticket.engineer_id = engineer_id
        await close_ticket_matcher.send("完成的预定")
    elif ticket.status != Status.PROCESSING or ticket.engineer_id != engineer_id:
        await close_ticket_matcher.finish("您未接单或不是该工单的工程师")
    ticket.description = describe
    ticket.status = Status.CLOSED
    ticket.end_at = datetime.fromtimestamp(event.time, cst)

    await session.commit()
    await session.refresh(ticket)

    await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group),
                                              message=await print_ticket(int(id)))
    # 通知客户
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id),
                                              message=f"工程师{engineer_id}已处理完您的工单，感谢您的信任和支持！")
    # 通知接单群
    await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group),
                                              message=f"工程师{engineer_id}已处理完{id}！")
    await close_ticket_matcher.finish()


# 强制关单
@force_close_ticket_mathcer.got("id", prompt="单号？")
@force_close_ticket_mathcer.got("describe", prompt="为什么强制关单？")
async def force_close_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText(),
                             describe: str = ArgPlainText()):
    ticket = await check_backend_ticket(id, bot, matcher, session)
    engineer_id = event.get_user_id()

    ticket.status = Status.CLOSED
    ticket.end_at = datetime.fromtimestamp(event.time, cst)
    ticket.description = "强制关单:" + describe
    await session.commit()
    await session.refresh(ticket)

    await get_backend_bot(bot).send_group_msg(group_id=int(plugin_config.notify_group),
                                              message=await print_ticket(ticket.id))
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id), message=f"感谢您的支持与信任，再见。")
    await force_close_ticket_mathcer.finish(f"强制关单{ticket.id}")


# 处理预定
@scheduled_ticket_matcher.got("id", prompt="单号？")
@scheduled_ticket_matcher.got("scheduled_time", prompt="预约时间地点？（会直接转发给机主）")
async def scheduled_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText(),
                           scheduled_time: str = ArgPlainText()):
    ticket = await check_backend_ticket(id, bot, matcher, session)
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
@send_ticket_matcher.got("id", "单号？")
@send_ticket_matcher.got("send_msg", "留言内容？")
async def send_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText(),
                      send_msg: str = ArgPlainText()):
    ticket = await check_backend_ticket(id, bot, matcher, session)
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id), message=send_msg)
    await matcher.finish("已转发留言")


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
        await send_forward_msg(get_backend_bot(bot), msgs=msg, event=event)
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
            await send_forward_msg(get_backend_bot(bot), await print_ticket_info(ticket), event=event)
    else:
        msgs = []
        for ticket in tickets:
            msgs.append(await print_ticket(ticket.id))
        await send_forward_msg(get_backend_bot(bot), msgs=msgs, event=event)


async def validate_ticket_id(args: str, matcher: Matcher, error_message: str = "请输入正确的工单号") -> int:
    arg = args.strip()
    try:
        ticket_id = int(arg)
    except:
        await matcher.finish(error_message)
    return ticket_id


async def check_backend_ticket(id: str, bot: Bot, matcher: Matcher, session: async_scoped_session, error_message: str = "工单不存在"):
    if bot.self_id != get_backend_bot(bot).self_id:
        await matcher.finish()
    ticket = await session.get(Ticket, id)
    if not ticket:
        await matcher.finish("工单不存在")
    else:
        return ticket

# 谁问你了
@who_asked_matcher.handle()
async def who_asked(bot:Bot,event:MessageEvent):
    await who_asked_matcher.finish(f"谁问你了[CQ:at,qq={event.get_user_id()}]")