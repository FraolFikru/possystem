"""
SQLAlchemy 2.0 Async Models for SME POS System.
Supports Restaurant (BOM), Retail (variants), Pharmacy/Grocery (FEFO batches).
Double-entry aware transaction ledger + Customer Credit (Idda).
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from enum import Enum as PyEnum

from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Date,
    Text,
    ForeignKey,
    Numeric,
    Enum,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


# ─── Enums ───────────────────────────────────────────────────────────────────

class ItemType(str, PyEnum):
    PRODUCT = "product"          # Finished goods / menu items
    INGREDIENT = "ingredient"    # Raw materials (restaurant)
    SERVICE = "service"


class PaymentMethod(str, PyEnum):
    CASH = "cash"
    TELEBIRR = "telebirr"
    MPESA = "mpesa"
    IDDA = "idda"                # Customer credit / debt
    CARD = "card"
    MIXED = "mixed"


class TransactionType(str, PyEnum):
    SALE = "sale"
    REFUND = "refund"
    STOCK_ADJUST = "stock_adjust"
    CREDIT_PAYMENT = "credit_payment"
    EXPENSE = "expense"


class OrderStatus(str, PyEnum):
    OPEN = "open"
    SENT_TO_KITCHEN = "sent_to_kitchen"
    READY = "ready"
    BILLED = "billed"
    PAID = "paid"
    CANCELLED = "cancelled"
    HELD = "held"


class BusinessMode(str, PyEnum):
    RESTAURANT = "restaurant"
    RETAIL = "retail"
    PHARMACY = "pharmacy"
    GROCERY = "grocery"


# ─── Core Catalog ────────────────────────────────────────────────────────────

class Item(Base):
    """
    Unified product / menu item / SKU.
    Sector-specific fields are nullable and activated by business mode.
    """
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    barcode: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), default="General", index=True)

    item_type: Mapped[ItemType] = mapped_column(
        Enum(ItemType), default=ItemType.PRODUCT, nullable=False
    )

    # Pricing
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.15)  # VAT

    # Inventory
    stock_qty: Mapped[float] = mapped_column(Float, default=0.0)  # current available
    low_stock_threshold: Mapped[float] = mapped_column(Float, default=5.0)
    unit: Mapped[str] = mapped_column(String(20), default="pcs")  # pcs, kg, ml, etc.

    # Retail / Boutique variants
    size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    variant_of_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("items.id"), nullable=True
    )

    # Pharmacy / Grocery
    requires_batch: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_expiry: Mapped[bool] = mapped_column(Boolean, default=False)

    # Restaurant
    is_recipe: Mapped[bool] = mapped_column(Boolean, default=False)  # has BOM

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    recipe_components: Mapped[List["RecipeBOM"]] = relationship(
        "RecipeBOM",
        foreign_keys="RecipeBOM.product_id",
        back_populates="product",
        cascade="all, delete-orphan",
    )
    batches: Mapped[List["InventoryBatch"]] = relationship(
        "InventoryBatch", back_populates="item", cascade="all, delete-orphan"
    )
    variants: Mapped[List["Item"]] = relationship("Item", backref="parent_item")

    def __repr__(self) -> str:
        return f"<Item {self.sku}: {self.name}>"


class Ingredient(Base):
    """
    Raw material / ingredient used in restaurant BOM.
    Can also be tracked as an Item of type INGREDIENT.
    """
    __tablename__ = "ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="g")  # g, ml, pcs
    stock_qty: Mapped[float] = mapped_column(Float, default=0.0)
    cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    low_stock_threshold: Mapped[float] = mapped_column(Float, default=100.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    recipe_usages: Mapped[List["RecipeBOM"]] = relationship(
        "RecipeBOM", back_populates="ingredient"
    )


class RecipeBOM(Base):
    """
    Bill of Materials / Recipe line.
    Selling 1 unit of product deducts (quantity * yield_factor) of ingredient.
    """
    __tablename__ = "recipe_bom"
    __table_args__ = (
        UniqueConstraint("product_id", "ingredient_id", name="uq_product_ingredient"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"), nullable=False)
    ingredient_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ingredients.id"), nullable=False
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)  # amount per 1 product unit
    unit: Mapped[str] = mapped_column(String(20), default="g")
    waste_factor: Mapped[float] = mapped_column(Float, default=1.0)  # 1.05 = 5% waste

    product: Mapped["Item"] = relationship(
        "Item", foreign_keys=[product_id], back_populates="recipe_components"
    )
    ingredient: Mapped["Ingredient"] = relationship(
        "Ingredient", back_populates="recipe_usages"
    )


class InventoryBatch(Base):
    """
    Batch tracking for Pharmacy / Grocery (FEFO - First Expiry First Out).
    """
    __tablename__ = "inventory_batches"
    __table_args__ = (
        Index("ix_batch_expiry", "item_id", "expiry_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"), nullable=False)
    batch_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    manufacture_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    item: Mapped["Item"] = relationship("Item", back_populates="batches")


# ─── Customers & Credit (Idda) ────────────────────────────────────────────────

class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    telegram_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    credits: Mapped[List["CustomerCredit"]] = relationship(
        "CustomerCredit", back_populates="customer", cascade="all, delete-orphan"
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="customer"
    )


class CustomerCredit(Base):
    """
    Idda ledger entry – debt or repayment.
    Positive amount = customer owes business.
    Negative amount = repayment / credit note.
    """
    __tablename__ = "customer_credits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False)
    transaction_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("transactions.id"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)  # +debt / -repay
    balance_after: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="credits")
    transaction: Mapped[Optional["Transaction"]] = relationship(
        "Transaction", back_populates="credit_entry"
    )


# ─── Transactions & Ledger ───────────────────────────────────────────────────

class Transaction(Base):
    """
    Core financial transaction (sale, refund, credit payment…).
    Supports double-entry style via payment method breakdown.
    """
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    txn_type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType), default=TransactionType.SALE
    )
    status: Mapped[str] = mapped_column(String(30), default="completed")  # completed, held, void

    # Amounts
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    # Payment breakdown (double-entry friendly)
    amount_cash: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    amount_telebirr: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    amount_mpesa: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    amount_idda: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    amount_card: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod), default=PaymentMethod.CASH
    )

    customer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True
    )
    order_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("orders.id"), nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_offline: Mapped[bool] = mapped_column(Boolean, default=False)
    synced: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    customer: Mapped[Optional["Customer"]] = relationship(
        "Customer", back_populates="transactions"
    )
    lines: Mapped[List["TransactionLine"]] = relationship(
        "TransactionLine", back_populates="transaction", cascade="all, delete-orphan"
    )
    credit_entry: Mapped[Optional["CustomerCredit"]] = relationship(
        "CustomerCredit", back_populates="transaction", uselist=False
    )
    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="transaction")


class TransactionLine(Base):
    __tablename__ = "transaction_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("transactions.id"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.15)
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Batch used (pharmacy FEFO)
    batch_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("inventory_batches.id"), nullable=True
    )

    transaction: Mapped["Transaction"] = relationship(
        "Transaction", back_populates="lines"
    )
    item: Mapped["Item"] = relationship("Item")


# ─── Restaurant Orders ───────────────────────────────────────────────────────

class Order(Base):
    """
    Open table / ticket for restaurant mode.
    Flow: Open → Kitchen → Ready → Bill → Paid
    """
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    table_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.OPEN
    )
    customer_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    covers: Mapped[int] = mapped_column(Integer, default=1)  # number of guests

    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    transaction: Mapped[Optional["Transaction"]] = relationship(
        "Transaction", back_populates="order", uselist=False
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_sent_to_kitchen: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ready: Mapped[bool] = mapped_column(Boolean, default=False)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    item: Mapped["Item"] = relationship("Item")


# ─── System & Offline ────────────────────────────────────────────────────────

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class OfflineQueue(Base):
    """
    Local queue for transactions created while offline.
    Synced when connectivity returns.
    """
    __tablename__ = "offline_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON serialized
    entity_type: Mapped[str] = mapped_column(String(50), default="transaction")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, synced, failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
