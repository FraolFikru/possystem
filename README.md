# SME POS & Business Management System

**Offline-first • Modular • Production-ready**  
Inspired by Square & Toast — tailored for SMEs in emerging markets (Ethiopia / East Africa focus).

## Features

| Module | Capabilities |
|--------|--------------|
| **Shared Core** | Double-entry aware ledger (Cash, Telebirr, M-Pesa, Idda), Inventory + COGS, Offline queue |
| **Restaurant** | BOM / Recipe engine (fractional ingredient deduction), Table → Kitchen → Bill flow |
| **Retail / Boutique** | Barcode/SKU lookup, Size/Color variants, multi-item discounts |
| **Pharmacy / Grocery** | Batch numbers, Expiry dates, FEFO stock deduction |
| **Idda (Credit)** | Per-customer debt ledger, repayments, SMS/Telegram reminder pre-fill |
| **Analytics** | Daily revenue, payment mix, top sellers, low-stock alerts |

## Tech Stack

- **Python 3.11+** / **FastAPI** (async)
- **SQLite** + **SQLAlchemy 2.0** (async) — 100 % local, zero cloud
- **Jinja2 + Tailwind CSS (CDN) + Vanilla JS**
- Clean Architecture: Models → Services → Routers → Templates

## Quick Start

```bash
cd pos_system
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run (creates pos_data.db + seeds demo products on first launch)
python main.py
```

Open **http://localhost:8000**

API docs: **http://localhost:8000/docs**

## Project Structure

```
pos_system/
├── main.py                 # FastAPI app, lifespan, seed
├── requirements.txt
├── app/
│   ├── core/config.py      # Settings (mode, VAT, currency)
│   ├── database.py         # Async engine + session
│   ├── models/models.py    # SQLAlchemy models
│   ├── schemas/schemas.py  # Pydantic v2
│   ├── services/
│   │   ├── inventory_service.py   # Stock, BOM, FEFO
│   │   └── transaction_service.py # Checkout, Idda, analytics
│   ├── api/routers/
│   │   ├── items.py
│   │   ├── transactions.py
│   │   └── system.py
│   └── templates/index.html       # Full SPA dashboard
```

## Business Mode Switch

Use the dropdown in the top navbar (or `PUT /api/system/mode`).  
The same core engine adapts validation & UI fields:

- **Restaurant** → Recipe/BOM fields active
- **Retail** → Size/Color variants
- **Pharmacy/Grocery** → Batch + Expiry + FEFO

## Offline Behaviour

- Transactions created while offline are flagged `is_offline=true` and queued in `offline_queue`.
- When connectivity returns, a background worker (extendable) can push the queue.
- UI shows an **OFFLINE** badge automatically via `navigator.onLine`.

## Demo Data

On first start the system seeds:

- 8 sample products (coffee, apparel, pharmacy, grocery)
- 1 customer (Abebe Kebede) ready for Idda credit

## Extending

1. **Alembic** — `alembic init` is ready; point `sqlalchemy.url` at the same SQLite file.
2. **Kitchen display** — poll `/api/orders?status=sent_to_kitchen`.
3. **Telegram bot** — use the pre-filled reminder messages + `telegram_id` on customers.
4. **Multi-device sync** — replace SQLite with a local LiteFS / rqlite cluster or periodic JSON export.

## License

MIT — built for the open-source SME ecosystem in emerging markets.
