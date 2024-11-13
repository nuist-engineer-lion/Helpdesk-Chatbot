from nonebot import get_plugin_config
from pydantic import BaseModel
from typing import List


class Config(BaseModel):
    """Plugin Config Here"""
    notify_group: str | int
    # engineers: List[str|int]

    front_bot: str | int | None = None
    backend_bot: str | int | None = None

    ticket_creating_alive_time: int = 60  # 秒，工单创建过程的生存期（最新消息后过该时间则完成工单创建）
    ticket_alarming_alive_time: int = 180  # 秒，工单报警过程的生存期（最新消息后过该时间则进行工单报警）
    ticket_checking_interval: int = 30  # 秒，工单检查间隔
    ticket_create_interval: int = 30  # 秒，创建工单检查间隔

    new_ticket_notify: str = "有新工单，请尽快处理！"  # 新工单通知消息
    alarm_ticket_notify: str = "用户在催单啦！请尽快处理！"  # 工单报警通知消息

    len_first_reply: int=  5   #判断字数
    first_reply_S: str ="您的描述有点简略哦，可以详细说一说具体情况"  # 第一次回复消息S
    first_reply_L: str ="好的，已了解您的大致情况，请稍等。"  # 第一次回复消息L
    first_reply_delay: int = 5  # 秒，第一次回复延迟时间
    # second_reply: str = "我们已经收到您的问题，正在为您联系工程师，请稍等片刻。"# 第二次回复消息
    # third_reply: str = "正在为您加急联系中，请稍等片刻。"# 第三次回复消息

plugin_config = get_plugin_config(Config)
