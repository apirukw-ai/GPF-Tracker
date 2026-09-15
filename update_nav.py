import os
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup
import requests
from supabase import Client, create_client

# ----------------------------------------------------
# 1. เชื่อมต่อ Supabase และตั้งค่าคงที่
# ----------------------------------------------------
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("❌ Missing Supabase Credentials")
    exit(1)

supabase: Client = create_client(url, key)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
}


# ----------------------------------------------------
# 2. ฟังก์ชันดึง NAV ของ GPF
# ----------------------------------------------------
def get_gpf_nav_direct():
    """ดึงข้อมูล NAV ล่าสุดของแผนการลงทุน กบข. (GPF)"""
    nav_map = {}
    try:
        gpf_url = (
            "https://www.gpf.or.th/thai2019/About/main.php?"
            "page=memberfund&lang=th&size=n&pattern=n&menu=statistic"
        )
        res = requests.get(gpf_url, headers=HEADERS, timeout=15)
        res.encoding = "utf-8" if "utf-8" in res.text.lower() else "tis-620"

        soup = BeautifulSoup(res.text, "html.parser")
        rows = soup.find_all("tr")

        for row in rows:
            text = row.get_text()
            cols = [
                re.sub(r"\s+", "", col.get_text())
                for col in row.find_all(["td", "th"])
            ]
            if not cols:
                continue

            nav_candidates = []
            for col_text in cols:
                match = re.search(r"^\d{1,3}(?:,\d{3})*\.\d{4}$", col_text)
                if match:
                    nav_candidates.append(
                        float(match.group(0).replace(",", ""))
                    )

            if not nav_candidates:
                continue

            nav_val = nav_candidates[0]

            if "หุ้นต่างประเทศ" in text or "1788632129596" in text:
                nav_map["1788632129596"] = nav_val
                nav_map["แผนหุ้นต่างประเทศ"] = nav_val
            elif "หุ้นไทย" in text and "ต่างประเทศ" not in text:
                nav_map["1788631314182"] = nav_val
                nav_map["แผนหุ้นไทย"] = nav_val
            elif "อสังหาริมทรัพย์" in text or "1788632247228" in text:
                nav_map["1788632247228"] = nav_val
                nav_map["แผนอสังหาริมทรัพย์ไทย"] = nav_val

    except Exception as e:
        print(f"⚠️ GPF Fetch Error: {e}")

    return nav_map


# ----------------------------------------------------
# 3. ฟังก์ชันบันทึก Snapshot รายวัน
# ----------------------------------------------------
def save_daily_snapshot(supabase_client, app_source, total_thb):
    """บันทึกมูลค่าพอร์ตรวมรายวันลงตาราง portfolio_snapshots"""
    try:
        today_str = (datetime.now(timezone.utc) + timedelta(hours=7)).strftime(
            "%Y-%m-%d"
        )
        app_upper = app_source.upper()

        # ค้นหาค่า % ผลตอบแทนล่าสุดของ GPF จากประวัติเดิม
        prev_res = (
            supabase_client.table("portfolio_snapshots")
            .select(
                "reported_ytd_pct, reported_5y_pct, reported_since_inception_pct"
            )
            .ilike("app_source", app_upper)
            .order("snapshot_date", desc=True)
            .limit(1)
            .execute()
        )

        data = {
            "snapshot_date": today_str,
            "app_source": app_upper,
            "total_value_thb": float(total_thb),
        }

        # คงค่า % ผลตอบแทนเดิมไว้ไม่ให้กลายเป็น NULL
        if prev_res.data and len(prev_res.data) > 0:
            last_record = prev_res.data[0]
            if last_record.get("reported_ytd_pct") is not None:
                data["reported_ytd_pct"] = last_record["reported_ytd_pct"]
            if last_record.get("reported_5y_pct") is not None:
                data["reported_5y_pct"] = last_record["reported_5y_pct"]
            if last_record.get("reported_since_inception_pct") is not None:
                data["reported_since_inception_pct"] = last_record[
                    "reported_since_inception_pct"
                ]

        supabase_client.table("portfolio_snapshots").upsert(
            data, on_conflict="snapshot_date,app_source"
        ).execute()

        print(
            f"✅ Saved snapshot for {app_upper}: ฿{total_thb:,.2f} (Preserved % metrics)"
        )
    except Exception as e:
        print(f"⚠️ Failed to save snapshot for {app_source}: {e}")


# ----------------------------------------------------
# 4. ฟังก์ชันหลักสำหรับอัปเดต GPF
# ----------------------------------------------------
def fetch_and_update():
    try:
        thai_tz = timezone(timedelta(hours=7))
        now_thai_dt = datetime.now(thai_tz)
        now_thai = now_thai_dt.strftime("%Y-%m-%dT%H:%M:%S+07:00")
        today_date_str = now_thai_dt.strftime("%d/%m/%Y")

        gpf_nav_data = get_gpf_nav_direct()

        db_res = supabase.table("user_portfolios").select("*").execute()
        portfolio_items = db_res.data or []

        print(f"📦 พบรายการสินทรัพย์ทั้งหมดใน DB {len(portfolio_items)} รายการ")

        # --- อัปเดต current_nav เฉพาะ GPF ---
        for item in portfolio_items:
            item_id = item["id"]
            app = str(item.get("app_source", "")).strip().lower()
            code = str(item.get("asset_code", "")).strip()
            units = float(item.get("units") or 0)

            if app == "gpf":
                update_payload = {"updated_at": now_thai}
                latest_nav = gpf_nav_data.get(code)

                if latest_nav and latest_nav > 0:
                    update_payload["current_nav"] = round(latest_nav, 4)
                    update_payload["current_value"] = round(units * latest_nav, 4)
                    update_payload["nav_date"] = today_date_str

                supabase.table("user_portfolios").update(update_payload).eq("id", item_id).execute()

                c_nav = update_payload.get("current_nav", item.get("current_nav"))
                print(f" ✅ อัปเดตสำเร็จ GPF [{code}]: NAV={c_nav}")

        # --- คำนวณและบันทึก Daily Snapshot เฉพาะ GPF ---
        updated_db = supabase.table("user_portfolios").select("*").execute()
        latest_items = updated_db.data or []

        gpf_items = [
            item for item in latest_items
            if str(item.get("app_source", "")).strip().upper() == "GPF"
        ]

        total_thb = sum(float(item.get("current_value") or 0) for item in gpf_items)

        if total_thb > 0:
            save_daily_snapshot(supabase, "GPF", total_thb)

        print("✅ อัปเดต NAV และ Snapshot ของ GPF สำเร็จเรียบร้อย")

    except Exception as e:
        print(f"❌ Error during update process: {e}")


if __name__ == "__main__":
    fetch_and_update()