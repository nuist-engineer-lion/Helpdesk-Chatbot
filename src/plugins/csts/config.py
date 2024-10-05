from pydantic import BaseModel
from typing import List

class Config(BaseModel):
    """Plugin Config Here"""
    notify_group: str|int
    engineers: List[str]