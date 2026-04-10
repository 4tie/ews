from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "web", "templates"))

router = APIRouter(tags=["ui"])


@router.get("/backtesting")
async def backtesting_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="pages/backtesting/backtesting.html",
        context={"page": "backtesting", "title": "Backtesting"},
    )


@router.get("/optimizer")
async def optimizer_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="pages/optimizer/index.html",
        context={"page": "optimizer", "title": "Optimizer"},
    )


@router.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="pages/settings/index.html",
        context={"page": "settings", "title": "Settings"},
    )
