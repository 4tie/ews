from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
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
    return RedirectResponse(url="/backtesting", status_code=307)


@router.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="pages/settings/index.html",
        context={"page": "settings", "title": "Settings"},
    )


@router.get("/versions")
async def versions_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="pages/versions/index.html",
        context={"page": "versions", "title": "Strategy Versions"},
    )
