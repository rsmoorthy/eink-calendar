#!/usr/bin/env python3
import sys
import os
import argparse
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import init_db, get_calendar_day, save_calendar_day, get_connection
from panchanga import fetch_online_panchanga
from tamil_calendar import get_tamil_date
from image_generator import generate_calendar_image, image_to_bitmap_bytes, compute_checksum


def generate_day(target_date: date, force: bool = False, refetch_panchanga: bool = False):
    date_str = target_date.strftime("%Y-%m-%d")
    existing = get_calendar_day(date_str)

    if existing and existing["bitmap"] and not force and not refetch_panchanga:
        return existing["checksum"], False

    # Metadata gathering
    day_name = target_date.strftime("%A")
    month_name = target_date.strftime("%b")
    day_num = target_date.day

    # Check if we already have panchanga in DB
    if existing and existing["lunar_masa"] and not refetch_panchanga:
        panchanga = {
            "lunar_masa": existing["lunar_masa"],
            "lunar_paksha": existing["lunar_paksha"],
            "lunar_tithi": existing["lunar_tithi"],
            "nakshatra": existing["nakshatra"],
        }
    else:
        panchanga = fetch_online_panchanga(target_date)

    tamil_info = get_tamil_date(target_date)
    icon_name = existing["icon_name"] if existing and "icon_name" in existing.keys() and existing["icon_name"] else ""
    addl_icon_name = existing["addl_icon_name"] if existing and "addl_icon_name" in existing.keys() and existing["addl_icon_name"] else ""
    custom_text = existing["custom_text"] if existing and existing["custom_text"] else ""

    day_data = {
        "date": date_str,
        "day_of_week": day_name,
        "gregorian_day": day_num,
        "gregorian_month": month_name,
        "lunar_masa": panchanga.get("lunar_masa", ""),
        "lunar_paksha": panchanga.get("lunar_paksha", "Shukla"),
        "lunar_tithi": panchanga.get("lunar_tithi", "Prathama"),
        "nakshatra": panchanga.get("nakshatra", ""),
        "tamil_month": tamil_info.get("tamil_month", ""),
        "tamil_month_ta": tamil_info.get("tamil_month_ta", ""),
        "tamil_date": tamil_info.get("tamil_date", 0),
        "custom_text": custom_text,
        "icon_name": icon_name,
        "addl_icon_name": addl_icon_name,
    }

    # Generate Image & Bitmap
    pil_img = generate_calendar_image(day_data)
    bitmap_bytes = image_to_bitmap_bytes(pil_img)
    checksum = compute_checksum(bitmap_bytes)

    day_data["bitmap"] = bitmap_bytes
    day_data["checksum"] = checksum

    save_calendar_day(day_data)
    return checksum, True


def run_bulk_generate(start_date: date = None, days: int = 90, force: bool = False, refetch_panchanga: bool = False, all_existing: bool = False):
    init_db()
    if all_existing:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT date FROM calendar_days ORDER BY date ASC;")
        dates = [date.fromisoformat(r["date"]) for r in cursor.fetchall()]
        conn.close()
        if not dates:
            print("No existing days found in DB.")
            return
        total = len(dates)
        print(f"Starting bulk generation for all {total} existing dates in DB ({dates[0]} to {dates[-1]})...")
        generated_count = 0
        skipped_count = 0
        for i, d in enumerate(dates):
            checksum, generated = generate_day(d, force=force, refetch_panchanga=refetch_panchanga)
            if generated:
                generated_count += 1
                print(f"[{i+1}/{total}] Updated {d.strftime('%Y-%m-%d')} (checksum: {checksum[:8]}...)")
            else:
                skipped_count += 1
                print(f"[{i+1}/{total}] Skipped {d.strftime('%Y-%m-%d')} (already exists)")
        print(f"Done! {generated_count} updated, {skipped_count} skipped.")
        return

    if start_date is None:
        start_date = date.today()

    print(f"Starting bulk generation for {days} days from {start_date.strftime('%Y-%m-%d')}...")
    generated_count = 0
    skipped_count = 0

    for i in range(days):
        d = start_date + timedelta(days=i)
        checksum, generated = generate_day(d, force=force, refetch_panchanga=refetch_panchanga)
        if generated:
            generated_count += 1
            print(f"[{i+1}/{days}] Generated {d.strftime('%Y-%m-%d')} (checksum: {checksum[:8]}...)")
        else:
            skipped_count += 1
            print(f"[{i+1}/{days}] Skipped {d.strftime('%Y-%m-%d')} (already exists)")

    print(f"Done! {generated_count} generated, {skipped_count} skipped.")


def main():
    parser = argparse.ArgumentParser(description="Bulk Calendar Image Generator")
    parser.add_argument("--start-date", "-s", default=None, help="Start date in YYYY-MM-DD format (default: today)")
    parser.add_argument("--days", "-d", type=int, default=90, help="Number of days to generate (default: 90)")
    parser.add_argument("--force", "-f", action="store_true", help="Force regeneration of existing images")
    parser.add_argument("--refetch-panchanga", "-r", action="store_true", help="Re-fetch panchanga from online source to update DB and images")
    parser.add_argument("--all", "-a", action="store_true", help="Process all existing days recorded in the database")

    args = parser.parse_args()
    start_d = date.fromisoformat(args.start_date) if args.start_date else None

    run_bulk_generate(start_d, args.days, args.force, args.refetch_panchanga, args.all)


if __name__ == "__main__":
    main()
