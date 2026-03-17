from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

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
