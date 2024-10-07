from nonebot import require
require("nonebot_plugin_chatrecorder")
from nonebot import get_plugin_config, on_message
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, PrivateMessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from asyncio import sleep
import random

from .config import Config
from .ticket_manager import (
    get_latest_active_ticket_by_user_id, 
    create_ticket, 
    get_ticket, 
    update_ticket, 
    get_all_tickets, 
    print_ticket, 
    get_ticket_by_engineer_id
    )
from datetime import datetime, timedelta, UTC
# 获取中国时区
from pytz import timezone
cst = timezone('Asia/Shanghai')

__plugin_meta__ = PluginMetadata(
    name="CSTS",
    description="客服工单系统",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

# 定义规则
async def is_engineer(event: MessageEvent) -> bool:
    return event.get_user_id() in config.engineers

async def is_customer(event: PrivateMessageEvent) -> bool:
    return await is_engineer(event) is False

# 定义响应器
customer_message = on_message(rule=is_customer & to_me())
engineer_message = on_message(rule=is_engineer & to_me())

# 回复客户消息
@customer_message.handle()
async def reply_customer_message(bot: Bot, event: PrivateMessageEvent):
    uid = event.get_user_id()
    ticket_id = get_latest_active_ticket_by_user_id(uid) # 获取用户最新的工单
    if ticket_id is None: # 如果没有工单
        # 创建工单
        ticket_id = create_ticket(uid, datetime.fromtimestamp(event.time, cst))
        # 延时3~5秒，用于模拟工程师接单
        await sleep(random.randint(3, 5))
        await customer_message.send("您好，欢迎联系咨询，请详细描述您的问题，我们会尽快为您解答。")
    if "解决了" in event.get_plaintext():
        update_ticket(ticket_id, status='closed', end_at=datetime.fromtimestamp(event.time, cst))
        await customer_message.finish("感谢您的咨询，祝您生活愉快！")
    if get_ticket(ticket_id)['status'] == 'creating': # 如果工单状态为创建中
        update_ticket(ticket_id, creating_expired_at=datetime.now() + timedelta(seconds=config.waiting_time))
        # 等待waiting_time秒
        await sleep(config.waiting_time+2)
        # 如果当前时间大于工单创建中过期时间
        if datetime.now() > get_ticket(ticket_id)['creating_expired_at'] and get_ticket(ticket_id)['status'] == 'creating':
            update_ticket(ticket_id, status='processing') # 更新工单状态为处理中
            # 将工单创建起至当下的消息合并转发至【通知群】
            await customer_message.send("您的问题已经记录并提交工程师，正在派单请稍等...")
            await print_ticket(event=event, bot=bot, ticket_id=ticket_id, target_group_id=config.notify_group)
            # @全体成员 有新工单，请尽快处理！
            await bot.send_group_msg(group_id=config.notify_group, message="[CQ:at,qq=all] 有新工单，请尽快处理！")
    elif get_ticket(ticket_id)['status'] == 'processing':
        if get_ticket(ticket_id)['engineer_id'] == '':
            update_ticket(ticket_id, processing_expired_at=datetime.now() + timedelta(seconds=config.waiting_time / 2))
            # 等待waiting_time秒
            await sleep(config.waiting_time/2+2)
            # 如果当前时间大于工单处理中过期时间
            if datetime.now() > get_ticket(ticket_id)['processing_expired_at']:
                # 将工单创建起至当下的消息合并转发至【通知群】
                await customer_message.send("不好意思啦，刚才工程师开小差了，正在积极为您联系工程师！")
                await print_ticket(event=event, bot=bot, ticket_id=ticket_id, target_group_id=config.notify_group)
                await bot.send_group_msg(group_id=config.notify_group, message="[CQ:at,qq=all] 工程师接单超时，请尽快处理！")
        else:
            # 将消息转发至工程师
            await bot.send_private_msg(user_id=get_ticket(ticket_id)['engineer_id'], message=event.get_message())

# 回复工程师消息
@engineer_message.handle()
async def reply_engineer_message(bot: Bot, event: MessageEvent):
    uid = event.get_user_id()
    plain_message = event.get_plaintext()
    ticket_id = get_ticket_by_engineer_id(uid)
    if "查看工单" in plain_message:
        ticket_ids = get_all_tickets()
        if len(ticket_ids) == 0:
            await engineer_message.finish("当前没有工单！")
        for ticket_id in ticket_ids:
            if get_ticket(ticket_id)['status'] != 'closed':
                await print_ticket(event=event, bot=bot, ticket_id=ticket_id)
    elif "取消接单" in plain_message:
        if ticket_id is not None:
            if get_ticket(ticket_id)['status'] == 'processing' and get_ticket(ticket_id)['engineer_id'] == uid:
                update_ticket(ticket_id, engineer_id='')
                await engineer_message.finish("取消接单成功！")
        else:
            await engineer_message.finish("没单你取消个啥？空气吗？")
    elif "接单" in plain_message:
        if ticket_id is not None and get_ticket(ticket_id)['status'] != 'closed':
            await engineer_message.finish("当前暂不支持同时接多个工单！请先处理完当前工单再接单！")
        try:
            ticket_id = plain_message.split("接单")[-1].strip()
            if ticket_id == "" or ticket_id is None:
                raise KeyError
        except KeyError:
            await engineer_message.finish("接单失败！请指定工单号！")
        ticket = get_ticket(ticket_id)
        if ticket['status'] == 'processing' and ticket['engineer_id'] == '':
            update_ticket(ticket_id, engineer_id=uid)
            await engineer_message.send("接单成功！接下来请与我一对一私聊，我会将用户消息转发给您！")
            # 告知用户工程师已接单，并发送工程师的名片
            await bot.send_private_msg(user_id=ticket['customer_id'], message=f"工程师{uid}已接单！您可以直接用此会话与工程师沟通，也可以添加工程师为好友！")
            await bot.send_private_msg(user_id=ticket['customer_id'], message=f"[CQ:contact,type=qq,id={uid}]")
        else:
            await engineer_message.finish("接单失败！下次早点来哦！")
    elif "关闭工单" in plain_message:
        if ticket_id is not None:
            if get_ticket(ticket_id)['status'] == 'processing' and get_ticket(ticket_id)['engineer_id'] == uid:
                update_ticket(ticket_id, status='closed', end_at=datetime.fromtimestamp(event.time, cst))
                await engineer_message.finish("关闭工单成功！")
        else:
            await engineer_message.finish("没单你关闭个啥？空气吗？")
    else:
        if ticket_id is not None:
            # 将消息转发至客户
            await bot.send_private_msg(user_id=get_ticket(ticket_id)['customer_id'], message=event.get_message())
            # await engineer_message.finish("消息已转发至客户！")
        else:
            await engineer_message.finish("可用指令：查看工单、接单、取消接单、关闭工单")