from pydantic import BaseModel
from typing import List

class Config(BaseModel):
    """Plugin Config Here"""
    notify_group: str|int
    engineers: List[str|int]
    ticket_creating_alive_time: int # 秒，工单创建过程的生存期（最新消息后过该时间则完成工单创建）
    ticket_alarming_alive_time: int # 秒，工单报警过程的生存期（最新消息后过该时间则进行工单报警）