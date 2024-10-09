from sqlalchemy.orm import Mapped,mapped_column
from datetime import datetime
from nonebot import require
require("nonebot_plugin_orm")
from nonebot_plugin_orm import Model

class Ticket(Model):
    id:Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    customer_id:Mapped[str]
    engineer_id:Mapped[str|None] = mapped_column(nullable=True)

    status:Mapped[str] = mapped_column(default="creating")# creating, pending, processing, alarming, closed
    
    begin_at:Mapped[datetime]
    end_at:Mapped[datetime|None] = mapped_column(nullable=True)
    
    creating_expired_at:Mapped[datetime]
    alarming_expired_at:Mapped[datetime|None] = mapped_column(nullable=True)
    
    created_at:Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at:Mapped[datetime] = mapped_column(onupdate=datetime.now)