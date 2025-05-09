from argparse import Namespace
from typing import Annotated
from ..matcher import *
from datetime import datetime, timedelta, UTC
from nonebot.typing import T_State
from nonebot_plugin_orm import async_scoped_session
from nonebot.params import CommandArg, ShellCommandArgs, ArgPlainText
from nonebot.exception import ParserExit
from ..config import plugin_config
from pytz import timezone
from ..utils import gen_message_node_by_id, gen_message_node_by_ticket, get_db_ticket, qq_get_db_ticket, gen_message_node_by_msgs, print_ticket_info, print_ticket, get_backend_bot, get_front_bot, get_messages_records, send_forward_msg, to_node, validate_ticket_id
from nonebot.matcher import Matcher
from nonebot.permission import Permission, User
from nonebot.adapters import MessageTemplate
from nonebot.adapters.onebot.v11 import Bot, Event, MessageEvent, PrivateMessageEvent, GroupMessageEvent, Message, MessageSegment, FriendRequestEvent
from ..model import Engineer, Ticket
# 获取中国时区
cst = timezone('Asia/Shanghai')


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
close(关单)|qclose(qq关单)|fclose(强制关单)|mclose(批量关单)
scheduled(预约)|set_schedule(设置默认预约)
send(留言)|report(报告)(统计)
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


@qid_close_ticket_matcher.handle()
@search_qq_matcher.handle()
# 所有指定qq号来获取工单的函数共同处理
async def _(matcher: Matcher, session: async_scoped_session, args: Message = CommandArg()):
    if args.extract_plain_text():
        ticket = await qq_get_db_ticket(args.extract_plain_text(), matcher, session)
        if ticket:
            matcher.set_arg("qid", args)
        else:
            await matcher.finish("工单不存在")


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
    await matcher.send(print_ticket(ticket))
    try:
        await send_forward_msg(bot, await gen_message_node_by_ticket(get_front_bot(bot).self_id, ticket), event=event)
    except:
        await send_forward_msg(get_front_bot(bot),gen_message_node_by_id(await get_messages_records(ticket)),event=event)


# 处理接单
@take_ticket_matcher.got("id", prompt="单号？")
async def take_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText()):
    ticket = await get_db_ticket(id, matcher, session)
    engineer_id = event.get_user_id()
    if not ticket:
        await take_ticket_matcher.finish()
    if ticket.status in [Status.CREATING, Status.CLOSED, Status.PROCESSING]:
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
    await matcher.send(print_ticket(ticket))
    try:
        await send_forward_msg(bot, await gen_message_node_by_ticket(get_front_bot(bot).self_id, ticket), target_group_id=plugin_config.notify_group)
    except:
        await send_forward_msg(get_front_bot(bot),gen_message_node_by_id(await get_messages_records(ticket)),event=event)
    await bot.send_group_msg(group_id=int(plugin_config.notify_group),
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
    await close_ticket_by_id(bot, matcher, event, session, describe, ticket)


@close_ticket_matcher.got("describe", prompt="请描述工单")
async def close_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText(),
                       describe: str = ArgPlainText()):
    if id:
        ticket = await get_db_ticket(id, matcher, session)
    else:
        await matcher.finish("怎么会这样？")
    await close_ticket_by_id(bot, matcher, event, session, describe, ticket)


async def close_ticket_by_id(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, describe: str, ticket: Ticket):
    engineer_id = event.get_user_id()
    ticket.description = describe
    ticket.status = Status.CLOSED
    ticket.end_at = datetime.fromtimestamp(event.time, cst)

    await session.commit()
    await session.refresh(ticket)
    
    await bot.send_group_msg(group_id=int(plugin_config.notify_group),
                             message=f"工程师{engineer_id}已处理完{ticket.id}！")
    await matcher.finish()


@close_many_ticket_matcher.handle()
# 批量关单
async def _(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, ids: str = ArgPlainText()):
    ids_list = ids.split(" ")
    for id in ids_list:
        ticket = await get_db_ticket(id, matcher, session)

        ticket.status = Status.CLOSED
        ticket.end_at = datetime.fromtimestamp(event.time, cst)
        ticket.description = "批量关单"
        await session.commit()

    await close_many_ticket_matcher.finish(f"批量关单完成")


@force_close_ticket_mathcer.got("describe", prompt="为什么强制关单？")
# 强制关单
async def force_close_ticket(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, id: str = ArgPlainText(),
                             describe: str = ArgPlainText()):
    ticket = await get_db_ticket(id, matcher, session)
    engineer_id = event.get_user_id()

    ticket.status = Status.CLOSED
    ticket.end_at = datetime.fromtimestamp(event.time, cst)
    ticket.description = "强制关单:" + describe
    await session.commit()
    await session.refresh(ticket)

    await force_close_ticket_mathcer.finish(f"强制关单{ticket.id}")


# 处理预定
@scheduled_ticket_matcher.handle()
async def _(matcher: Matcher):
    await matcher.send("默认时间：" + plugin_config.default_schedule)


@scheduled_ticket_matcher.got("usedefault", prompt=MessageTemplate("使用默认时间?(是/否)"))
async def schedule_use_default(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, usedefault: str = ArgPlainText()):
    if usedefault == "是":
        matcher.set_arg("scheduled_time", Message(
            plugin_config.default_schedule))


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
    await bot.send_group_msg(group_id=int(plugin_config.notify_group), message=f"添加预约:{id}")

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
    tickets = (await session.execute(select(Ticket).where(Ticket.customer_id == qid).order_by(Ticket.begin_at.desc()).limit(10))).scalars()
    msgs: list[Message] = []
    for ticket in tickets:
        msgs.append(print_ticket(ticket))
    await send_forward_msg(bot, gen_message_node_by_msgs(msgs), event=event)
    await matcher.finish()


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
        try:
            msg_nodes = []
            for ticket in tickets:
                msg_nodes.append(to_node("CM", bot.self_id, print_ticket(ticket)))
                msg_nodes.append(to_node("CM",bot.self_id,await gen_message_node_by_ticket(
                    get_front_bot(bot).self_id, ticket)))
            await send_forward_msg(bot, msg_nodes, event=event)
        except:
            msg_nodes = []
            for ticket in tickets:
                msg_nodes.append(to_node("CM", bot.self_id, print_ticket(ticket)))
                msg_nodes.append(to_node("CM",bot.self_id,gen_message_node_by_id(
                    await get_messages_records(ticket))))
            await send_forward_msg(get_front_bot(bot),msg_nodes,event=event)
    else:
        msgs = []
        for ticket in tickets:
            msgs.append(print_ticket(ticket))
        await send_forward_msg(bot, gen_message_node_by_msgs(msgs), event=event)


@set_schedule_matcher.handle()
@set_schedule_matcher.got("time", "输入时间地点")
async def set_schedule(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, time: str = ArgPlainText()):
    plugin_config.default_schedule = time
    await matcher.finish("设置完成")


@who_asked_matcher.handle()
# 谁问你了
async def who_asked(bot: Bot, event: MessageEvent):
    await who_asked_matcher.finish(Message(f"[CQ:at,qq={event.get_user_id()}] 谁问你了"))


@i_understand_matcher.handle()
# 我懂
async def i_understand(bot: Bot, event: MessageEvent):
    await i_understand_matcher.finish(Message(f"[CQ:at,qq={event.get_user_id()}] 我懂"))

# 数据报告


@report_matcher.handle()
async def _(bot: Bot, matcher: Matcher, event: MessageEvent, session: async_scoped_session, args: Message = CommandArg()):
    try:
        days = int(args.extract_plain_text())
        if days < 0:
            raise (ValueError)
    except:
        days = 7
        await matcher.send(f'没指定天数，默认{days}天')

    # 防止有铸币要乱搞
    try:
        tickets = (await session.execute(select(Ticket).filter(Ticket.end_at > datetime.now() - timedelta(days=days)))).scalars()
    except:
        await matcher.finish('不知道发生了什么，但是搜不了')

    await matcher.send(f"以下是{days}天内的关单统计")
    counter: dict[str, int] = {}
    not_correctly_closed = 0
    msg = '统计结果\n'

    for ticket in tickets:
        if ticket.engineer_id:
            counter.setdefault(ticket.engineer_id, 0)
            counter[ticket.engineer_id] += 1
        else:
            not_correctly_closed += 1

    qid_nick: dict[str, str] = {}

    # 倒序输出关单数
    for k, v in sorted(counter.items(), key=lambda kv: (kv[1], kv[0]), reverse=True):
        try:
            nick = qid_nick.setdefault(k, (await bot.call_api('get_group_member_info', group_id=plugin_config.notify_group, user_id=k, no_cache=False))['nickname'])
            msg += f'{nick}:{v}\n'
        except:
            msg += f'{k}:{v}\n'
    msg += f'NaN:{not_correctly_closed}'

    await matcher.finish(msg)
