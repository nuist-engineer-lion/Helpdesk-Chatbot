from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from nonebot import require
import uuid
require("nonebot_plugin_orm")
from nonebot_plugin_orm import Model

class Ticket(Model):
    __tablename__ = 'tickets'
    id = Column(Integer, primary_key=True)
    uid = Column(String, unique=True)
    customer_id = Column(String)
    status = Column(String,default="creating")
    
    begin_at = Column(DateTime)
    end_at = Column(DateTime, nullable=True)
    
    creating_expired_at = Column(DateTime)
    processing_expired_at = Column(DateTime)
    
    create_time = Column(DateTime, default=datetime.now)
    update_time = Column(DateTime, onupdate=datetime.now)
    
    engineer_id = Column(String,nullable=True)