from pydantic import BaseModel
from typing import List

class Config(BaseModel):
    """Plugin Config Here"""
    notify_group: str|int
    engineers: List[str|int]
    ticket_creating_alive_time: int = 60 # 秒，工单创建过程的生存期（最新消息后过该时间则完成工单创建）
    ticket_alarming_alive_time: int = 20 # 秒，工单报警过程的生存期（最新消息后过该时间则进行工单报警）
    ticket_checking_interval: int = 30 # 秒，工单检查间隔

    new_ticket_notify: str = "[CQ:at,qq=all] 有新工单，请尽快处理！" # 新工单通知消息
    alarm_ticket_notify: str = "[CQ:at,qq=all] 用户在催单啦！请尽快处理！"# 工单报警通知消息