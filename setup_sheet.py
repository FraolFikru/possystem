import gspread
from google.oauth2.service_account import Credentials

# ========== CONFIG ==========
SHEET_ID = "1ojcGLMq-uc3x-p4Qc02pfmAumDjY-L5mmxfKjbcZ6pc/edit?gid=0#gid=0"          # ← put your Sheet ID
CREDENTIALS_FILE = "service_account.json"
# ============================

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SHEET_ID)

# Headers for each tab
HEADERS = {
    "Items": [
        "id", "sku", "barcode", "name", "category", "unit_price", "cost_price",
        "stock_qty", "low_stock_threshold", "unit", "size", "color",
        "requires_batch", "requires_expiry", "is_recipe", "is_active", "created_at"
    ],
    "Customers": [
        "id", "code", "name", "phone", "credit_limit", "is_active", "created_at"
    ],
    "Transactions": [
        "id", "reference", "status", "subtotal", "tax_amount", "discount_amount",
        "total_amount", "amount_cash", "amount_telebirr", "amount_mpesa",
        "amount_idda", "amount_card", "payment_method", "customer_id", "notes", "created_at"
    ],
    "TransactionLines": [
        "id", "transaction_id", "item_id", "quantity", "unit_price", "line_total"
    ],
    "Credits": [
        "id", "customer_id", "amount", "balance_after", "note", "created_at"
    ],
    "Settings": [
        "key", "value"
    ],
}

print("Setting up headers...\n")

for tab_name, headers in HEADERS.items():
    try:
        # Try to get the worksheet
        try:
            ws = spreadsheet.worksheet(tab_name)
            print(f"✓ Found tab: {tab_name}")
        except gspread.WorksheetNotFound:
            # Create the tab if it doesn't exist
            ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=20)
            print(f"+ Created tab: {tab_name}")

        # Clear existing content and write headers
        ws.clear()
        ws.append_row(headers, value_input_option="USER_ENTERED")
        print(f"  → Headers added to {tab_name}")

    except Exception as e:
        print(f"✗ Error on {tab_name}: {e}")

print("\n✅ Done! Your Google Sheet is ready.")
