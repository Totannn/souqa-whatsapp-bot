from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse
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

    resp = MessagingResponse()
    msg = resp.message()

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
            msg.body("❌ No account linked to this phone number.")
            return PlainTextResponse(str(resp))

        SESSIONS[from_number] = {
            "owner_verified": True,
            "phone": phone,
            "state": None
        }

        msg.body(
            "✅ Account verified!\n\n"
            "Commands:\n"
            "• add product\n"
            "• list products\n"
            "• update product\n"
            "• delete product <slug>"
        )
        return PlainTextResponse(str(resp))

    # ================= AUTH GUARD =================

    if text.startswith(("add", "list", "update", "delete")):
        if not session or not session.get("owner_verified"):
            msg.body("🔒 Please verify first.\nSend: verify")
            return PlainTextResponse(str(resp))
# ===================== ADD PRODUCT =====================

    if text == "add product":
        if not session:
            msg.body("🔒 Please verify first.\nSend: verify")
            return PlainTextResponse(str(resp))

        session["state"] = "awaiting_product_details"


        msg.body(
            "🛒 Send product details in this format:\n\n"
            "name | cost | currency | location | size | image_url\n\n"
            "Example:\n"
            "Iphone 17 | 400 | USD | Lagos | XL | https://image.com/pic.jpg"
        )
        return PlainTextResponse(str(resp))

    if session and session.get("state") == "awaiting_product_details":
        try:
            name, cost, currency, location, size, image_url = [
                x.strip() for x in raw_text.split("|")
            ]
        except ValueError:
            msg.body("❌ Invalid format.")
            return PlainTextResponse(str(resp))

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

        files = {
            "image_urls[]": (None, image_url)
        }

        r = requests.post(
            f"{SOUQA_BASE_URL}/ai-service/products",
            headers=HEADERS_BASE,
            data=form_data,
            files=files,
            timeout=15
        )

        if r.status_code not in (200, 201):
            msg.body("❌ Failed to add product.")
            return PlainTextResponse(str(resp))

        session["state"] = None
        msg.body("✅ Product added successfully!")
        return PlainTextResponse(str(resp))

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
            msg.body("📦 You have no products.")
            return PlainTextResponse(str(resp))

        reply = "📦 Your products:\n\n"
        for p in products:
            reply += f"• {p['name']}\n  Slug: {p['slug']}\n\n"

        msg.body(reply)
        return PlainTextResponse(str(resp))

    # ================= UPDATE PRODUCT (STEP 1) =================

    if text == "update product":
        r = requests.get(
            f"{SOUQA_BASE_URL}/ai-service/products",
            headers={**HEADERS_BASE, "Content-Type": "application/json"},
            json={"phone": session["phone"]},
            timeout=10
        )

        products = r.json().get("data", {}).get("data", [])

        if not products:
            msg.body("📦 You have no products to update.")
            return PlainTextResponse(str(resp))

        session["products"] = products
        session["state"] = "awaiting_product_choice"

        reply = "✏️ Select a product to update:\n\n"
        for i, p in enumerate(products, 1):
            reply += f"{i}. {p['name']}\n"

        msg.body(reply)
        return PlainTextResponse(str(resp))

    # ================= UPDATE PRODUCT (STEP 2) =================

    if session and session.get("state") == "awaiting_product_choice":
        try:
            idx = int(text) - 1
            product = session["products"][idx]
        except:
            msg.body("❌ Invalid selection.")
            return PlainTextResponse(str(resp))

        session["selected_product"] = product
        session["state"] = "awaiting_update_payload"

        msg.body(
            f"✏️ Updating *{product['name']}*\n\n"
            "Send:\n"
            "name | cost | currency | location | size | image_url\n\n"
            "Use `-` to keep existing value."
        )
        return PlainTextResponse(str(resp))

    # ================= UPDATE PRODUCT (STEP 3) =================

    if session and session.get("state") == "awaiting_update_payload":
        product = session["selected_product"]

        try:
            name, cost, currency, location, size, image_url = [
                x.strip() for x in raw_text.split("|")
            ]
        except ValueError:
            msg.body("❌ Invalid format.")
            return PlainTextResponse(str(resp))

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
            msg.body("❌ Failed to update product.")
            return PlainTextResponse(str(resp))

        session["state"] = None
        session.pop("selected_product", None)
        session.pop("products", None)

        msg.body("✅ Product updated successfully!")
        return PlainTextResponse(str(resp))

    # ================= DELETE PRODUCT =================

    if text.startswith("delete product"):
        slug = text.replace("delete product", "").strip()

        if not slug:
            msg.body("❌ Usage:\ndelete product <slug>")
            return PlainTextResponse(str(resp))

        r = requests.delete(
            f"{SOUQA_BASE_URL}/ai-service/products/{slug}",
            headers={**HEADERS_BASE, "Content-Type": "application/json"},
            json={"phone": session["phone"]},
            timeout=10
        )

        if r.status_code != 200:
            msg.body("❌ Failed to delete product.")
            return PlainTextResponse(str(resp))

        msg.body("🗑️ Product deleted successfully.")
        return PlainTextResponse(str(resp))

    # ================= HELP =================

    msg.body(
        "👋 Souqa WhatsApp Bot\n\n"
        "Commands:\n"
        "• verify\n"
        "• add product\n"
        "• list products\n"
        "• update product\n"
        "• delete product <slug>"
    )

    return PlainTextResponse(str(resp))
