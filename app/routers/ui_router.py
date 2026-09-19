import os
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()

# Use absolute path to templates to avoid issues on different OS/environments
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@router.get("/")
async def login_root(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@router.get("/generator")
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={
        "current_page": "generator"
    })

@router.get("/editor")
async def news_editor(request: Request):
    return templates.TemplateResponse(request=request, name="editor.html", context={
        "current_page": "editor"
    })

@router.get("/editor/workspace")
async def news_editor_workspace(request: Request):
    return templates.TemplateResponse(request=request, name="editor_workspace.html", context={
        "current_page": "editor"
    })

@router.get("/admin/categories")
async def admin_categories(request: Request):
    return templates.TemplateResponse(request=request, name="categories.html", context={
        "current_page": "categories"
    })

@router.get("/admin/slots")
async def admin_slots(request: Request):
    return templates.TemplateResponse(request=request, name="slots.html", context={
        "current_page": "slots"
    })

@router.get("/admin/users")
async def admin_users(request: Request):
    return templates.TemplateResponse(request=request, name="users.html", context={
        "current_page": "users"
    })

@router.get("/full-newspaper")
async def full_newspaper(request: Request):
    return templates.TemplateResponse(request=request, name="full_newspaper.html", context={
        "current_page": "full_newspaper"
    })

@router.get("/admin/advt-categories/list")
async def advt_categories_list(request: Request):
    return templates.TemplateResponse(request=request, name="advt_categories/list.html", context={
        "current_page": "advt_categories"
    })

@router.get("/admin/advt-categories/add")
async def advt_categories_add(request: Request):
    return templates.TemplateResponse(request=request, name="advt_categories/add.html", context={
        "current_page": "advt_categories"
    })

@router.get("/admin/advt-categories/edit/{category_id}")
async def advt_categories_edit(request: Request, category_id: str):
    return templates.TemplateResponse(request=request, name="advt_categories/edit.html", context={
        "current_page": "advt_categories",
        "category_id": category_id
    })

@router.get("/advt")
async def advt_module(request: Request):
    return templates.TemplateResponse(request=request, name="advt.html", context={
        "current_page": "advt"
    })
