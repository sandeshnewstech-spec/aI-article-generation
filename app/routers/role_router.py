from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from app.core.database import get_db
from app.models.role import RolePermission, RolePermissionUpdate
from app.routers.user_router import require_role
from app.models.user import UserRole

router = APIRouter(prefix="/api/roles", tags=["Roles"])

@router.get("", response_model=List[RolePermission])
async def get_all_roles(admin: dict = Depends(require_role([UserRole.SUPER_ADMIN]))):
    db = get_db()
    roles_cursor = db["role_permissions"].find({})
    roles = await roles_cursor.to_list(length=100)
    return roles

@router.put("/{role_name}", response_model=RolePermission)
async def update_role_permissions(role_name: str, role_update: RolePermissionUpdate, admin: dict = Depends(require_role([UserRole.SUPER_ADMIN]))):
    db = get_db()
    
    # Check if role is valid
    try:
        UserRole(role_name)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid role name")

    result = await db["role_permissions"].update_one(
        {"role": role_name},
        {"$set": {"modules": role_update.modules}},
        upsert=True
    )
    
    updated_role = await db["role_permissions"].find_one({"role": role_name})
    if not updated_role:
        updated_role = {"role": role_name, "modules": role_update.modules}
        
    return updated_role
