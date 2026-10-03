from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.api.routers import items, transactions, system

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="SME POS - Google Sheets backend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

app.include_router(items.router)
app.include_router(transactions.router)
app.include_router(system.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "currency": settings.CURRENCY_SYMBOL,
            "vat_rate": settings.DEFAULT_VAT_RATE,
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
