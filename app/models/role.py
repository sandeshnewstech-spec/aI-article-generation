from pydantic import BaseModel, Field
from typing import List

class RolePermission(BaseModel):
    role: str
    modules: List[str]

class RolePermissionUpdate(BaseModel):
    modules: List[str]
