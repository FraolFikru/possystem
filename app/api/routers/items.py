"""Item / Inventory API router."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.schemas import (
    ItemCreate,
    ItemUpdate,
    ItemOut,
    IngredientCreate,
    IngredientOut,
    RecipeBOMCreate,
    RecipeBOMOut,
    InventoryBatchCreate,
    InventoryBatchOut,
)
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/api/items", tags=["Items & Inventory"])


@router.get("", response_model=List[ItemOut])
async def list_items(
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    svc = InventoryService(db)
    items = await svc.list_items(category=category, search=search)
    return items


@router.get("/{item_id}", response_model=ItemOut)
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    svc = InventoryService(db)
    item = await svc.get_item(item_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item


@router.post("", response_model=ItemOut, status_code=201)
async def create_item(payload: ItemCreate, db: AsyncSession = Depends(get_db)):
    svc = InventoryService(db)
    existing = await svc.get_item_by_sku(payload.sku)
    if existing:
        raise HTTPException(400, f"SKU {payload.sku} already exists")
    item = await svc.create_item(payload.model_dump())
    return item


@router.patch("/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: int, payload: ItemUpdate, db: AsyncSession = Depends(get_db)
):
    svc = InventoryService(db)
    item = await svc.update_item(item_id, payload.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(404, "Item not found")
    return item


@router.post("/{item_id}/stock", response_model=ItemOut)
async def add_stock(
    item_id: int,
    quantity: float = Query(..., gt=0),
    batch_number: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    svc = InventoryService(db)
    ok, msg = await svc.add_stock(item_id, quantity, batch_number=batch_number)
    if not ok:
        raise HTTPException(400, msg)
    item = await svc.get_item(item_id)
    return item


@router.get("/lookup/barcode/{barcode}", response_model=ItemOut)
async def lookup_barcode(barcode: str, db: AsyncSession = Depends(get_db)):
    svc = InventoryService(db)
    item = await svc.get_item_by_barcode(barcode)
    if not item:
        raise HTTPException(404, "Barcode not found")
    return item


# ─── Ingredients & BOM ───────────────────────────────────────────────────────

@router.get("/ingredients/list", response_model=List[IngredientOut])
async def list_ingredients(db: AsyncSession = Depends(get_db)):
    svc = InventoryService(db)
    return await svc.list_ingredients()


@router.post("/ingredients", response_model=IngredientOut, status_code=201)
async def create_ingredient(payload: IngredientCreate, db: AsyncSession = Depends(get_db)):
    svc = InventoryService(db)
    return await svc.create_ingredient(payload.model_dump())


@router.post("/bom", response_model=RecipeBOMOut, status_code=201)
async def add_bom_line(payload: RecipeBOMCreate, db: AsyncSession = Depends(get_db)):
    svc = InventoryService(db)
    return await svc.add_recipe_line(payload.model_dump())


@router.post("/batches", response_model=InventoryBatchOut, status_code=201)
async def create_batch(payload: InventoryBatchCreate, db: AsyncSession = Depends(get_db)):
    from app.models.models import InventoryBatch
    batch = InventoryBatch(**payload.model_dump())
    db.add(batch)
    # also bump item stock
    svc = InventoryService(db)
    await svc.add_stock(payload.item_id, payload.quantity)
    await db.flush()
    return batch
