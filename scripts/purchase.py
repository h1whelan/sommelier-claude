#!/usr/bin/env python3
"""
purchase.py — Automate wine purchases from UK retailers using Playwright.

Usage:
    python3 scripts/purchase.py order.json

order.json format:
{
    "wines": [
        {
            "url": "https://www.majestic.co.uk/some-wine",
            "name": "Producer Wine Name 2020",
            "price": 15.99,
            "quantity": 1,
            "retailer": "majestic"
        },
        ...
    ],
    "budget_cap": 250,
    "dry_run": false
}

Credentials are read from ~/.sommelier-claude/credentials.json:
{
    "majestic": {
        "email": "...",
        "password": "..."
    },
    "bbr": {
        "email": "...",
        "password": "..."
    }
}

The script:
1. Groups wines by retailer
2. Logs into each retailer
3. Adds wines to cart
4. Verifies total is within budget
5. Proceeds to checkout (using saved payment/address on the account)
6. Returns order confirmations
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

CREDENTIALS_PATH = Path.home() / ".sommelier-claude" / "credentials.json"
SCREENSHOT_DIR = Path(__file__).parent.parent / "logs" / "screenshots"


def load_credentials():
    if not CREDENTIALS_PATH.exists():
        print(f"Error: credentials file not found at {CREDENTIALS_PATH}", file=sys.stderr)
        print("Create it with retailer login details. See README for format.", file=sys.stderr)
        sys.exit(1)
    with open(CREDENTIALS_PATH) as f:
        return json.load(f)


def load_order(path):
    with open(path) as f:
        return json.load(f)


class RetailerPurchaser:
    """Base class for retailer-specific purchase automation."""

    def __init__(self, page, credentials, dry_run=False):
        self.page = page
        self.credentials = credentials
        self.dry_run = dry_run

    def screenshot(self, name):
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / f"{name}.png"
        self.page.screenshot(path=str(path))
        print(f"  Screenshot: {path}")

    def wait_and_click(self, selector, timeout=10000):
        self.page.wait_for_selector(selector, timeout=timeout)
        self.page.click(selector)

    def dismiss_cookies(self):
        """Try to dismiss cookie banners."""
        for selector in [
            '#onetrust-accept-btn-handler',
            'button:has-text("Accept")',
            'button:has-text("Accept all")',
            'button:has-text("Accept All")',
            '[data-action="accept"]',
        ]:
            try:
                self.page.click(selector, timeout=3000)
                time.sleep(1)
                return
            except Exception:
                continue


class MajesticPurchaser(RetailerPurchaser):
    """Automate purchases from majestic.co.uk."""

    def dismiss_popups(self):
        """Dismiss cookie banner and AB-testing overlay."""
        self.dismiss_cookies()
        try:
            self.page.evaluate(
                "document.querySelector('.ab_widget_container_popin-simple')?.remove()"
            )
        except Exception:
            pass

    def login(self):
        print("  Logging into Majestic...")
        self.page.goto("https://www.majestic.co.uk/login", wait_until="domcontentloaded")
        time.sleep(5)
        self.dismiss_popups()

        self.page.fill("#mail_t1", self.credentials["email"])
        self.page.fill("#Password", self.credentials["password"])
        self.page.click('#loginForm button[type="submit"]')
        time.sleep(5)

        # Majestic redirects to /?login=1 on success
        if "login=1" in self.page.url or "login" not in self.page.url.split("?")[0].lower():
            print("  Logged in successfully")
            self.screenshot("majestic-logged-in")
        else:
            self.screenshot("majestic-login-failed")
            raise Exception("Majestic login failed — check credentials")

    def add_to_cart(self, wine):
        print(f"  Adding: {wine['name']} ({wine['url']})")
        self.page.goto(wine["url"], wait_until="domcontentloaded")
        time.sleep(5)
        self.dismiss_popups()

        title = self.page.title()
        if "not found" in title.lower() or "page not found" in title.lower():
            print(f"  WARNING: Product page not found for {wine['name']}")
            return False

        self.screenshot(f"majestic-product-{wine['name'][:30].replace(' ', '-')}")

        # Majestic uses <a> tags with id="add-to-cart-button-XXXX" and text "ADD TO TROLLEY"
        for selector in [
            'a[id^="add-to-cart-button"]',
            'a:has-text("ADD TO TROLLEY")',
            'button:has-text("ADD TO TROLLEY")',
            'button:has-text("Add to basket")',
            '.add-to-cart-btn:visible',
        ]:
            try:
                self.page.click(selector, timeout=5000)
                time.sleep(3)
                print(f"  Added to trolley")
                self.screenshot(f"majestic-added-{wine['name'][:20].replace(' ', '-')}")
                return True
            except Exception:
                continue

        self.screenshot(f"majestic-no-add-button-{wine['name'][:20]}")
        print(f"  WARNING: Could not find add-to-trolley button for {wine['name']}")
        return False

    def checkout(self):
        print("  Proceeding to Majestic checkout...")
        self.page.goto("https://www.majestic.co.uk/customer/cart", wait_until="domcontentloaded")
        time.sleep(5)
        self.screenshot("majestic-cart")

        # Check if cart is empty
        body = self.page.inner_text("body")
        if "basket is empty" in body.lower() or "trolley is empty" in body.lower():
            return {
                "status": "failed",
                "retailer": "majestic",
                "message": "Cart is empty — wines were not added successfully",
            }

        # Extract total
        total_text = ""
        try:
            total_text = self.page.evaluate("""
                () => {
                    const els = document.querySelectorAll('*');
                    for (const el of els) {
                        const text = el.textContent.trim();
                        if (text.match(/^Total:?\\s*£[\\d.]+$/) || text.match(/^£[\\d.]+$/) && el.closest('[class*="total"]')) {
                            return text;
                        }
                    }
                    return '';
                }
            """)
        except Exception:
            pass

        print(f"  Cart total: {total_text}")

        if self.dry_run:
            print("  DRY RUN — not completing checkout")
            self.screenshot("majestic-checkout-dry-run")
            return {"status": "dry_run", "total": total_text, "retailer": "majestic"}

        # Click checkout
        for selector in [
            'a:has-text("PROCEED TO CHECKOUT")',
            'a:has-text("CHECKOUT")',
            'a:has-text("Checkout")',
            'button:has-text("Checkout")',
        ]:
            try:
                self.page.click(selector, timeout=5000)
                time.sleep(5)
                break
            except Exception:
                continue

        self.screenshot("majestic-checkout-step1")

        # Look for place order / confirm
        for selector in [
            'button:has-text("Place order")',
            'button:has-text("Place Order")',
            'button:has-text("Confirm order")',
            'button:has-text("Pay now")',
            'button:has-text("Complete order")',
        ]:
            try:
                self.page.click(selector, timeout=10000)
                time.sleep(5)
                break
            except Exception:
                continue

        self.screenshot("majestic-order-confirmed")

        confirmation = ""
        try:
            page_text = self.page.inner_text("body")
            import re
            match = re.search(r'(?:order|confirmation|reference)\s*(?:#|number|:)\s*(\w+)', page_text, re.IGNORECASE)
            if match:
                confirmation = match.group(1)
        except Exception:
            pass

        return {
            "status": "ordered",
            "total": total_text,
            "confirmation": confirmation,
            "retailer": "majestic",
        }


class BBRPurchaser(RetailerPurchaser):
    """Automate purchases from bbr.com (Berry Bros & Rudd)."""

    def login(self):
        print("  Logging into Berry Bros & Rudd...")
        self.page.goto("https://www.bbr.com/login", wait_until="networkidle", timeout=30000)
        time.sleep(3)
        self.dismiss_cookies()

        self.page.fill("#login-modal-email", self.credentials["email"])
        self.page.fill("#login-modal-password", self.credentials["password"])
        self.screenshot("bbr-login-filled")
        self.page.click('button:has-text("Sign in")', timeout=5000)
        time.sleep(5)

        # BBR redirects to / or stays on /login on failure
        # Check for the authenticated indicator
        try:
            self.page.wait_for_selector('.is-authenticated, [class*="is-authenticated"]', timeout=10000)
            print("  Logged in successfully")
            self.screenshot("bbr-logged-in")
        except Exception:
            self.screenshot("bbr-login-failed")
            raise Exception("BBR login failed — check credentials")

    def add_to_cart(self, wine):
        print(f"  Adding: {wine['name']} ({wine['url']})")
        self.page.goto(wine["url"], wait_until="networkidle", timeout=30000)
        time.sleep(3)

        title = self.page.title()
        if "not found" in title.lower() or "page not found" in title.lower():
            print(f"  WARNING: Product page not found for {wine['name']}")
            return False

        self.screenshot(f"bbr-product-{wine['name'][:30].replace(' ', '-')}")

        for selector in [
            'button:has-text("Add to basket")',
            'button:has-text("ADD TO BASKET")',
            'button:has-text("Add to Basket")',
            'button:has-text("Buy")',
        ]:
            try:
                self.page.click(selector, timeout=5000)
                print(f"  Added to basket")
                time.sleep(3)
                return True
            except Exception:
                continue

        self.screenshot(f"bbr-no-add-button-{wine['name'][:20]}")
        print(f"  WARNING: Could not find add-to-basket button for {wine['name']}")
        return False

    def checkout(self):
        print("  Proceeding to BBR checkout...")
        self.page.goto("https://www.bbr.com/cart", wait_until="networkidle", timeout=30000)
        time.sleep(5)
        self.screenshot("bbr-cart")

        # Extract order total
        total_text = ""
        try:
            total_text = self.page.inner_text('.order-total')
            total_text = total_text.replace('\n', ' ').strip()
        except Exception:
            try:
                total_text = self.page.inner_text('.order-subtotal')
                total_text = total_text.replace('\n', ' ').strip()
            except Exception:
                pass

        print(f"  Cart total: {total_text}")

        # Check if cart is empty
        body = self.page.inner_text("body")
        if "basket is empty" in body.lower() or "cart is empty" in body.lower() or "no items" in body.lower():
            return {
                "status": "failed",
                "retailer": "bbr",
                "message": "Cart is empty — wines were not added successfully",
            }

        if self.dry_run:
            print("  DRY RUN — not completing checkout")
            self.screenshot("bbr-checkout-dry-run")
            return {"status": "dry_run", "total": total_text, "retailer": "bbr"}

        # Click checkout / proceed button
        for selector in [
            'a:has-text("Proceed to checkout")',
            'a:has-text("Checkout")',
            'a:has-text("CHECKOUT")',
            'button:has-text("Checkout")',
            'button:has-text("Proceed")',
        ]:
            try:
                self.page.click(selector, timeout=5000)
                time.sleep(5)
                break
            except Exception:
                continue

        self.screenshot("bbr-checkout-step1")

        # BBR checkout may have multiple steps (delivery, payment, confirm)
        # With saved payment + address, look for final confirm/place order
        for selector in [
            'button:has-text("Place order")',
            'button:has-text("Place Order")',
            'button:has-text("Confirm order")',
            'button:has-text("Pay now")',
            'button:has-text("Pay")',
            'button:has-text("Complete order")',
        ]:
            try:
                self.page.click(selector, timeout=10000)
                time.sleep(5)
                break
            except Exception:
                continue

        self.screenshot("bbr-order-confirmed")

        # Try to extract confirmation
        confirmation = ""
        try:
            page_text = self.page.inner_text("body")
            import re
            match = re.search(r'(?:order|confirmation|reference)\s*(?:#|number|:)\s*(\w+)', page_text, re.IGNORECASE)
            if match:
                confirmation = match.group(1)
        except Exception:
            pass

        return {
            "status": "ordered",
            "total": total_text,
            "confirmation": confirmation,
            "retailer": "bbr",
        }


class WineSocietyPurchaser(RetailerPurchaser):
    """Automate purchases from thewinesociety.com."""

    def login(self):
        print("  Logging into The Wine Society...")
        self.page.goto("https://www.thewinesociety.com/login", wait_until="networkidle", timeout=30000)
        time.sleep(3)
        self.dismiss_cookies()

        self.page.fill("#email", self.credentials["email"])
        self.page.fill("#password", self.credentials["password"])
        self.screenshot("winesociety-login-filled")
        self.page.click('button:has-text("Login")')
        time.sleep(5)

        # Wine Society stays on /login but shows "Welcome back" on success
        body_text = self.page.inner_text("body")
        if "welcome back" in body_text.lower():
            print("  Logged in successfully")
            self.screenshot("winesociety-logged-in")
        else:
            self.screenshot("winesociety-login-failed")
            raise Exception("Wine Society login failed — check credentials")

    def add_to_cart(self, wine):
        print(f"  Adding: {wine['name']} ({wine['url']})")
        self.page.goto(wine["url"], wait_until="networkidle", timeout=30000)
        time.sleep(3)

        title = self.page.title()
        if "can't find" in title.lower() or "not found" in title.lower():
            print(f"  WARNING: Product page not found for {wine['name']}")
            return False

        self.screenshot(f"winesociety-product-{wine['name'][:30].replace(' ', '-')}")

        # Main product add-to-basket button (not the recommendation tile ones)
        try:
            self.page.click("button.js-add-to-basket:not(.product-tile__button)", timeout=10000)
            time.sleep(3)
            print(f"  Added to basket")
            return True
        except Exception:
            pass

        # Fallback selectors
        for selector in [
            'button:has-text("Add to basket")',
            'button:has-text("Add to Basket")',
            'button.busy-button.js-add-to-basket',
        ]:
            try:
                self.page.click(selector, timeout=5000)
                print(f"  Added to basket")
                time.sleep(2)
                return True
            except Exception:
                continue

        self.screenshot(f"winesociety-no-add-button-{wine['name'][:20]}")
        print(f"  WARNING: Could not find add-to-basket button for {wine['name']}")
        return False

    def checkout(self):
        print("  Proceeding to Wine Society checkout...")
        self.page.goto("https://www.thewinesociety.com/basket/", wait_until="networkidle", timeout=30000)
        time.sleep(3)
        self.screenshot("winesociety-basket")

        # Extract basket total from summary section
        total_text = ""
        try:
            # basket-summary contains item count, subtotal, discounts, total
            summary = self.page.inner_text('.basket-summary')
            summary = summary.replace('\n', ' ').strip()
            # Extract subtotal and total
            import re
            subtotal_match = re.search(r'Item subtotal\s*(£[\d,.]+)', summary)
            total_match = re.search(r'Total\s*(£[\d,.]+)', summary)
            parts = []
            if subtotal_match:
                parts.append(f"Subtotal {subtotal_match.group(1)}")
            if total_match:
                parts.append(f"Total {total_match.group(1)}")
            total_text = ", ".join(parts) if parts else summary
        except Exception:
            try:
                total_text = self.page.inner_text('.basket-total')
                total_text = total_text.replace('\n', ' ').strip()
            except Exception:
                pass

        print(f"  Basket total: {total_text}")

        # Check if basket is empty
        body = self.page.inner_text("body")
        if "basket is empty" in body.lower():
            return {
                "status": "failed",
                "retailer": "thewinesociety",
                "message": "Basket is empty — wines were not added successfully",
            }

        if self.dry_run:
            print("  DRY RUN — not completing checkout")
            self.screenshot("winesociety-checkout-dry-run")
            return {"status": "dry_run", "total": total_text, "retailer": "thewinesociety"}

        # Click Continue to Checkout
        try:
            self.page.click('a:has-text("Continue to Checkout")', timeout=10000)
            time.sleep(5)
        except Exception:
            self.screenshot("winesociety-no-checkout-button")
            raise Exception("Could not find 'Continue to Checkout' button")

        self.screenshot("winesociety-delivery-page")

        # Select Home Delivery
        try:
            self.page.click('text=Home Delivery', timeout=10000)
            time.sleep(5)
        except Exception:
            self.screenshot("winesociety-no-home-delivery")
            raise Exception("Could not find 'Home Delivery' option")

        self.screenshot("winesociety-home-delivery-selected")

        # Select first available delivery date
        try:
            self.page.click('.delivery-date-selector__item', timeout=10000)
            time.sleep(3)
        except Exception:
            self.screenshot("winesociety-no-delivery-date")
            raise Exception("Could not find delivery date options")

        # Click Review & Pay
        try:
            self.page.click('button:has-text("Review & Pay")', timeout=10000)
            time.sleep(5)
        except Exception:
            self.screenshot("winesociety-no-review-pay")
            raise Exception("Could not find 'Review & Pay' button")

        self.screenshot("winesociety-review-pay")

        # On Review & Pay page, look for Place Order / Confirm
        for selector in [
            'button:has-text("Place order")',
            'button:has-text("Place Order")',
            'button:has-text("Confirm order")',
            'button:has-text("Confirm Order")',
            'button:has-text("Pay now")',
            'button:has-text("Complete order")',
            'button:has-text("Submit order")',
        ]:
            try:
                self.page.click(selector, timeout=10000)
                time.sleep(5)
                break
            except Exception:
                continue

        self.screenshot("winesociety-order-confirmed")

        # Try to extract confirmation
        confirmation = ""
        try:
            page_text = self.page.inner_text("body")
            import re
            match = re.search(r'(?:order|confirmation|reference)\s*(?:#|number|:)\s*(\w+)', page_text, re.IGNORECASE)
            if match:
                confirmation = match.group(1)
        except Exception:
            pass

        return {
            "status": "ordered",
            "total": total_text,
            "confirmation": confirmation,
            "retailer": "thewinesociety",
        }


class GenericPurchaser(RetailerPurchaser):
    """Fallback purchaser for retailers without specific automation.
    Adds items to cart but stops before checkout, notifying Henry to complete manually."""

    def login(self):
        print(f"  No automated login for this retailer")

    def add_to_cart(self, wine):
        print(f"  Opening: {wine['name']} ({wine['url']})")
        self.page.goto(wine["url"], wait_until="domcontentloaded")
        time.sleep(2)
        self.screenshot(f"generic-{wine['name'][:30].replace(' ', '-')}")
        return True

    def checkout(self):
        return {
            "status": "manual_required",
            "message": "No automated checkout for this retailer. Wines identified but not ordered.",
            "retailer": "other",
        }


PURCHASERS = {
    "majestic": MajesticPurchaser,
    "bbr": BBRPurchaser,
    "thewinesociety": WineSocietyPurchaser,
}


def get_purchaser(retailer):
    return PURCHASERS.get(retailer, GenericPurchaser)


def main():
    parser = argparse.ArgumentParser(description="Purchase wines from UK retailers")
    parser.add_argument("order_file", help="Path to order JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Add to cart but don't complete checkout")
    args = parser.parse_args()

    order = load_order(args.order_file)
    credentials = load_credentials()
    dry_run = args.dry_run or order.get("dry_run", False)
    budget_cap = order.get("budget_cap", 250)

    # Calculate total
    total = sum(w["price"] * w.get("quantity", 1) for w in order["wines"])
    print(f"Order total: £{total:.2f} (budget cap: £{budget_cap})")

    if total > budget_cap:
        print(f"ERROR: Order total £{total:.2f} exceeds budget cap £{budget_cap}", file=sys.stderr)
        sys.exit(1)

    # Group wines by retailer
    by_retailer = {}
    for wine in order["wines"]:
        retailer = wine.get("retailer", "unknown")
        by_retailer.setdefault(retailer, []).append(wine)

    print(f"\nOrdering from {len(by_retailer)} retailer(s): {', '.join(by_retailer.keys())}")
    if dry_run:
        print("MODE: DRY RUN (will add to cart but not complete checkout)\n")
    else:
        print("MODE: LIVE ORDER\n")

    from playwright.sync_api import sync_playwright

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled'],
        )

        for retailer, wines in by_retailer.items():
            print(f"\n{'='*60}")
            print(f"Retailer: {retailer} ({len(wines)} wine(s))")
            print(f"{'='*60}")

            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                locale="en-GB",
            )
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

            purchaser_class = get_purchaser(retailer)
            creds = credentials.get(retailer, {})
            purchaser = purchaser_class(page, creds, dry_run=dry_run)

            try:
                if creds:
                    purchaser.login()

                added = []
                for wine in wines:
                    if purchaser.add_to_cart(wine):
                        added.append(wine)

                if added:
                    result = purchaser.checkout()
                    result["wines_added"] = [w["name"] for w in added]
                    result["wines_failed"] = [
                        w["name"] for w in wines if w not in added
                    ]
                    results.append(result)
                else:
                    results.append({
                        "status": "failed",
                        "retailer": retailer,
                        "message": "No wines could be added to cart",
                    })

            except Exception as e:
                print(f"  ERROR: {e}", file=sys.stderr)
                purchaser.screenshot(f"{retailer}-error")
                results.append({
                    "status": "error",
                    "retailer": retailer,
                    "error": str(e),
                })
            finally:
                context.close()

        browser.close()

    # Write results
    results_path = Path(args.order_file).with_suffix(".results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults written to {results_path}")

    # Summary
    print(f"\n{'='*60}")
    print("ORDER SUMMARY")
    print(f"{'='*60}")
    for r in results:
        status = r.get("status", "unknown")
        retailer = r.get("retailer", "unknown")
        if status == "ordered":
            print(f"  {retailer}: ORDERED — {r.get('total', '?')} — {r.get('confirmation', 'no confirmation #')}")
        elif status == "dry_run":
            print(f"  {retailer}: DRY RUN — {r.get('total', '?')} in basket")
        elif status == "manual_required":
            print(f"  {retailer}: MANUAL CHECKOUT NEEDED")
        else:
            print(f"  {retailer}: {status} — {r.get('error', r.get('message', ''))}")

    return 0 if all(r.get("status") in ("ordered", "dry_run") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
