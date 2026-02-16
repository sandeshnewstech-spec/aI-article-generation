from pydantic import BaseModel
from app.models.data import NewspaperOutput, NewspaperConfig


class RefineRequest(BaseModel):
    selected_article: NewspaperOutput
    config: NewspaperConfig
