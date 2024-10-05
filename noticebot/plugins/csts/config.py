from pydantic import BaseModel
from typing import List

class Config(BaseModel):
    """Plugin Config Here"""
    NOTIFY_GROUP: str
    ENGINEERS: List[str]