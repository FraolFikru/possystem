"""
Accounting & Transaction Engine.
Double-entry aware ledger: Cash, Telebirr, M-Pesa, Idda (customer debt).
"""
from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional, Dict, Any
import uuid
import json

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import (
    Transaction,
    TransactionLine,
    Customer,
    CustomerCredit,
    OfflineQueue,
    TransactionType,
    PaymentMethod,
)
from app.services.inventory_service import InventoryService


class TransactionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.inventory = InventoryService(db)

    def _gen_reference(self) -> str:
        return f"TXN-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    async def checkout(self, payload: Dict[str, Any]) -> Transaction:
        """
        Full checkout pipeline:
        1. Validate items & stock
        2. Deduct inventory (BOM / FEFO / simple)
        3. Create transaction + lines
        4. Handle Idda credit if applicable
        5. Queue offline if needed
        """
        items_data = payload["items"]
        payment_method = payload.get("payment_method", PaymentMethod.CASH)
        is_offline = payload.get("is_offline", False)
        hold = payload.get("hold", False)

        subtotal = Decimal("0")
        tax_total = Decimal("0")
        lines_to_create = []

        # Pre-validate & calculate
        for cart_item in items_data:
            item = await self.inventory.get_item(cart_item["item_id"])
            if not item or not item.is_active:
                raise ValueError(f"Item id={cart_item['item_id']} not found or inactive")

            qty = float(cart_item["quantity"])
            unit_price = Decimal(str(cart_item.get("unit_price") or item.unit_price))
            discount = Decimal(str(cart_item.get("discount", 0)))
            line_sub = (unit_price * Decimal(str(qty))) - discount
            line_tax = line_sub * Decimal(str(item.tax_rate))
            line_total = line_sub + line_tax

            # Stock check (skip for hold)
            if not hold:
                ok, msg, batch_id = await self.inventory.deduct_stock(item.id, qty)
                if not ok:
                    raise ValueError(msg)
            else:
                batch_id = None

            subtotal += line_sub
            tax_total += line_tax
            lines_to_create.append(
                {
                    "item_id": item.id,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "cost_price": item.cost_price,
                    "tax_rate": item.tax_rate,
                    "discount": discount,
                    "line_total": line_total,
                    "batch_id": batch_id,
                }
            )

        discount_amount = Decimal(str(payload.get("discount_amount", 0)))
        total = subtotal + tax_total - discount_amount

        # Payment breakdown
        amount_cash = Decimal(str(payload.get("amount_cash", 0)))
        amount_telebirr = Decimal(str(payload.get("amount_telebirr", 0)))
        amount_mpesa = Decimal(str(payload.get("amount_mpesa", 0)))
        amount_idda = Decimal(str(payload.get("amount_idda", 0)))
        amount_card = Decimal(str(payload.get("amount_card", 0)))

        # Auto-fill single payment method
        if payment_method == PaymentMethod.CASH and amount_cash == 0:
            amount_cash = total
        elif payment_method == PaymentMethod.TELEBIRR and amount_telebirr == 0:
            amount_telebirr = total
        elif payment_method == PaymentMethod.MPESA and amount_mpesa == 0:
            amount_mpesa = total
        elif payment_method == PaymentMethod.IDDA and amount_idda == 0:
            amount_idda = total
        elif payment_method == PaymentMethod.CARD and amount_card == 0:
            amount_card = total

        paid_sum = amount_cash + amount_telebirr + amount_mpesa + amount_idda + amount_card
        if not hold and abs(paid_sum - total) > Decimal("0.05"):
            # Allow small rounding difference
            if payment_method != PaymentMethod.MIXED:
                # Force balance for single method
                if payment_method == PaymentMethod.CASH:
                    amount_cash = total
                elif payment_method == PaymentMethod.TELEBIRR:
                    amount_telebirr = total
                # etc. – simplified

        status = "held" if hold else "completed"
        txn_type = TransactionType.SALE

        txn = Transaction(
            reference=self._gen_reference(),
            txn_type=txn_type,
            status=status,
            subtotal=subtotal,
            tax_amount=tax_total,
            discount_amount=discount_amount,
            total_amount=total,
            amount_cash=amount_cash,
            amount_telebirr=amount_telebirr,
            amount_mpesa=amount_mpesa,
            amount_idda=amount_idda,
            amount_card=amount_card,
            payment_method=payment_method,
            customer_id=payload.get("customer_id"),
            notes=payload.get("notes"),
            is_offline=is_offline,
            synced=not is_offline,
        )
        self.db.add(txn)
        await self.db.flush()

        for ld in lines_to_create:
            line = TransactionLine(transaction_id=txn.id, **ld)
            self.db.add(line)

        # Idda (customer debt)
        if amount_idda > 0 and payload.get("customer_id") and not hold:
            await self._record_credit(
                customer_id=payload["customer_id"],
                amount=amount_idda,  # positive = debt increases
                transaction_id=txn.id,
                note=f"Sale {txn.reference}",
            )

        # Offline queue
        if is_offline:
            await self._queue_offline(txn)

        await self.db.flush()
        # Reload with lines
        result = await self.db.execute(
            select(Transaction)
            .options(selectinload(Transaction.lines))
            .where(Transaction.id == txn.id)
        )
        return result.scalar_one()

    async def _record_credit(
        self,
        customer_id: int,
        amount: Decimal,
        transaction_id: Optional[int] = None,
        note: Optional[str] = None,
    ) -> CustomerCredit:
        # Current balance
        result = await self.db.execute(
            select(func.coalesce(func.sum(CustomerCredit.amount), 0)).where(
                CustomerCredit.customer_id == customer_id
            )
        )
        current = Decimal(str(result.scalar() or 0))
        new_balance = current + amount

        entry = CustomerCredit(
            customer_id=customer_id,
            transaction_id=transaction_id,
            amount=amount,
            balance_after=new_balance,
            note=note,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def record_repayment(
        self, customer_id: int, amount: Decimal, note: Optional[str] = None
    ) -> CustomerCredit:
        """Record a customer debt repayment (negative amount)."""
        if amount <= 0:
            raise ValueError("Repayment amount must be positive")
        return await self._record_credit(
            customer_id=customer_id,
            amount=-amount,
            note=note or "Repayment",
        )

    async def get_customer_balance(self, customer_id: int) -> Decimal:
        result = await self.db.execute(
            select(func.coalesce(func.sum(CustomerCredit.amount), 0)).where(
                CustomerCredit.customer_id == customer_id
            )
        )
        return Decimal(str(result.scalar() or 0))

    async def list_customer_balances(self) -> List[Dict]:
        # Aggregate per customer
        result = await self.db.execute(
            select(
                Customer.id,
                Customer.name,
                Customer.phone,
                Customer.credit_limit,
                func.coalesce(func.sum(CustomerCredit.amount), 0).label("balance"),
                func.max(CustomerCredit.created_at).label("last_activity"),
            )
            .outerjoin(CustomerCredit, Customer.id == CustomerCredit.customer_id)
            .where(Customer.is_active.is_(True))
            .group_by(Customer.id)
            .having(func.coalesce(func.sum(CustomerCredit.amount), 0) != 0)
            .order_by(func.coalesce(func.sum(CustomerCredit.amount), 0).desc())
        )
        rows = result.all()
        return [
            {
                "customer_id": r.id,
                "customer_name": r.name,
                "phone": r.phone,
                "current_balance": Decimal(str(r.balance)),
                "credit_limit": r.credit_limit,
                "available_credit": r.credit_limit - Decimal(str(r.balance)),
                "last_activity": r.last_activity,
            }
            for r in rows
        ]

    async def _queue_offline(self, txn: Transaction) -> None:
        payload = {
            "reference": txn.reference,
            "total": str(txn.total_amount),
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
        }
        q = OfflineQueue(
            payload=json.dumps(payload),
            entity_type="transaction",
            status="pending",
        )
        self.db.add(q)

    async def get_daily_analytics(self, target_date: Optional[date] = None) -> Dict:
        if target_date is None:
            target_date = date.today()

        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())

        result = await self.db.execute(
            select(
                func.coalesce(func.sum(Transaction.total_amount), 0).label("revenue"),
                func.coalesce(func.sum(Transaction.amount_cash), 0).label("cash"),
                func.coalesce(func.sum(Transaction.amount_telebirr), 0).label("telebirr"),
                func.coalesce(func.sum(Transaction.amount_mpesa), 0).label("mpesa"),
                func.coalesce(func.sum(Transaction.amount_idda), 0).label("idda"),
                func.coalesce(func.sum(Transaction.amount_card), 0).label("card"),
                func.count(Transaction.id).label("count"),
            ).where(
                and_(
                    Transaction.created_at >= start,
                    Transaction.created_at <= end,
                    Transaction.status == "completed",
                    Transaction.txn_type == TransactionType.SALE,
                )
            )
        )
        row = result.one()

        # Top items (simplified – join lines)
        top_q = await self.db.execute(
            select(
                TransactionLine.item_id,
                func.sum(TransactionLine.quantity).label("qty"),
                func.sum(TransactionLine.line_total).label("sales"),
            )
            .join(Transaction)
            .where(
                and_(
                    Transaction.created_at >= start,
                    Transaction.created_at <= end,
                    Transaction.status == "completed",
                )
            )
            .group_by(TransactionLine.item_id)
            .order_by(func.sum(TransactionLine.line_total).desc())
            .limit(5)
        )
        top_rows = top_q.all()
        top_items = []
        for tr in top_rows:
            item = await self.inventory.get_item(tr.item_id)
            top_items.append(
                {
                    "item_id": tr.item_id,
                    "name": item.name if item else "Unknown",
                    "quantity": float(tr.qty),
                    "sales": float(tr.sales),
                }
            )

        low_stock = await self.inventory.get_low_stock_items()
        low_alerts = [
            {
                "item_id": i.id,
                "sku": i.sku,
                "name": i.name,
                "stock_qty": i.stock_qty,
                "low_stock_threshold": i.low_stock_threshold,
                "unit": i.unit,
            }
            for i in low_stock
        ]

        # Outstanding credit
        credit_q = await self.db.execute(
            select(func.coalesce(func.sum(CustomerCredit.amount), 0))
        )
        total_credit = Decimal(str(credit_q.scalar() or 0))

        return {
            "date": target_date,
            "total_revenue": Decimal(str(row.revenue)),
            "cash_total": Decimal(str(row.cash)),
            "telebirr_total": Decimal(str(row.telebirr)),
            "mpesa_total": Decimal(str(row.mpesa)),
            "idda_total": Decimal(str(row.idda)),
            "card_total": Decimal(str(row.card)),
            "transaction_count": row.count,
            "top_items": top_items,
            "low_stock_alerts": low_alerts,
            "total_credit_outstanding": total_credit,
        }
