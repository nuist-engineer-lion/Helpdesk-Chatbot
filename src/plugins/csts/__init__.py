from typing import Annotated
from nonebot import get_bots, logger, on_shell_command, require, get_bot
from nonebot.rule import Rule
from nonebot import get_plugin_config, on_message, on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, PrivateMessageEvent, GroupMessageEvent, Message
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me,ArgumentParser,Namespace
from nonebot.permission import SUPERUSER
from nonebot.params import CommandArg,ShellCommandArgs
from nonebot.exception import ParserExit
from datetime import datetime, timedelta, UTC
from nonebot_plugin_orm import async_scoped_session, get_session
from sqlalchemy import select
from asyncio import sleep
# 获取中国时区
from pytz import timezone
cst = timezone('Asia/Shanghai')

from .config import Config
from .model import Ticket,Status,Engineer
from .utils import send_forward_msg, print_ticket_info,print_ticket

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

def is_front(event:MessageEvent) -> bool:
    # 没有配置前端一律视作前端
    if not plugin_config.front_bot:
        return True
    if event.self_id == int(plugin_config.front_bot):
        return True
    return False

def is_backend(event:MessageEvent) -> bool:
    if not plugin_config.backend_bot:
        return True
    if event.self_id == int(plugin_config.backend_bot):
        return True
    return False
    

async def is_engineer(event: MessageEvent) -> bool:
    # 避免自己给自己发消息反复触发
    if event.get_user_id() in get_bots():
        return False
    # 从非后端工程师发来的消息
    if is_backend(event):
        if isinstance(event, GroupMessageEvent):
            return event.group_id == plugin_config.notify_group
        session = get_session()
        async with session.begin():
            return bool((await session.execute(select(Engineer).filter(Engineer.engineer_id==event.get_user_id()))).scalar_one_or_none())
    else:
        return False

async def is_customer(event: PrivateMessageEvent) -> bool:
    # 自己不会是机主
    if event.get_user_id() in get_bots():
        return False
    # 只要是前端发来的一律视作机主(方便整活了属于是)
    return is_front(event)

Types_Ticket={
    "活动的":lambda id:select(Ticket).filter(Ticket.status != Status.CLOSED).order_by(Ticket.begin_at.desc()),
    "未接的":lambda id:select(Ticket).filter(Ticket.status == Status.PENDING).order_by(Ticket.begin_at.desc()),
    "我的":lambda engineer_id:select(Ticket).filter(Ticket.engineer_id == engineer_id, Ticket.status != Status.CLOSED).order_by(Ticket.begin_at.desc()),
    "所有的":lambda id:select(Ticket).order_by(Ticket.begin_at.desc()),
    "所有我的":lambda engineer_id:select(Ticket).filter(Ticket.engineer_id == engineer_id).order_by(Ticket.begin_at.desc())
    }

close_parser = ArgumentParser(prog="close")
close_parser.add_argument("id",help="工单号",type=int)
close_parser.add_argument("describe",help="描述工单",type=str)

list_parser = ArgumentParser(prog="list")
list_parser.add_argument("type",help=f"工单种类:{ ' '.join([key for key in Types_Ticket]) }",type=str)
list_parser.add_argument("-a",help="用消息转发显示机主描述",action='store_true')

scheduled_parser = ArgumentParser(prog="scheduled")
scheduled_parser.add_argument("id",help="工单号",type=int)

engineer_parser = ArgumentParser(prog="engineers",description="工程师名单操作")
engineer_parser_sub = engineer_parser.add_subparsers(dest="sub",help='subcommand help')

engineer_parser_add = engineer_parser_sub.add_parser("add",help="添加工程师")
engineer_parser_add.add_argument("-a",help="加入通知群聊的所有人",action='store_true')
engineer_parser_add.add_argument("--ids",action="extend", nargs="+", type=str,help="列出id")

engineer_parser_del = engineer_parser_sub.add_parser("del",help="删除工程师")
engineer_parser_del.add_argument("ids",action="extend", nargs="+", type=str,help="列出id")

engineer_parser_list = engineer_parser_sub.add_parser("list",help="列出全部工程师")

# 定义响应器
customer_message = on_message(rule=is_customer & to_me(), priority=100)
engineer_message = on_message(rule=is_engineer & to_me(), priority=100)
list_ticket_matcher = on_shell_command("list", parser=list_parser, rule=is_engineer, aliases={"列出"} , priority=10, block=True)
take_ticket_matcher = on_command("take", rule=is_engineer, aliases={"接单"}, priority=10, block=True)
untake_ticket_matcher = on_command("untake", rule=is_engineer, aliases={"放单"}, priority=10, block=True)
close_ticket_matcher = on_shell_command("close",parser=close_parser, rule=is_engineer, aliases={"关单"}, priority=10, block=True)
force_close_ticket_mathcer = on_command("fclose",rule=is_engineer,aliases={"强制关单"},priority=10,block=True)
scheduled_ticket_matcher = on_shell_command("scheduled",parser=scheduled_parser, rule=is_engineer, aliases={"预定"}, priority=10, block=True)
op_engineer_matcher = on_shell_command("engineers",parser=engineer_parser ,rule=to_me() & is_backend ,permission=SUPERUSER)


# 回复客户消息
@customer_message.handle()
async def reply_customer_message(bot: Bot, event: PrivateMessageEvent, session: async_scoped_session):
    customer_id = event.get_user_id()
    # 根据客户id获取最新的未关闭工单
    ticket = await session.execute(select(Ticket).filter(Ticket.customer_id == customer_id, Ticket.status != Status.CLOSED).order_by(Ticket.begin_at.desc()).limit(1))
    ticket = ticket.scalars().first()
    if ticket is None: # 如果没有工单
        # 创建工单
        ticket = Ticket(customer_id=customer_id, begin_at=datetime.fromtimestamp(event.time, cst), creating_expired_at=datetime.now() + timedelta(seconds=plugin_config.ticket_creating_alive_time))
        session.add(ticket)
        await session.commit()
        logger.info("创建工单已经提交到数据库")
        # 延时n秒，用于模拟工程师接单
        try:
            await bot.call_api("set_input_status", user_id=customer_id)
        except:
            logger.warning("不支持set_input_status api")
        await sleep(plugin_config.first_reply_delay)
        await customer_message.send(plugin_config.first_reply)
    elif ticket.status == Status.CREATING:
        # 更新工单的创建过期时间
        ticket.creating_expired_at = datetime.now() + timedelta(seconds=plugin_config.ticket_creating_alive_time)
        await session.commit()
    elif ticket.status == Status.ALARMING:
        # 更新工单的报警过期时间
        ticket.alarming_expired_at = datetime.now() + timedelta(seconds=plugin_config.ticket_alarming_alive_time)
        await session.commit()
    elif ticket.status == Status.PENDING: # 如果没有工程师接单，设置为催单状态
        ticket.status = Status.ALARMING
        ticket.alarming_expired_at = datetime.now() + timedelta(seconds=plugin_config.ticket_alarming_alive_time)
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

@scheduler.scheduled_job(trigger="interval", seconds=plugin_config.ticket_checking_interval)
async def ticket_check():
    bot = get_bot()
    front_bot = get_front_bot(bot)
    backend_bot = get_backend_bot(bot)
    # 发通知用发通知的号
    session = get_session()
    # 筛选出所有处于creating但是已经过期的工单
    async with session.begin():
        tickets = await session.execute(select(Ticket).filter(Ticket.status == Status.CREATING, Ticket.creating_expired_at < datetime.now()))
        tickets = tickets.scalars().all()
        for ticket in tickets:
            ticket_id = ticket.id
            ticket_customer_id = ticket.customer_id
            # 将工单状态更新为pending
            ticket.status = Status.PENDING
            # 转发消息给通知群
            await send_forward_msg(backend_bot, await print_ticket_info(ticket_id), target_group_id=plugin_config.notify_group)
            # 不要告诉机主转发出去了
            # await front_bot.send_private_msg(user_id=ticket_customer_id, message=plugin_config.second_reply)
        if tickets:
            await backend_bot.send_group_msg(group_id=plugin_config.notify_group, message=plugin_config.new_ticket_notify)
    
    # 筛选出所有处于alarming但是已经过期的工单
    async with session.begin():
        tickets = await session.execute(select(Ticket).filter(Ticket.status == Status.ALARMING, Ticket.alarming_expired_at < datetime.now()))
        tickets = tickets.scalars().all()
        for ticket in tickets:
            ticket_id = ticket.id
            ticket_customer_id = ticket.customer_id
            # 将工单状态更新为pending
            ticket.status = Status.PENDING
            # 转发消息给通知群
            await send_forward_msg(backend_bot, await print_ticket_info(ticket_id), target_group_id=plugin_config.notify_group)
            # 不要告诉机主他在催单
            # await front_bot.send_private_msg(user_id=ticket_customer_id, message=plugin_config.third_reply)
        if tickets:
            await backend_bot.send_group_msg(group_id=plugin_config.notify_group, message=plugin_config.alarm_ticket_notify)

# 捕获未能解析的工程师命令
@engineer_message.handle()
async def reply_engineer_message(bot: Bot, event: MessageEvent, session: async_scoped_session):
    await engineer_message.finish("指令列表：[list(列出)|take(接单)|untake(放单)|close(关单)|fclose(强制关单)|scheduled(预定)|engineers(管理员操作)]")

# list 错误处理
@list_ticket_matcher.handle()
async def _(bot:Bot,event:MessageEvent,session:async_scoped_session,args:Annotated[ParserExit, ShellCommandArgs()]):
    await list_ticket_matcher.finish(list_parser.format_help())

# 处理list
@list_ticket_matcher.handle()
async def list_ticket(bot:Bot,event:MessageEvent,session:async_scoped_session,args:Annotated[Namespace, ShellCommandArgs()]):
    if args.type not in Types_Ticket.keys():
        await list_ticket_matcher.finish(list_parser.format_help())
    tickets = (await session.execute(Types_Ticket[args.type](event.get_user_id()))).scalars().all()
    if not tickets:
        await list_ticket_matcher.finish("没有")
    if args.a:
        for ticket in tickets:
            await send_forward_msg(bot, await print_ticket_info(ticket.id), event=event)
    else:
        msgs=[]
        for ticket in tickets:
            msgs.append(await print_ticket(ticket.id))
        await send_forward_msg(bot, msgs=msgs, event=event)

async def validate_ticket_id(args: str, matcher, error_message: str = "请输入正确的工单号") -> int:
    arg = args.strip()
    try:
        ticket_id = int(arg)
    except:
        await matcher.finish(error_message)
    return ticket_id

# 处理接单
@take_ticket_matcher.handle()
async def take_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session, args: Message = CommandArg()):
    engineer_id = event.get_user_id()
    ticket_id = await validate_ticket_id(args.extract_plain_text(), take_ticket_matcher)
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await take_ticket_matcher.finish("工单不存在")
    if ticket.status not in [Status.PENDING,Status.SCHEDULED]:
        await take_ticket_matcher.finish("该工单尚未创建完成或已被接单")
    ticket.status = Status.PROCESSING
    ticket.engineer_id = engineer_id
    await session.commit()
    await session.refresh(ticket)
    # 通知客户
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id), message=f"工程师{engineer_id}已接单！您可以直接用此会话与工程师沟通，也可以添加工程师为好友！")
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id), message=f"[CQ:contact,type=qq,id={engineer_id}]")
    await take_ticket_matcher.send(f"接单成功！请添加客户为好友！解决后及时关单！")
    await take_ticket_matcher.finish(Message(f"[CQ:contact,type=qq,id={ticket.customer_id}]"))

# 处理放单
@untake_ticket_matcher.handle()
async def untake_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session, args: Message = CommandArg()):
    engineer_id = event.get_user_id()
    ticket_id = await validate_ticket_id(args.extract_plain_text(), untake_ticket_matcher)
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await untake_ticket_matcher.finish("工单不存在")
    if ticket.status != Status.PROCESSING or ticket.engineer_id != engineer_id:
        await untake_ticket_matcher.finish("您未接单或不是该工单的工程师")
    ticket.status = Status.PENDING
    ticket.engineer_id = None
    customer_id = int(ticket.customer_id)
    await session.commit()
    # 通知客户
    await get_front_bot(bot).send_private_msg(user_id=customer_id, message=f"工程师{engineer_id}有事暂时无法处理您的工单，您的工单已重新进入待接单状态！我们将优先为您安排其他工程师！")
    # 通知接单群
    await send_forward_msg(bot, await print_ticket_info(ticket_id), target_group_id=plugin_config.notify_group)
    await bot.send_group_msg(group_id=int(plugin_config.notify_group), message=f"工程师{engineer_id}有事暂时无法处理工单 {ticket_id:0>3} ，工单已重新进入待接单状态！")
    await untake_ticket_matcher.finish("放单成功！")

@close_ticket_matcher.handle()
async def _(bot: Bot, event: MessageEvent, session: async_scoped_session, args: Annotated[ParserExit, ShellCommandArgs()]):
    await close_ticket_matcher.finish(close_parser.format_help())

# 处理关单
@close_ticket_matcher.handle()
async def close_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session, args: Annotated[Namespace, ShellCommandArgs()]):
    engineer_id = event.get_user_id()
    ticket_id = await validate_ticket_id(args.id, close_ticket_matcher)
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await close_ticket_matcher.finish("工单不存在")
    
    if ticket.status == Status.SCHEDULED:
        ticket.engineer_id=engineer_id
        await close_ticket_matcher.send("完成的预定")
    elif ticket.status != Status.PROCESSING or ticket.engineer_id != engineer_id:
        await close_ticket_matcher.finish("您未接单或不是该工单的工程师")
    ticket.description = args.describe
    ticket.status = Status.CLOSED
    ticket.end_at = datetime.fromtimestamp(event.time, cst)
    
    await session.commit()
    await session.refresh(ticket)
    
    await bot.send_group_msg(group_id=int(plugin_config.notify_group),message= await print_ticket(ticket_id))
    # 通知客户
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id), message=f"工程师{engineer_id}已处理完您的工单，感谢您的信任和支持！")
    # 通知接单群
    await bot.send_group_msg(group_id=int(plugin_config.notify_group), message=f"工程师{engineer_id}已处理完{ticket_id}！")

@force_close_ticket_mathcer.handle()
async def force_close_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session, args: Message = CommandArg()):
    engineer_id = event.get_user_id()
    ticket_id = await validate_ticket_id(args.extract_plain_text(), close_ticket_matcher)
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await close_ticket_matcher.finish("工单不存在")
    
    ticket.status = Status.CLOSED
    ticket.end_at = datetime.fromtimestamp(event.time, cst)
    await session.commit()
    await session.refresh(ticket)
    
    await force_close_ticket_mathcer.finish(f"强制关单{ticket_id}")
    await bot.send_group_msg(group_id=int(plugin_config.notify_group),message= await print_ticket(ticket_id))

@scheduled_ticket_matcher.handle()
async def _(bot: Bot, event: MessageEvent, session: async_scoped_session,  args: Annotated[ParserExit, ShellCommandArgs()]):
    await scheduled_ticket_matcher.finish(scheduled_parser.format_help())

# 处理预定
@scheduled_ticket_matcher.handle()
async def scheduled_ticket(bot: Bot, event: MessageEvent, session: async_scoped_session,  args: Annotated[Namespace, ShellCommandArgs()]):
    ticket_id = await validate_ticket_id(args.id, close_ticket_matcher)
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        await close_ticket_matcher.finish("工单不存在")
    ticket.status = Status.SCHEDULED
    ticket.scheduled_time = args.time
    
    await session.commit()
    await session.refresh(ticket)
    # 发给顾客
    await get_front_bot(bot).send_private_msg(user_id=int(ticket.customer_id), message=f"为您预约：{args.time}")
    await bot.send_group_msg(group_id=int(plugin_config.notify_group), message=f"添加预约id:{ticket_id}")



@op_engineer_matcher.handle()
async def _(bot: Bot, event: MessageEvent, session: async_scoped_session,  args: Annotated[ParserExit, ShellCommandArgs()]):
    await op_engineer_matcher.finish(engineer_parser.format_help())
@op_engineer_matcher.handle()
async def _(bot: Bot, event: MessageEvent, session: async_scoped_session,  args: Annotated[Namespace, ShellCommandArgs()]):
    if args.sub == "add":
        if args.a:
            users = await bot.get_group_member_list(group_id=int(plugin_config.notify_group))
            for user in users:
                if str(user['user_id']) not in [str(plugin_config.backend_bot),str(plugin_config.front_bot)]:
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
            engineer = (await session.execute(select(Engineer).where(Engineer.engineer_id==id))).scalar_one_or_none()
            if engineer:
                await session.delete(engineer)
        await session.commit()
    elif args.sub == "list":
        engineers = (await session.execute(select(Engineer))).scalars().all()
        msg = []
        for engineer in engineers:
            msg += Message(engineer.engineer_id)
        await send_forward_msg(bot,msgs=msg,event=event)
    else:
        await op_engineer_matcher.finish(engineer_parser.format_usage())
    
    