#!/usr/bin/env python3
"""
import-vivino.py — Parse Vivino GDPR export into taste-profile.md

Usage:
    python3 scripts/import-vivino.py /path/to/vivino-export/

Vivino GDPR exports typically include:
    - wines.csv or similar: your rated wines with ratings, vintages, etc.
    - Various JSON/CSV files with activity data

This script extracts patterns from your ratings to build a structured taste
profile that the sommelier session can use for better recommendations.
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROFILE_PATH = Path(__file__).parent.parent / "taste-profile.md"


def find_wines_file(export_dir):
    """Find the wines/ratings data file in the export."""
    candidates = [
        "wines.csv",
        "ratings.csv",
        "wine_ratings.csv",
        "my_wines.csv",
        "data.csv",
    ]
    export_path = Path(export_dir)

    # Check direct candidates
    for name in candidates:
        path = export_path / name
        if path.exists():
            return path

    # Search recursively for CSV files
    csvs = list(export_path.rglob("*.csv"))
    if len(csvs) == 1:
        return csvs[0]

    # Look for largest CSV (likely the ratings)
    if csvs:
        return max(csvs, key=lambda p: p.stat().st_size)

    # Check for JSON
    jsons = list(export_path.rglob("*.json"))
    if jsons:
        return max(jsons, key=lambda p: p.stat().st_size)

    return None


def parse_csv_wines(filepath):
    """Parse wines from a CSV export file."""
    wines = []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        if not headers:
            print(f"Error: empty CSV at {filepath}", file=sys.stderr)
            return wines

        # Map common header variations
        header_map = {}
        for h in headers:
            hl = h.lower().strip()
            if "name" in hl or "wine" in hl:
                header_map.setdefault("name", h)
            if "rating" in hl or "score" in hl:
                header_map.setdefault("rating", h)
            if "grape" in hl or "varietal" in hl or "variety" in hl:
                header_map.setdefault("grape", h)
            if "region" in hl:
                header_map.setdefault("region", h)
            if "country" in hl:
                header_map.setdefault("country", h)
            if "vintage" in hl or "year" in hl:
                header_map.setdefault("vintage", h)
            if "price" in hl:
                header_map.setdefault("price", h)
            if "winery" in hl or "producer" in hl:
                header_map.setdefault("producer", h)
            if "type" in hl or "colour" in hl or "color" in hl:
                header_map.setdefault("type", h)

        print(f"Found headers: {headers}")
        print(f"Mapped: {header_map}")

        for row in reader:
            wine = {}
            for key, col in header_map.items():
                wine[key] = row.get(col, "").strip()
            if wine.get("name") or wine.get("producer"):
                wines.append(wine)

    return wines


def parse_json_wines(filepath):
    """Parse wines from a JSON export file."""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Try common keys
        for key in ["wines", "ratings", "data", "items"]:
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def analyze_wines(wines):
    """Analyze wine list and extract taste patterns."""
    analysis = {
        "total_rated": len(wines),
        "top_wines": [],
        "grapes": Counter(),
        "regions": Counter(),
        "countries": Counter(),
        "types": Counter(),
        "avg_rating": 0,
        "price_range": {"min": float("inf"), "max": 0, "prices": []},
        "high_rated_grapes": Counter(),
        "high_rated_regions": Counter(),
    }

    ratings = []
    for w in wines:
        # Rating
        rating = None
        for key in ["rating", "score"]:
            val = w.get(key, "")
            if val:
                try:
                    rating = float(val)
                    ratings.append(rating)
                    break
                except (ValueError, TypeError):
                    pass

        # Grape
        grape = w.get("grape", "") or w.get("varietal", "") or w.get("variety", "")
        if grape:
            for g in grape.split(","):
                g = g.strip()
                if g:
                    analysis["grapes"][g] += 1
                    if rating and rating >= 4.0:
                        analysis["high_rated_grapes"][g] += 1

        # Region
        region = w.get("region", "")
        if region:
            analysis["regions"][region] += 1
            if rating and rating >= 4.0:
                analysis["high_rated_regions"][region] += 1

        # Country
        country = w.get("country", "")
        if country:
            analysis["countries"][country] += 1

        # Type
        wine_type = w.get("type", "") or w.get("colour", "") or w.get("color", "")
        if wine_type:
            analysis["types"][wine_type] += 1

        # Price
        price = w.get("price", "")
        if price:
            try:
                p = float(price.replace("£", "").replace("$", "").replace(",", ""))
                analysis["price_range"]["prices"].append(p)
                analysis["price_range"]["min"] = min(analysis["price_range"]["min"], p)
                analysis["price_range"]["max"] = max(analysis["price_range"]["max"], p)
            except (ValueError, TypeError):
                pass

        # Top wines (rated 4+)
        if rating and rating >= 4.0:
            name = w.get("name", "") or w.get("producer", "Unknown")
            analysis["top_wines"].append(
                {"name": name, "rating": rating, "grape": grape, "region": region}
            )

    if ratings:
        analysis["avg_rating"] = sum(ratings) / len(ratings)

    # Sort top wines by rating
    analysis["top_wines"].sort(key=lambda x: x["rating"], reverse=True)

    return analysis


def generate_profile(analysis):
    """Generate taste-profile.md content from analysis."""
    lines = [
        "# Henry's Wine Taste Profile",
        "",
        f"*Last updated: {__import__('datetime').date.today()} (imported from Vivino data)*",
        "",
        "## Overview",
        "",
        f"Based on **{analysis['total_rated']} wines** rated on Vivino.",
    ]

    if analysis["avg_rating"]:
        lines.append(f"Average rating: **{analysis['avg_rating']:.1f}/5**")
    lines.append("")

    # Top wines
    if analysis["top_wines"]:
        lines.extend(["## Top Rated Wines", ""])
        for w in analysis["top_wines"][:15]:
            grape_info = f" ({w['grape']})" if w["grape"] else ""
            region_info = f" — {w['region']}" if w["region"] else ""
            lines.append(
                f"- **{w['name']}**{grape_info}{region_info} — {w['rating']}/5"
            )
        lines.append("")

    # Preferred grapes
    if analysis["grapes"]:
        lines.extend(["## Preferred Grapes", ""])
        lines.append("### Most Frequently Rated")
        for grape, count in analysis["grapes"].most_common(15):
            lines.append(f"- {grape}: {count} wines")
        lines.append("")

        if analysis["high_rated_grapes"]:
            lines.append("### Highest Rated (4+ stars)")
            for grape, count in analysis["high_rated_grapes"].most_common(10):
                lines.append(f"- {grape}: {count} wines rated 4+")
            lines.append("")

    # Regions
    if analysis["regions"]:
        lines.extend(["## Preferred Regions", ""])
        lines.append("### Most Explored")
        for region, count in analysis["regions"].most_common(15):
            lines.append(f"- {region}: {count} wines")
        lines.append("")

        if analysis["high_rated_regions"]:
            lines.append("### Highest Rated Regions")
            for region, count in analysis["high_rated_regions"].most_common(10):
                lines.append(f"- {region}: {count} wines rated 4+")
            lines.append("")

    # Countries
    if analysis["countries"]:
        lines.extend(["## Countries", ""])
        for country, count in analysis["countries"].most_common(10):
            lines.append(f"- {country}: {count} wines")
        lines.append("")

    # Wine types
    if analysis["types"]:
        lines.extend(["## Wine Types", ""])
        for t, count in analysis["types"].most_common():
            lines.append(f"- {t}: {count} wines")
        lines.append("")

    # Price range
    prices = analysis["price_range"]["prices"]
    if prices:
        lines.extend(["## Price Range", ""])
        lines.append(f"- Range: £{min(prices):.0f} – £{max(prices):.0f}")
        lines.append(f"- Average: £{sum(prices)/len(prices):.0f}")
        median = sorted(prices)[len(prices) // 2]
        lines.append(f"- Median: £{median:.0f}")
        lines.append("")

    # Retailers
    lines.extend(
        [
            "## Retailers",
            "",
            "- **Primary:** Majestic (convenience + mixed case discounts)",
            "- **Also shops at:** Berry Bros & Rudd, independent wine shops, Waitrose",
            "",
            "## Feedback History",
            "",
            "*Profile imported from Vivino. Will be enriched by monthly feedback.*",
            "",
            "---",
            "",
            "*This profile was generated by `scripts/import-vivino.py` from Vivino export data.",
            "It is updated monthly by the sommelier session based on Henry's feedback.*",
        ]
    )

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Import Vivino GDPR export into taste-profile.md"
    )
    parser.add_argument("export_dir", help="Path to extracted Vivino export directory")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print profile without saving"
    )
    args = parser.parse_args()

    if not os.path.isdir(args.export_dir):
        print(f"Error: {args.export_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    wines_file = find_wines_file(args.export_dir)
    if not wines_file:
        print(
            f"Error: no wine data file found in {args.export_dir}", file=sys.stderr
        )
        print("Expected CSV or JSON file with wine ratings.", file=sys.stderr)
        sys.exit(1)

    print(f"Found wine data: {wines_file}")

    if wines_file.suffix == ".json":
        wines = parse_json_wines(wines_file)
    else:
        wines = parse_csv_wines(wines_file)

    if not wines:
        print("Error: no wines found in data file", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(wines)} wines")

    analysis = analyze_wines(wines)
    profile = generate_profile(analysis)

    if args.dry_run:
        print("\n--- Generated Profile ---\n")
        print(profile)
    else:
        with open(PROFILE_PATH, "w") as f:
            f.write(profile)
        print(f"Profile written to {PROFILE_PATH}")


if __name__ == "__main__":
    main()
