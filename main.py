"""
SME POS & Business Management System
Offline-first • Modular (Restaurant / Retail / Pharmacy) • FastAPI + SQLite
"""
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.database import init_db, AsyncSessionLocal
from app.api.routers import items, transactions, system
from app.models.models import Item, Customer, SystemSetting
from app.services.inventory_service import InventoryService
from sqlalchemy import select

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables + seed demo data if empty."""
    await init_db()
    await seed_demo_data()
    yield
    # Shutdown (nothing special for SQLite)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Modular offline-first POS for SMEs in emerging markets",
    lifespan=lifespan,
)

# CORS – allow local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static & Templates
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

# Routers
app.include_router(items.router)
app.include_router(transactions.router)
app.include_router(system.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the single-page POS dashboard."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": settings.APP_NAME,
            "currency": settings.CURRENCY_SYMBOL,
            "vat_rate": settings.DEFAULT_VAT_RATE,
        },
    )


async def seed_demo_data():
    """Seed a few demo products & a customer so the UI is immediately usable."""
    async with AsyncSessionLocal() as db:
        # Check if already seeded
        result = await db.execute(select(Item).limit(1))
        if result.scalar_one_or_none():
            return

        demo_items = [
            {
                "sku": "COF-001",
                "barcode": "1001001",
                "name": "Ethiopian Coffee (Cup)",
                "category": "Beverages",
                "unit_price": 45.00,
                "cost_price": 15.00,
                "stock_qty": 200,
                "unit": "cup",
                "is_recipe": False,
            },
            {
                "sku": "BREAD-01",
                "barcode": "1001002",
                "name": "Fresh Injera (Pack)",
                "category": "Food",
                "unit_price": 80.00,
                "cost_price": 40.00,
                "stock_qty": 50,
                "unit": "pack",
            },
            {
                "sku": "SHIRT-M-BLU",
                "barcode": "2002001",
                "name": "Cotton Shirt - Blue M",
                "category": "Apparel",
                "unit_price": 650.00,
                "cost_price": 320.00,
                "stock_qty": 25,
                "size": "M",
                "color": "Blue",
                "unit": "pcs",
            },
            {
                "sku": "PARA-500",
                "barcode": "3003001",
                "name": "Paracetamol 500mg (10 tabs)",
                "category": "Pharmacy",
                "unit_price": 35.00,
                "cost_price": 12.00,
                "stock_qty": 120,
                "requires_batch": True,
                "requires_expiry": True,
                "unit": "box",
                "low_stock_threshold": 20,
            },
            {
                "sku": "SOAP-01",
                "barcode": "4004001",
                "name": "Body Soap 100g",
                "category": "Grocery",
                "unit_price": 25.00,
                "cost_price": 12.00,
                "stock_qty": 80,
                "unit": "pcs",
            },
            {
                "sku": "TEA-SP",
                "barcode": "1001003",
                "name": "Special Tea",
                "category": "Beverages",
                "unit_price": 30.00,
                "cost_price": 8.00,
                "stock_qty": 150,
                "unit": "cup",
            },
            {
                "sku": "JUICE-M",
                "barcode": "1001004",
                "name": "Fresh Mango Juice",
                "category": "Beverages",
                "unit_price": 55.00,
                "cost_price": 20.00,
                "stock_qty": 40,
                "unit": "glass",
            },
            {
                "sku": "DRESS-S-RED",
                "barcode": "2002002",
                "name": "Summer Dress - Red S",
                "category": "Apparel",
                "unit_price": 890.00,
                "cost_price": 450.00,
                "stock_qty": 12,
                "size": "S",
                "color": "Red",
                "unit": "pcs",
            },
        ]

        for d in demo_items:
            item = Item(**d)
            db.add(item)

        # Demo customer for Idda
        cust = Customer(
            code="C001",
            name="Abebe Kebede",
            phone="+251911223344",
            credit_limit=5000.00,
        )
        db.add(cust)

        # Default business mode
        db.add(SystemSetting(key="business_mode", value="retail"))

        await db.commit()
        print("✅ Demo data seeded successfully")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )
