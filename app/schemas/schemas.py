from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class PaymentMethod(str, Enum):
    CASH = "cash"
    TELEBIRR = "telebirr"
    MPESA = "mpesa"
    IDDA = "idda"
    CARD = "card"
    MIXED = "mixed"


class CartItem(BaseModel):
    item_id: int
    quantity: float = Field(..., gt=0)
    unit_price: Optional[float] = None
    discount: float = 0


class CheckoutRequest(BaseModel):
    items: List[CartItem]
    payment_method: PaymentMethod = PaymentMethod.CASH
    amount_cash: float = 0
    amount_telebirr: float = 0
    amount_mpesa: float = 0
    amount_idda: float = 0
    amount_card: float = 0
    customer_id: Optional[int] = None
    discount_amount: float = 0
    notes: Optional[str] = None


class ItemCreate(BaseModel):
    sku: str
    barcode: Optional[str] = None
    name: str
    category: str = "General"
    unit_price: float
    cost_price: float = 0
    stock_qty: float = 0
    low_stock_threshold: float = 5
    unit: str = "pcs"
    size: Optional[str] = None
    color: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    unit_price: Optional[float] = None
    cost_price: Optional[float] = None
    stock_qty: Optional[float] = None
    low_stock_threshold: Optional[float] = None
    unit: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerCreate(BaseModel):
    code: str
    name: str
    phone: Optional[str] = None
    credit_limit: float = 0
