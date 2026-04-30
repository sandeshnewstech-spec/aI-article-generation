from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from app.core.database import get_db
from app.core.security import SECRET_KEY, ALGORITHM, get_password_hash
from app.models.user import UserCreate, UserResponse, UserRole, UserUpdate
from typing import List
from bson import ObjectId

router = APIRouter(tags=["Users"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    
    db = get_db()
    user = await db["users"].find_one({"username": username})
    if user is None:
        raise credentials_exception
    return user

def require_role(roles: List[UserRole]):
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have enough permissions"
            )
        return current_user
    return role_checker

@router.post("/users", response_model=UserResponse)
async def create_user(
    user_in: UserCreate, 
    admin: dict = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    db = get_db()
    existing_user = await db["users"].find_one({"username": user_in.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    user_dict = user_in.model_dump()
    user_dict["hashed_password"] = get_password_hash(user_dict.pop("password"))
    
    result = await db["users"].insert_one(user_dict)
    user_dict["id"] = str(result.inserted_id)
    return user_dict

@router.get("/users", response_model=List[UserResponse])
async def list_users(admin: dict = Depends(require_role([UserRole.SUPER_ADMIN]))):
    db = get_db()
    users = await db["users"].find().to_list(100)
    for u in users:
        u["id"] = str(u["_id"])
    return users

@router.get("/users/me", response_model=UserResponse)
async def read_users_me(current_user: dict = Depends(get_current_user)):
    current_user["id"] = str(current_user["_id"])
    return current_user

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_in: UserUpdate,
    admin: dict = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    db = get_db()
    update_data = {k: v for k, v in user_in.model_dump().items() if v is not None}
    
    if "password" in update_data:
        update_data["hashed_password"] = get_password_hash(update_data.pop("password"))
        
    result = await db["users"].find_one_and_update(
        {"_id": ObjectId(user_id)},
        {"$set": update_data},
        return_document=True
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
        
    result["id"] = str(result["_id"])
    return result

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    admin: dict = Depends(require_role([UserRole.SUPER_ADMIN]))
):
    db = get_db()
    result = await db["users"].delete_one({"_id": ObjectId(user_id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
        
    return {"status": "success", "message": "User deleted"}
