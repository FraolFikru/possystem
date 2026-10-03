from typing import List, Optional
from fastapi import APIRouter, HTTPException
from app.schemas.schemas import CheckoutRequest, CustomerCreate
from app import sheets

router = APIRouter(prefix="/api", tags=["Transactions & Credit"])


@router.post("/checkout")
async def checkout(payload: CheckoutRequest):
    try:
        txn = sheets.create_transaction(payload.model_dump())
        return txn
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/transactions/today")
async def daily_analytics():
    return sheets.get_daily_analytics()


@router.get("/customers")
async def list_customers():
    return sheets.list_customers()


@router.post("/customers", status_code=201)
async def create_customer(payload: CustomerCreate):
    return sheets.create_customer(payload.model_dump())


@router.get("/customers/balances")
async def customer_balances():
    return sheets.list_credit_balances()


@router.post("/customers/{customer_id}/repay")
async def repay_credit(customer_id: int, amount: float, note: Optional[str] = None):
    try:
        return sheets.repay_credit(customer_id, amount, note or "Repayment")
    except ValueError as e:
        raise HTTPException(400, str(e))
