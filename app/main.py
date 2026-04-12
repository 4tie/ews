from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
import uvicorn
import os

from app.routers import web_ui_routes, backtest, optimizer, settings, ai_chat, evolution, versions

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")
DATA_DIR = os.path.join(BASE_DIR, "data")
USER_DATA_DIR = os.path.join(BASE_DIR, "user_data")


def _dev_reload_dirs() -> list[str]:
    return [
        os.path.join(BASE_DIR, "app"),
        os.path.join(BASE_DIR, "web"),
    ]


def _dev_reload_excludes() -> list[str]:
    return [
        os.path.join(DATA_DIR, "backtest_runs", "*", "workspace"),
        os.path.join(DATA_DIR, "backtest_runs", "*", "workspace", "*"),
        os.path.join(USER_DATA_DIR, "backtest_results", "*"),
        os.path.join(DATA_DIR, "versions", "*", "*.json"),
    ]

app = FastAPI(title="4tie Control Panel", docs_url="/api/docs")

app.mount("/static", StaticFiles(directory=os.path.join(WEB_DIR, "static")), name="static")

templates = Jinja2Templates(directory=os.path.join(WEB_DIR, "templates"))

app.include_router(web_ui_routes.router)
app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(optimizer.router, prefix="/api/optimizer", tags=["optimizer"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])
app.include_router(ai_chat.router, prefix="/api/ai/chat", tags=["ai-chat"])
app.include_router(evolution.router, prefix="/api/ai/evolution", tags=["ai-evolution"])
app.include_router(versions.router, prefix="/api/versions", tags=["versions"])


@app.get("/")
async def root():
    return RedirectResponse(url="/backtesting")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
        reload_dirs=_dev_reload_dirs(),
        reload_excludes=_dev_reload_excludes(),
    )
