from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "web", "templates"))

router = APIRouter(tags=["ui"])


@router.get("/backtesting")
async def backtesting_page(request: Request):
    return templates.TemplateResponse(
        "pages/backtesting/backtesting.html",
        {"request": request, "page": "backtesting", "title": "Backtesting"},
    )


@router.get("/optimizer")
async def optimizer_page(request: Request):
    return templates.TemplateResponse(
        "pages/optimizer/index.html",
        {"request": request, "page": "optimizer", "title": "Optimizer"},
    )


@router.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse(
        "pages/settings/index.html",
        {"request": request, "page": "settings", "title": "Settings"},
    )
