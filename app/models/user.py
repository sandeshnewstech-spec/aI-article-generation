from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    USER = "user"

class UserBase(BaseModel):
    username: str
    role: UserRole = UserRole.USER
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

class UserInDB(UserBase):
    id: str = Field(alias="_id")
    hashed_password: str

class UserResponse(UserBase):
    id: str

    class Config:
        populate_by_name = True
