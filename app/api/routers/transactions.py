"""Checkout, Transactions, Customer Credit (Idda) API."""
from typing import List, Optional
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.schemas.schemas import (
    CheckoutRequest,
    TransactionOut,
    CustomerCreate,
    CustomerOut,
    CustomerCreditCreate,
    CustomerCreditOut,
    CustomerBalanceOut,
    AnalyticsSummary,
)
from app.services.transaction_service import TransactionService
from app.models.models import Customer, CustomerCredit

router = APIRouter(prefix="/api", tags=["Transactions & Credit"])


@router.post("/checkout", response_model=TransactionOut)
async def checkout(payload: CheckoutRequest, db: AsyncSession = Depends(get_db)):
    svc = TransactionService(db)
    try:
        txn = await svc.checkout(payload.model_dump())
        return txn
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/transactions/today", response_model=AnalyticsSummary)
async def daily_analytics(
    target_date: Optional[date] = None, db: AsyncSession = Depends(get_db)
):
    svc = TransactionService(db)
    data = await svc.get_daily_analytics(target_date)
    return data


# ─── Customers ───────────────────────────────────────────────────────────────

@router.get("/customers", response_model=List[CustomerOut])
async def list_customers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Customer).where(Customer.is_active.is_(True)).order_by(Customer.name)
    )
    return list(result.scalars().all())


@router.post("/customers", response_model=CustomerOut, status_code=201)
async def create_customer(payload: CustomerCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Customer).where(Customer.code == payload.code))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Customer code already exists")
    cust = Customer(**payload.model_dump())
    db.add(cust)
    await db.flush()
    return cust


@router.get("/customers/balances", response_model=List[CustomerBalanceOut])
async def customer_balances(db: AsyncSession = Depends(get_db)):
    svc = TransactionService(db)
    return await svc.list_customer_balances()


@router.post("/customers/{customer_id}/repay", response_model=CustomerCreditOut)
async def repay_credit(
    customer_id: int,
    amount: Decimal,
    note: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    svc = TransactionService(db)
    try:
        entry = await svc.record_repayment(customer_id, amount, note)
        return entry
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/customers/{customer_id}/ledger", response_model=List[CustomerCreditOut])
async def customer_ledger(customer_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CustomerCredit)
        .where(CustomerCredit.customer_id == customer_id)
        .order_by(CustomerCredit.created_at.desc())
    )
    return list(result.scalars().all())
