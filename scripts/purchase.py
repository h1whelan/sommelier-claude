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

    def login(self):
        print("  Logging into Majestic...")
        self.page.goto("https://www.majestic.co.uk/account/login", wait_until="domcontentloaded")
        time.sleep(2)
        self.dismiss_cookies()

        self.page.fill('input[name="email"], input[type="email"], #email', self.credentials["email"])
        self.page.fill('input[name="password"], input[type="password"], #password', self.credentials["password"])
        self.page.click('button[type="submit"], input[type="submit"]')
        time.sleep(3)

        # Verify login succeeded
        if "login" in self.page.url.lower():
            self.screenshot("majestic-login-failed")
            raise Exception("Majestic login failed — check credentials")

        print("  Logged in successfully")
        self.screenshot("majestic-logged-in")

    def add_to_cart(self, wine):
        print(f"  Adding: {wine['name']} ({wine['url']})")
        self.page.goto(wine["url"], wait_until="domcontentloaded")
        time.sleep(2)

        # Check the page loaded a real product
        title = self.page.title()
        if "404" in title or "not found" in title.lower():
            print(f"  WARNING: Product page not found for {wine['name']}")
            return False

        self.screenshot(f"majestic-product-{wine['name'][:30].replace(' ', '-')}")

        # Look for add to cart button
        for selector in [
            'button:has-text("Add to basket")',
            'button:has-text("Add to Basket")',
            'button:has-text("Add to cart")',
            '[data-action="add-to-basket"]',
            '.add-to-basket',
            'button.btn-add-to-basket',
        ]:
            try:
                self.page.click(selector, timeout=5000)
                print(f"  Added to basket")
                time.sleep(2)
                return True
            except Exception:
                continue

        self.screenshot(f"majestic-no-add-button-{wine['name'][:20]}")
        print(f"  WARNING: Could not find add-to-basket button for {wine['name']}")
        return False

    def checkout(self):
        print("  Proceeding to checkout...")
        self.page.goto("https://www.majestic.co.uk/basket", wait_until="domcontentloaded")
        time.sleep(2)
        self.screenshot("majestic-basket")

        # Extract basket total
        total_text = ""
        for selector in ['.basket-total', '.order-total', '[data-testid="basket-total"]']:
            try:
                total_text = self.page.inner_text(selector)
                break
            except Exception:
                continue

        print(f"  Basket total: {total_text}")

        if self.dry_run:
            print("  DRY RUN — not completing checkout")
            self.screenshot("majestic-checkout-dry-run")
            return {"status": "dry_run", "total": total_text, "retailer": "majestic"}

        # Click checkout
        for selector in [
            'a:has-text("Checkout")',
            'button:has-text("Checkout")',
            'a:has-text("Proceed")',
            '.checkout-button',
        ]:
            try:
                self.page.click(selector, timeout=5000)
                time.sleep(3)
                break
            except Exception:
                continue

        self.screenshot("majestic-checkout-step1")

        # At this point, if the account has saved payment + address,
        # Majestic should show a confirmation page.
        # We look for a "Place order" / "Confirm" button.
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

        # Try to extract order confirmation number
        confirmation = ""
        for selector in ['.order-confirmation', '.order-number', '[data-testid="order-number"]']:
            try:
                confirmation = self.page.inner_text(selector)
                break
            except Exception:
                continue

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
        self.page.goto("https://www.bbr.com/account/login", wait_until="domcontentloaded")
        time.sleep(2)
        self.dismiss_cookies()

        self.page.fill('input[name="email"], input[type="email"], #email', self.credentials["email"])
        self.page.fill('input[name="password"], input[type="password"], #password', self.credentials["password"])
        self.page.click('button[type="submit"], input[type="submit"]')
        time.sleep(3)

        if "login" in self.page.url.lower():
            self.screenshot("bbr-login-failed")
            raise Exception("BBR login failed — check credentials")

        print("  Logged in successfully")

    def add_to_cart(self, wine):
        print(f"  Adding: {wine['name']} ({wine['url']})")
        self.page.goto(wine["url"], wait_until="domcontentloaded")
        time.sleep(2)

        title = self.page.title()
        if "404" in title or "not found" in title.lower():
            print(f"  WARNING: Product page not found for {wine['name']}")
            return False

        for selector in [
            'button:has-text("Add to basket")',
            'button:has-text("Add to Basket")',
            'button:has-text("Add to bag")',
            '.add-to-basket',
        ]:
            try:
                self.page.click(selector, timeout=5000)
                time.sleep(2)
                return True
            except Exception:
                continue

        print(f"  WARNING: Could not find add-to-basket button for {wine['name']}")
        return False

    def checkout(self):
        print("  Proceeding to BBR checkout...")
        self.page.goto("https://www.bbr.com/basket", wait_until="domcontentloaded")
        time.sleep(2)
        self.screenshot("bbr-basket")

        total_text = ""
        for selector in ['.basket-total', '.order-total']:
            try:
                total_text = self.page.inner_text(selector)
                break
            except Exception:
                continue

        if self.dry_run:
            print("  DRY RUN — not completing checkout")
            return {"status": "dry_run", "total": total_text, "retailer": "bbr"}

        for selector in [
            'a:has-text("Checkout")',
            'button:has-text("Checkout")',
        ]:
            try:
                self.page.click(selector, timeout=5000)
                time.sleep(3)
                break
            except Exception:
                continue

        self.screenshot("bbr-checkout")

        for selector in [
            'button:has-text("Place order")',
            'button:has-text("Confirm")',
            'button:has-text("Pay now")',
        ]:
            try:
                self.page.click(selector, timeout=10000)
                time.sleep(5)
                break
            except Exception:
                continue

        self.screenshot("bbr-order-confirmed")
        return {"status": "ordered", "total": total_text, "retailer": "bbr"}


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
        browser = p.chromium.launch(headless=True)

        for retailer, wines in by_retailer.items():
            print(f"\n{'='*60}")
            print(f"Retailer: {retailer} ({len(wines)} wine(s))")
            print(f"{'='*60}")

            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            )
            page = context.new_page()

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
