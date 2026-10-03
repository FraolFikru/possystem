"""
Google Sheets database layer.
Replaces SQLAlchemy + SQLite.
"""
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional, Dict, Any
import uuid
from functools import lru_cache

from app.core.config import get_settings

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

settings = get_settings()


@lru_cache()
def get_client():
    creds = Credentials.from_service_account_file(
        settings.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    return gspread.authorize(creds)


def get_sheet(tab_name: str):
    client = get_client()
    spreadsheet = client.open_by_key(settings.GOOGLE_SHEET_ID)
    return spreadsheet.worksheet(tab_name)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().isoformat()


def _to_float(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _row_to_dict(headers: List[str], row: List[str]) -> Dict[str, Any]:
    return {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}


def _next_id(ws) -> int:
    """Simple auto-increment using the last ID in column A."""
    values = ws.col_values(1)[1:]  # skip header
    ids = [int(v) for v in values if str(v).isdigit()]
    return max(ids) + 1 if ids else 1


# ─── Items ──────────────────────────────────────────────────────────────────

def list_items(active_only: bool = True) -> List[Dict]:
    ws = get_sheet("Items")
    records = ws.get_all_records()
    if active_only:
        records = [r for r in records if str(r.get("is_active", "TRUE")).upper() in ("TRUE", "1", "YES")]
    return records


def get_item(item_id: int) -> Optional[Dict]:
    items = list_items(active_only=False)
    for item in items:
        if int(item.get("id", 0)) == item_id:
            return item
    return None


def get_item_by_sku(sku: str) -> Optional[Dict]:
    for item in list_items(active_only=False):
        if str(item.get("sku", "")).lower() == sku.lower():
            return item
    return None


def create_item(data: Dict) -> Dict:
    ws = get_sheet("Items")
    new_id = _next_id(ws)
    row = [
        new_id,
        data.get("sku", ""),
        data.get("barcode", ""),
        data.get("name", ""),
        data.get("category", "General"),
        data.get("unit_price", 0),
        data.get("cost_price", 0),
        data.get("stock_qty", 0),
        data.get("low_stock_threshold", 5),
        data.get("unit", "pcs"),
        data.get("size", ""),
        data.get("color", ""),
        data.get("requires_batch", False),
        data.get("requires_expiry", False),
        data.get("is_recipe", False),
        True,  # is_active
        _now(),
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    return get_item(new_id)


def update_item(item_id: int, data: Dict) -> Optional[Dict]:
    ws = get_sheet("Items")
    records = ws.get_all_records()
    headers = ws.row_values(1)

    for idx, record in enumerate(records, start=2):  # row 1 = header
        if int(record.get("id", 0)) == item_id:
            for key, value in data.items():
                if key in headers and value is not None:
                    col = headers.index(key) + 1
                    ws.update_cell(idx, col, value)
            return get_item(item_id)
    return None


def update_stock(item_id: int, new_qty: float) -> bool:
    return update_item(item_id, {"stock_qty": new_qty}) is not None


# ─── Customers ──────────────────────────────────────────────────────────────

def list_customers() -> List[Dict]:
    ws = get_sheet("Customers")
    return ws.get_all_records()


def get_customer(customer_id: int) -> Optional[Dict]:
    for c in list_customers():
        if int(c.get("id", 0)) == customer_id:
            return c
    return None


def create_customer(data: Dict) -> Dict:
    ws = get_sheet("Customers")
    new_id = _next_id(ws)
    row = [
        new_id,
        data.get("code", ""),
        data.get("name", ""),
        data.get("phone", ""),
        data.get("credit_limit", 0),
        True,
        _now(),
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")
    return get_customer(new_id)


# ─── Transactions ───────────────────────────────────────────────────────────

def create_transaction(payload: Dict) -> Dict:
    """
    Full checkout:
    - Create transaction
    - Create transaction lines
    - Deduct stock
    - Handle Idda credit if needed
    """
    ws_txn = get_sheet("Transactions")
    ws_lines = get_sheet("TransactionLines")

    txn_id = _next_id(ws_txn)
    reference = f"TXN-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    items = payload.get("items", [])
    subtotal = 0.0
    tax_total = 0.0
    lines = []

    for cart_item in items:
        item = get_item(int(cart_item["item_id"]))
        if not item:
            raise ValueError(f"Item {cart_item['item_id']} not found")

        qty = float(cart_item["quantity"])
        unit_price = float(cart_item.get("unit_price") or item.get("unit_price", 0))
        line_sub = unit_price * qty
        line_tax = line_sub * 0.15
        line_total = line_sub + line_tax

        # stock check + deduct
        current_stock = _to_float(item.get("stock_qty", 0))
        if current_stock < qty:
            raise ValueError(f"Insufficient stock for {item.get('name')}")

        update_stock(int(item["id"]), current_stock - qty)

        subtotal += line_sub
        tax_total += line_tax
        lines.append({
            "item_id": int(item["id"]),
            "quantity": qty,
            "unit_price": unit_price,
            "line_total": line_total,
        })

    discount = float(payload.get("discount_amount", 0))
    total = subtotal + tax_total - discount

    payment_method = payload.get("payment_method", "cash")
    amount_cash = float(payload.get("amount_cash", 0))
    amount_telebirr = float(payload.get("amount_telebirr", 0))
    amount_idda = float(payload.get("amount_idda", 0))
    amount_mpesa = float(payload.get("amount_mpesa", 0))
    amount_card = float(payload.get("amount_card", 0))

    # Auto-fill single method
    if payment_method == "cash" and amount_cash == 0:
        amount_cash = total
    elif payment_method == "telebirr" and amount_telebirr == 0:
        amount_telebirr = total
    elif payment_method == "idda" and amount_idda == 0:
        amount_idda = total
    elif payment_method == "mpesa" and amount_mpesa == 0:
        amount_mpesa = total
    elif payment_method == "card" and amount_card == 0:
        amount_card = total

    # Write transaction
    txn_row = [
        txn_id,
        reference,
        "completed",
        round(subtotal, 2),
        round(tax_total, 2),
        round(discount, 2),
        round(total, 2),
        round(amount_cash, 2),
        round(amount_telebirr, 2),
        round(amount_mpesa, 2),
        round(amount_idda, 2),
        round(amount_card, 2),
        payment_method,
        payload.get("customer_id") or "",
        payload.get("notes") or "",
        _now(),
    ]
    ws_txn.append_row(txn_row, value_input_option="USER_ENTERED")

    # Write lines
    for line in lines:
        line_id = _next_id(ws_lines)
        ws_lines.append_row([
            line_id,
            txn_id,
            line["item_id"],
            line["quantity"],
            line["unit_price"],
            line["line_total"],
        ], value_input_option="USER_ENTERED")

    # Idda credit
    if amount_idda > 0 and payload.get("customer_id"):
        record_credit(
            customer_id=int(payload["customer_id"]),
            amount=amount_idda,
            note=f"Sale {reference}",
        )

    return {
        "id": txn_id,
        "reference": reference,
        "status": "completed",
        "subtotal": subtotal,
        "tax_amount": tax_total,
        "discount_amount": discount,
        "total_amount": total,
        "amount_cash": amount_cash,
        "amount_telebirr": amount_telebirr,
        "amount_mpesa": amount_mpesa,
        "amount_idda": amount_idda,
        "amount_card": amount_card,
        "payment_method": payment_method,
        "customer_id": payload.get("customer_id"),
        "created_at": _now(),
        "lines": lines,
    }


# ─── Credits (Idda) ─────────────────────────────────────────────────────────

def record_credit(customer_id: int, amount: float, note: str = "") -> Dict:
    ws = get_sheet("Credits")
    # current balance
    records = ws.get_all_records()
    current = sum(_to_float(r.get("amount", 0)) for r in records if int(r.get("customer_id", 0)) == customer_id)
    new_balance = current + amount

    new_id = _next_id(ws)
    ws.append_row([
        new_id,
        customer_id,
        round(amount, 2),
        round(new_balance, 2),
        note,
        _now(),
    ], value_input_option="USER_ENTERED")

    return {
        "id": new_id,
        "customer_id": customer_id,
        "amount": amount,
        "balance_after": new_balance,
        "note": note,
        "created_at": _now(),
    }


def list_credit_balances() -> List[Dict]:
    ws = get_sheet("Credits")
    records = ws.get_all_records()
    customers = {int(c["id"]): c for c in list_customers()}

    balances = {}
    for r in records:
        cid = int(r.get("customer_id", 0))
        balances[cid] = balances.get(cid, 0) + _to_float(r.get("amount", 0))

    result = []
    for cid, balance in balances.items():
        if abs(balance) < 0.01:
            continue
        cust = customers.get(cid, {})
        result.append({
            "customer_id": cid,
            "customer_name": cust.get("name", "Unknown"),
            "phone": cust.get("phone", ""),
            "current_balance": round(balance, 2),
            "credit_limit": _to_float(cust.get("credit_limit", 0)),
            "available_credit": round(_to_float(cust.get("credit_limit", 0)) - balance, 2),
        })
    return sorted(result, key=lambda x: x["current_balance"], reverse=True)


def repay_credit(customer_id: int, amount: float, note: str = "Repayment") -> Dict:
    if amount <= 0:
        raise ValueError("Amount must be positive")
    return record_credit(customer_id, -amount, note)


# ─── Analytics ──────────────────────────────────────────────────────────────

def get_daily_analytics() -> Dict:
    ws = get_sheet("Transactions")
    records = ws.get_all_records()
    today = date.today().isoformat()

    today_txns = [r for r in records if str(r.get("created_at", "")).startswith(today)]

    revenue = sum(_to_float(r.get("total_amount", 0)) for r in today_txns)
    cash = sum(_to_float(r.get("amount_cash", 0)) for r in today_txns)
    telebirr = sum(_to_float(r.get("amount_telebirr", 0)) for r in today_txns)
    idda = sum(_to_float(r.get("amount_idda", 0)) for r in today_txns)

    # low stock
    low_stock = []
    for item in list_items():
        qty = _to_float(item.get("stock_qty", 0))
        threshold = _to_float(item.get("low_stock_threshold", 5))
        if qty <= threshold:
            low_stock.append({
                "item_id": item.get("id"),
                "sku": item.get("sku"),
                "name": item.get("name"),
                "stock_qty": qty,
                "low_stock_threshold": threshold,
                "unit": item.get("unit", "pcs"),
            })

    # outstanding credit
    total_credit = sum(b["current_balance"] for b in list_credit_balances())

    return {
        "date": today,
        "total_revenue": round(revenue, 2),
        "cash_total": round(cash, 2),
        "telebirr_total": round(telebirr, 2),
        "mpesa_total": 0,
        "idda_total": round(idda, 2),
        "card_total": 0,
        "transaction_count": len(today_txns),
        "top_items": [],
        "low_stock_alerts": low_stock,
        "total_credit_outstanding": round(total_credit, 2),
    }


# ─── Settings ───────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    ws = get_sheet("Settings")
    for row in ws.get_all_records():
        if row.get("key") == key:
            return str(row.get("value", default))
    return default


def set_setting(key: str, value: str):
    ws = get_sheet("Settings")
    records = ws.get_all_records()
    headers = ws.row_values(1)

    for idx, record in enumerate(records, start=2):
        if record.get("key") == key:
            col = headers.index("value") + 1
            ws.update_cell(idx, col, value)
            return

    # not found → append
    ws.append_row([key, value], value_input_option="USER_ENTERED")
