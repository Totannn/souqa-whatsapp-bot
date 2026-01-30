from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
import requests

app = FastAPI()

SOUQA_BASE_URL = "https://souqa.avidroneconsulting.com/api/v1"

HEADERS_BASE = {
    "Accept": "application/json",
    "X-Device": "whatsapp",
    "X-Platform": "bot"
}

SESSIONS = {}

@app.post("/whatsapp")
async def whatsapp_webhook(
    Body: str = Form(...),
    From: str = Form(...)
):
    raw_text = Body.strip()
    text = raw_text.lower()
    from_number = From.replace("whatsapp:", "")
    phone = from_number

    session = SESSIONS.get(from_number)

    # ================= VERIFY =================
    if text == "verify":
        r = requests.post(
            f"{SOUQA_BASE_URL}/ai-service/verify-owner",
            json={"phone": phone},
            headers={**HEADERS_BASE, "Content-Type": "application/json"},
            timeout=10
        )

        if r.status_code != 200 or not r.json().get("data", {}).get("exists"):
            return PlainTextResponse("❌ No account linked to this phone number.")

        SESSIONS[from_number] = {
            "owner_verified": True,
            "phone": phone,
            "state": None
        }

        return PlainTextResponse(
            "✅ Account verified!\n\n"
            "Commands:\n"
            "• add product\n"
            "• list products\n"
            "• update product\n"
            "• delete product <slug>"
        )

    # ================= AUTH GUARD =================
    if text.startswith(("add", "list", "update", "delete")):
        if not session or not session.get("owner_verified"):
            return PlainTextResponse("🔒 Please verify first.\nSend: verify")

    # ================= ADD PRODUCT =================
    if text == "add product":
        session["state"] = "awaiting_product_details"

        return PlainTextResponse(
            "🛒 Send product details in this format:\n\n"
            "name | cost | currency | location | size | image_url\n\n"
            "Example:\n"
            "Iphone 17 | 400 | USD | Lagos | XL | https://image.com/pic.jpg"
        )

    if session and session.get("state") == "awaiting_product_details":
        try:
            name, cost, currency, location, size, image_url = [
                x.strip() for x in raw_text.split("|")
            ]
        except ValueError:
            return PlainTextResponse("❌ Invalid format.")

        form_data = {
            "category_id": "b9123c31-41ba-46a2-ae5b-1d446d050c85",
            "name": name,
            "description": f"{name} description",
            "cost": cost,
            "currency": currency,
            "location": location,
            "size": size,
            "is_returnable": "1",
            "phone": session["phone"]
        }

        files = {"image_urls[]": (None, image_url)}

        r = requests.post(
            f"{SOUQA_BASE_URL}/ai-service/products",
            headers=HEADERS_BASE,
            data=form_data,
            files=files,
            timeout=15
        )

        if r.status_code not in (200, 201):
            return PlainTextResponse("❌ Failed to add product.")

        session["state"] = None
        return PlainTextResponse("✅ Product added successfully!")

    # ================= LIST PRODUCTS =================
    if text in ("list product", "list products"):
        r = requests.get(
            f"{SOUQA_BASE_URL}/ai-service/products",
            headers={**HEADERS_BASE, "Content-Type": "application/json"},
            json={"phone": session["phone"]},
            timeout=10
        )

        products = r.json().get("data", {}).get("data", [])

        if not products:
            return PlainTextResponse("📦 You have no products.")

        reply = "📦 Your products:\n\n"
        for i, p in enumerate(products, 1):
            reply += f"{i}. {p['name']}\n   Slug: {p['slug']}\n\n"

        return PlainTextResponse(reply)

    # ================= UPDATE PRODUCT =================
    if text == "update product":
        r = requests.get(
            f"{SOUQA_BASE_URL}/ai-service/products",
            headers={**HEADERS_BASE, "Content-Type": "application/json"},
            json={"phone": session["phone"]},
            timeout=10
        )

        products = r.json().get("data", {}).get("data", [])
        if not products:
            return PlainTextResponse("📦 You have no products to update.")

        session["products"] = products
        session["state"] = "awaiting_product_choice"

        reply = "✏️ Select a product to update:\n\n"
        for i, p in enumerate(products, 1):
            reply += f"{i}. {p['name']}\n"

        return PlainTextResponse(reply)

    if session and session.get("state") == "awaiting_product_choice":
        try:
            idx = int(text) - 1
            product = session["products"][idx]
        except:
            return PlainTextResponse("❌ Invalid selection.")

        session["selected_product"] = product
        session["state"] = "awaiting_update_payload"

        return PlainTextResponse(
            f"✏️ Updating {product['name']}\n\n"
            "Send:\n"
            "name | cost | currency | location | size | image_url\n\n"
            "Use '-' to keep existing value."
        )

    if session and session.get("state") == "awaiting_update_payload":
        product = session["selected_product"]

        try:
            name, cost, currency, location, size, image_url = [
                x.strip() for x in raw_text.split("|")
            ]
        except ValueError:
            return PlainTextResponse("❌ Invalid format.")

        form_data = {
            "_method": "put",
            "category_id": product["category_id"],
            "name": product["name"] if name == "-" else name,
            "cost": product["cost"] if cost == "-" else cost,
            "currency": product["currency"] if currency == "-" else currency,
            "location": product["location"] if location == "-" else location,
            "size": product["size"] if size == "-" else size,
            "description": product["description"],
            "is_returnable": "1",
            "phone": session["phone"]
        }

        files = {}
        if image_url != "-":
            files["image_urls[]"] = (None, image_url)

        r = requests.post(
            f"{SOUQA_BASE_URL}/ai-service/products/{product['slug']}",
            headers=HEADERS_BASE,
            data=form_data,
            files=files,
            timeout=15
        )

        if r.status_code != 200:
            return PlainTextResponse("❌ Failed to update product.")

        session["state"] = None
        session.pop("selected_product", None)
        session.pop("products", None)

        return PlainTextResponse("✅ Product updated successfully!")

    # ================= DELETE PRODUCT =================
    if text.startswith("delete product"):
        slug = text.replace("delete product", "").strip()

        if not slug:
            return PlainTextResponse("❌ Usage:\ndelete product <slug>")

        r = requests.delete(
            f"{SOUQA_BASE_URL}/ai-service/products/{slug}",
            headers={**HEADERS_BASE, "Content-Type": "application/json"},
            json={"phone": session["phone"]},
            timeout=10
        )

        if r.status_code != 200:
            return PlainTextResponse("❌ Failed to delete product.")

        return PlainTextResponse("🗑️ Product deleted successfully!")

    # ================= HELP =================
    return PlainTextResponse(
        "👋 Souqa WhatsApp Bot\n\n"
        "Commands:\n"
        "• verify\n"
        "• add product\n"
        "• list products\n"
        "• update product\n"
        "• delete product <slug>"
    )
