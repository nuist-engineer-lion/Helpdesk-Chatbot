from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from enum import Enum
from nonebot import require


class Status(Enum):
    CREATING = 0
    PENDING = 1
    PROCESSING = 2
    ALARMING = 3
    CLOSED = 4
    SCHEDULED = 5


class Ticket(Model):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    customer_id: Mapped[str]
    engineer_id: Mapped[str | None] = mapped_column(nullable=True)

    status: Mapped[Status] = mapped_column(default=Status.CREATING)

    begin_at: Mapped[datetime]
    end_at: Mapped[datetime | None] = mapped_column(nullable=True)

    creating_expired_at: Mapped[datetime]
    alarming_expired_at: Mapped[datetime | None] = mapped_column(nullable=True)

    scheduled_time: Mapped[str | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.now, onupdate=datetime.now)


class Engineer(Model):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    engineer_id: Mapped[str] = mapped_column(unique=True)
