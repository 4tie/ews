import os
import sys

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.routers import ai_chat, backtest, evolution, optimizer, settings, versions, web_ui_routes

WEB_DIR = os.path.join(BASE_DIR, "web")
DATA_DIR = os.path.join(BASE_DIR, "data")
USER_DATA_DIR = os.path.join(BASE_DIR, "user_data")


def _dev_reload_dirs() -> list[str]:
    return ["app", "web"]


def _dev_reload_excludes() -> list[str]:
    return [
        os.path.join("data", "backtest_runs", "*", "workspace"),
        os.path.join("data", "backtest_runs", "*", "workspace", "*"),
        os.path.join("user_data", "backtest_results", "*"),
        os.path.join("data", "versions", "*", "*.json"),
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


def main() -> None:
    os.chdir(BASE_DIR)
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
        reload_dirs=_dev_reload_dirs(),
        reload_excludes=_dev_reload_excludes(),
    )


if __name__ == "__main__":
    main()
