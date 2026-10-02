"""Pydantic v2 schemas for request validation & response serialization."""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ─── Enums mirrored from models ──────────────────────────────────────────────

class ItemType(str, Enum):
    PRODUCT = "product"
    INGREDIENT = "ingredient"
    SERVICE = "service"


class PaymentMethod(str, Enum):
    CASH = "cash"
    TELEBIRR = "telebirr"
    MPESA = "mpesa"
    IDDA = "idda"
    CARD = "card"
    MIXED = "mixed"


class TransactionType(str, Enum):
    SALE = "sale"
    REFUND = "refund"
    STOCK_ADJUST = "stock_adjust"
    CREDIT_PAYMENT = "credit_payment"
    EXPENSE = "expense"


class OrderStatus(str, Enum):
    OPEN = "open"
    SENT_TO_KITCHEN = "sent_to_kitchen"
    READY = "ready"
    BILLED = "billed"
    PAID = "paid"
    CANCELLED = "cancelled"
    HELD = "held"


class BusinessMode(str, Enum):
    RESTAURANT = "restaurant"
    RETAIL = "retail"
    PHARMACY = "pharmacy"
    GROCERY = "grocery"


# ─── Item / Catalog ──────────────────────────────────────────────────────────

class ItemBase(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    barcode: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: str = "General"
    item_type: ItemType = ItemType.PRODUCT
    unit_price: Decimal = Field(..., ge=0)
    cost_price: Decimal = Field(default=Decimal("0"), ge=0)
    tax_rate: float = Field(default=0.15, ge=0, le=1)
    stock_qty: float = Field(default=0, ge=0)
    low_stock_threshold: float = Field(default=5.0, ge=0)
    unit: str = "pcs"
    size: Optional[str] = None
    color: Optional[str] = None
    requires_batch: bool = False
    requires_expiry: bool = False
    is_recipe: bool = False
    is_active: bool = True


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    unit_price: Optional[Decimal] = None
    cost_price: Optional[Decimal] = None
    tax_rate: Optional[float] = None
    stock_qty: Optional[float] = None
    low_stock_threshold: Optional[float] = None
    unit: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    requires_batch: Optional[bool] = None
    requires_expiry: Optional[bool] = None
    is_recipe: Optional[bool] = None
    is_active: Optional[bool] = None
    barcode: Optional[str] = None


class ItemOut(ItemBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ─── Ingredient & BOM ────────────────────────────────────────────────────────

class IngredientCreate(BaseModel):
    code: str
    name: str
    unit: str = "g"
    stock_qty: float = 0
    cost_per_unit: Decimal = Decimal("0")
    low_stock_threshold: float = 100.0


class IngredientOut(IngredientCreate):
    id: int
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class RecipeBOMCreate(BaseModel):
    product_id: int
    ingredient_id: int
    quantity: float = Field(..., gt=0)
    unit: str = "g"
    waste_factor: float = Field(default=1.0, ge=1.0)


class RecipeBOMOut(RecipeBOMCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ─── Inventory Batch ─────────────────────────────────────────────────────────

class InventoryBatchCreate(BaseModel):
    item_id: int
    batch_number: str
    quantity: float = Field(..., gt=0)
    cost_per_unit: Decimal = Decimal("0")
    manufacture_date: Optional[date] = None
    expiry_date: Optional[date] = None


class InventoryBatchOut(InventoryBatchCreate):
    id: int
    received_at: datetime
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


# ─── Customer & Credit ───────────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    code: str
    name: str
    phone: Optional[str] = None
    telegram_id: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    credit_limit: Decimal = Decimal("0")


class CustomerOut(CustomerCreate):
    id: int
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CustomerCreditCreate(BaseModel):
    customer_id: int
    amount: Decimal  # positive = debt, negative = repayment
    note: Optional[str] = None
    transaction_id: Optional[int] = None


class CustomerCreditOut(BaseModel):
    id: int
    customer_id: int
    amount: Decimal
    balance_after: Decimal
    note: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CustomerBalanceOut(BaseModel):
    customer_id: int
    customer_name: str
    phone: Optional[str]
    current_balance: Decimal
    credit_limit: Decimal
    available_credit: Decimal
    last_activity: Optional[datetime]


# ─── Cart & Checkout ─────────────────────────────────────────────────────────

class CartItem(BaseModel):
    item_id: int
    quantity: float = Field(..., gt=0)
    unit_price: Optional[Decimal] = None  # override if needed
    discount: Decimal = Decimal("0")
    notes: Optional[str] = None


class CheckoutRequest(BaseModel):
    items: List[CartItem]
    payment_method: PaymentMethod = PaymentMethod.CASH
    amount_cash: Decimal = Decimal("0")
    amount_telebirr: Decimal = Decimal("0")
    amount_mpesa: Decimal = Decimal("0")
    amount_idda: Decimal = Decimal("0")
    amount_card: Decimal = Decimal("0")
    customer_id: Optional[int] = None
    discount_amount: Decimal = Decimal("0")
    notes: Optional[str] = None
    table_number: Optional[str] = None  # restaurant
    is_offline: bool = False
    hold: bool = False  # hold ticket instead of completing


class TransactionLineOut(BaseModel):
    id: int
    item_id: int
    quantity: float
    unit_price: Decimal
    line_total: Decimal
    model_config = ConfigDict(from_attributes=True)


class TransactionOut(BaseModel):
    id: int
    reference: str
    txn_type: TransactionType
    status: str
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    amount_cash: Decimal
    amount_telebirr: Decimal
    amount_mpesa: Decimal
    amount_idda: Decimal
    amount_card: Decimal
    payment_method: PaymentMethod
    customer_id: Optional[int]
    notes: Optional[str]
    is_offline: bool
    created_at: datetime
    lines: List[TransactionLineOut] = []
    model_config = ConfigDict(from_attributes=True)


# ─── Orders (Restaurant) ─────────────────────────────────────────────────────

class OrderItemCreate(BaseModel):
    item_id: int
    quantity: float = 1
    notes: Optional[str] = None


class OrderCreate(BaseModel):
    table_number: Optional[str] = None
    customer_name: Optional[str] = None
    covers: int = 1
    items: List[OrderItemCreate]
    notes: Optional[str] = None


class OrderOut(BaseModel):
    id: int
    order_number: str
    table_number: Optional[str]
    status: OrderStatus
    customer_name: Optional[str]
    covers: int
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    notes: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ─── Analytics ───────────────────────────────────────────────────────────────

class LowStockAlert(BaseModel):
    item_id: int
    sku: str
    name: str
    stock_qty: float
    low_stock_threshold: float
    unit: str


class AnalyticsSummary(BaseModel):
    date: date
    total_revenue: Decimal
    cash_total: Decimal
    telebirr_total: Decimal
    mpesa_total: Decimal
    idda_total: Decimal
    card_total: Decimal
    transaction_count: int
    top_items: List[dict]
    low_stock_alerts: List[LowStockAlert]
    open_orders: int = 0
    total_credit_outstanding: Decimal = Decimal("0")


# ─── System ──────────────────────────────────────────────────────────────────

class BusinessModeUpdate(BaseModel):
    mode: BusinessMode


class SystemSettingOut(BaseModel):
    key: str
    value: str
    model_config = ConfigDict(from_attributes=True)
