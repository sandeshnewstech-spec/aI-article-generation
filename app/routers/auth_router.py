from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.core.database import get_db
from app.core.security import verify_password, create_access_token
from app.models.user import UserRole
from bson import ObjectId

router = APIRouter(tags=["Authentication"])

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db = get_db()
    user = await db["users"].find_one({"username": form_data.username})
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.get("is_active", True):
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token = create_access_token(subject=user["username"])
    return {"access_token": access_token, "token_type": "bearer", "role": user["role"]}
