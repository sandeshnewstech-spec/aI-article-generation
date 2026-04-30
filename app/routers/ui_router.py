from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "current_page": "generator"
    })

@router.get("/editor")
async def news_editor(request: Request):
    return templates.TemplateResponse("editor.html", {
        "request": request,
        "current_page": "editor"
    })

@router.get("/admin/categories")
async def admin_categories(request: Request):
    return templates.TemplateResponse("categories.html", {
        "request": request,
        "current_page": "categories"
    })

@router.get("/admin/slots")
async def admin_slots(request: Request):
    return templates.TemplateResponse("slots.html", {
        "request": request,
        "current_page": "slots"
    })

@router.get("/admin/users")
async def admin_users(request: Request):
    return templates.TemplateResponse("users.html", {
        "request": request,
        "current_page": "users"
    })

@router.get("/full-newspaper")
async def full_newspaper(request: Request):
    return templates.TemplateResponse("full_newspaper.html", {
        "request": request,
        "current_page": "full_newspaper"
    })
