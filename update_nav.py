import urllib.request
import re
import json
import ssl
from datetime import datetime, timezone, timedelta

GPF_URL = "https://www.gpf.or.th/thai2019/About/main.php?page=memberfund&lang=th&size=n&pattern=n&menu=statistic"

def fetch_gpf_nav():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        GPF_URL, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            raw_data = resp.read()
            try:
                html = raw_data.decode('utf-8')
            except UnicodeDecodeError:
                html = raw_data.decode('tis-620', errors='ignore')
    except Exception as e:
        print(f"❌ Error fetching GPF website: {e}")
        return {}, None

    nav_date_str = None
    date_pattern = r'(?:วันที่ประกาศใช้|ณ\s*วันที่|ประจำวันที่)[\s\S]*?(\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{4}|\d{1,2}\s+[ก-๙\.]+\s+\d{4})'
    date_match = re.search(date_pattern, html, re.IGNORECASE)
    if date_match:
        nav_date_str = date_match.group(1).strip()

    nav_data = {}
    rows = re.findall(r'<tr.*?>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)

    for row in rows:
        nav_match = re.search(r'(\d+\.\d{4})', row)
        if not nav_match:
            continue
            
        nav_val = float(nav_match.group(1))

        if 'หุ้นต่างประเทศ' in row:
            nav_data['แผนหุ้นต่างประเทศ'] = nav_val
        elif 'หุ้นไทย' in row and 'ต่างประเทศ' not in row:
            nav_data['แผนหุ้นไทย'] = nav_val
        elif 'อสังหาริมทรัพย์' in row:
            nav_data['แผนกองทุนอสังหาริมทรัพย์ไทย'] = nav_val

print("NAV DATE =", nav_date_str)
print("NAV DATA =", nav_data)
    
    return nav_data, nav_date_str

def update_firebase(nav_data, nav_date_str):
    if not nav_data:
        print("❌ ไม่พบข้อมูล NAV จากหน้าเว็บ กบข.")
        return

    db_url = "https://scb-e-class-default-rtdb.asia-southeast1.firebasedatabase.app/gpf_ports/my-gpf-4750131.json"
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(db_url)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            current_data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"❌ Error fetching Firebase: {e}")
        return

    # ดึงเฉพาะรายการกองทุน
    if isinstance(current_data, dict):
        funds_list = current_data.get('funds', [])
    elif isinstance(current_data, list):
        funds_list = current_data
    else:
        funds_list = []

    for fund in funds_list:
        code = fund.get('code')
        if code in nav_data:
            new_nav = nav_data[code]
            old_nav = fund.get('currentNav', 0)

            if old_nav > 0 and new_nav != old_nav:
                pct_change = ((new_nav - old_nav) / old_nav) * 100
                fund['prevNav'] = old_nav
                fund['dailyPct'] = round(pct_change, 2)
            
            fund['currentNav'] = new_nav

    tz_th = timezone(timedelta(hours=7))
    sync_time = datetime.now(tz_th).strftime('%d/%m %H:%M น.')
    
    if nav_date_str:
        display_text = f"{nav_date_str} (Auto {sync_time})"
    else:
        display_text = f"{datetime.now(tz_th).strftime('%d/%m/%Y %H:%M น.')} (Auto)"

    # 🎯 บังคับสร้างโครงสร้าง Object ที่มี lastUpdated เสมอ
    payload = {
        "funds": funds_list,
        "lastUpdated": display_text
    }

    try:
        req = urllib.request.Request(db_url, data=json.dumps(payload).encode('utf-8'), method='PUT')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            print(f"🚀 Firebase Updated Successfully: {display_text}")
    except Exception as e:
        print(f"❌ Error updating Firebase: {e}")

if __name__ == "__main__":
    navs, nav_date = fetch_gpf_nav()
    update_firebase(navs, nav_date)
