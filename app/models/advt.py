from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class AdvtModel(BaseModel):
    """Structured advertisement uploaded document and translation"""
    id: Optional[str] = Field(None, alias="_id")
    filename: str
    file_type: str
    advt_type: Optional[str] = None
    height: Optional[float] = None
    width: Optional[float] = None
    unit: Optional[str] = None
    original_text: Optional[str] = None
    translated_text: Optional[str] = None
    generated_image_url: Optional[str] = None
    status: str = Field(default="Processing") # Processing, Completed, Error
    created_at: datetime = Field(default_factory=datetime.utcnow)
    username: Optional[str] = None

class AdvtCategoryModel(BaseModel):
    """Structured advertisement category and description"""
    id: Optional[str] = Field(None, alias="_id")
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AdvtCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None

class AdvtCategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
