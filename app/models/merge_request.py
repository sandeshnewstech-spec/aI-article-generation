from pydantic import BaseModel
from typing import List
from app.models.data import NewspaperOutput, NewspaperConfig


class MergeRequest(BaseModel):
    selected_articles: List[NewspaperOutput]
    config: NewspaperConfig
