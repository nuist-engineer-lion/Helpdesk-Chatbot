from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from nonebot import require
require("nonebot_plugin_orm")
from nonebot_plugin_orm import Model

class Ticket(Model):
    id = Column(Integer, primary_key=True, autoincrement=True)

    customer_id = Column(String)
    engineer_id = Column(String, nullable=True)

    status = Column(String,default="creating")# creating, processing, alarming, closed
    
    begin_at = Column(DateTime)
    end_at = Column(DateTime, nullable=True)
    
    creating_expired_at = Column(DateTime)
    alarming_expired_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, onupdate=datetime.now)