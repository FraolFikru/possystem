"""
Inventory Engine: stock tracking, COGS, FEFO deduction, BOM explosion.
"""
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Item, Ingredient, RecipeBOM, InventoryBatch, TransactionLine


class InventoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_item(self, item_id: int) -> Optional[Item]:
        result = await self.db.execute(
            select(Item)
            .options(selectinload(Item.recipe_components).selectinload(RecipeBOM.ingredient))
            .options(selectinload(Item.batches))
            .where(Item.id == item_id)
        )
        return result.scalar_one_or_none()

    async def get_item_by_sku(self, sku: str) -> Optional[Item]:
        result = await self.db.execute(select(Item).where(Item.sku == sku))
        return result.scalar_one_or_none()

    async def get_item_by_barcode(self, barcode: str) -> Optional[Item]:
        result = await self.db.execute(select(Item).where(Item.barcode == barcode))
        return result.scalar_one_or_none()

    async def list_items(
        self,
        category: Optional[str] = None,
        active_only: bool = True,
        search: Optional[str] = None,
    ) -> List[Item]:
        q = select(Item)
        if active_only:
            q = q.where(Item.is_active.is_(True))
        if category:
            q = q.where(Item.category == category)
        if search:
            like = f"%{search}%"
            q = q.where(
                (Item.name.ilike(like)) | (Item.sku.ilike(like)) | (Item.barcode.ilike(like))
            )
        q = q.order_by(Item.category, Item.name)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def create_item(self, data: dict) -> Item:
        item = Item(**data)
        self.db.add(item)
        await self.db.flush()
        return item

    async def update_item(self, item_id: int, data: dict) -> Optional[Item]:
        item = await self.get_item(item_id)
        if not item:
            return None
        for k, v in data.items():
            if v is not None and hasattr(item, k):
                setattr(item, k, v)
        await self.db.flush()
        return item

    # ─── Stock Deduction Pipeline ─────────────────────────────────────────────

    async def deduct_stock(
        self,
        item_id: int,
        quantity: float,
        prefer_fefo: bool = True,
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Deduct stock. Returns (success, message, batch_id_used).
        For pharmacy/grocery: FEFO (earliest expiry first).
        For restaurant recipes: explode BOM and deduct ingredients.
        """
        item = await self.get_item(item_id)
        if not item:
            return False, "Item not found", None

        # Recipe explosion (Restaurant mode)
        if item.is_recipe and item.recipe_components:
            return await self._deduct_recipe(item, quantity)

        # Batch-aware FEFO
        if item.requires_batch or item.requires_expiry:
            return await self._deduct_fefo(item, quantity)

        # Simple stock
        if item.stock_qty < quantity:
            return False, f"Insufficient stock for {item.name}. Available: {item.stock_qty}", None

        item.stock_qty -= quantity
        await self.db.flush()
        return True, "OK", None

    async def _deduct_recipe(self, product: Item, qty: float) -> Tuple[bool, str, None]:
        """Explode BOM and deduct fractional ingredients."""
        for bom in product.recipe_components:
            needed = bom.quantity * qty * bom.waste_factor
            ing = bom.ingredient
            if ing.stock_qty < needed:
                return (
                    False,
                    f"Insufficient {ing.name} for {product.name}. Need {needed:.2f}{ing.unit}, have {ing.stock_qty}",
                    None,
                )
        # All good – deduct
        for bom in product.recipe_components:
            needed = bom.quantity * qty * bom.waste_factor
            bom.ingredient.stock_qty -= needed
        # Also reduce finished goods if tracked
        if product.stock_qty >= qty:
            product.stock_qty -= qty
        await self.db.flush()
        return True, "BOM deducted", None

    async def _deduct_fefo(self, item: Item, quantity: float) -> Tuple[bool, str, Optional[int]]:
        """First-Expiry-First-Out deduction across batches."""
        today = date.today()
        result = await self.db.execute(
            select(InventoryBatch)
            .where(
                and_(
                    InventoryBatch.item_id == item.id,
                    InventoryBatch.is_active.is_(True),
                    InventoryBatch.quantity > 0,
                )
            )
            .order_by(InventoryBatch.expiry_date.asc().nullslast())
        )
        batches = list(result.scalars().all())

        remaining = quantity
        last_batch_id = None
        for batch in batches:
            if remaining <= 0:
                break
            take = min(batch.quantity, remaining)
            batch.quantity -= take
            remaining -= take
            last_batch_id = batch.id
            if batch.quantity <= 0:
                batch.is_active = False

        if remaining > 0:
            return False, f"Insufficient batch stock for {item.name}", None

        # Keep item.stock_qty in sync
        item.stock_qty = max(0, item.stock_qty - quantity)
        await self.db.flush()
        return True, "FEFO deducted", last_batch_id

    async def add_stock(
        self,
        item_id: int,
        quantity: float,
        batch_number: Optional[str] = None,
        expiry_date: Optional[date] = None,
        cost_per_unit: Decimal = Decimal("0"),
    ) -> Tuple[bool, str]:
        item = await self.get_item(item_id)
        if not item:
            return False, "Item not found"

        if item.requires_batch and batch_number:
            batch = InventoryBatch(
                item_id=item_id,
                batch_number=batch_number,
                quantity=quantity,
                cost_per_unit=cost_per_unit,
                expiry_date=expiry_date,
            )
            self.db.add(batch)

        item.stock_qty += quantity
        await self.db.flush()
        return True, "Stock added"

    async def get_low_stock_items(self) -> List[Item]:
        result = await self.db.execute(
            select(Item).where(
                and_(Item.is_active.is_(True), Item.stock_qty <= Item.low_stock_threshold)
            )
        )
        return list(result.scalars().all())

    # ─── Ingredients (Restaurant) ─────────────────────────────────────────────

    async def list_ingredients(self) -> List[Ingredient]:
        result = await self.db.execute(
            select(Ingredient).where(Ingredient.is_active.is_(True)).order_by(Ingredient.name)
        )
        return list(result.scalars().all())

    async def create_ingredient(self, data: dict) -> Ingredient:
        ing = Ingredient(**data)
        self.db.add(ing)
        await self.db.flush()
        return ing

    async def add_recipe_line(self, data: dict) -> RecipeBOM:
        bom = RecipeBOM(**data)
        self.db.add(bom)
        # Mark product as recipe
        item = await self.get_item(data["product_id"])
        if item:
            item.is_recipe = True
        await self.db.flush()
        return bom
