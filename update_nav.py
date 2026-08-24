import urllib.request
import re
import json
from datetime import datetime, timezone, timedelta

GPF_URL = "https://www.gpf.or.th/thai2019/About/main.php?page=memberfund&lang=th&size=n&pattern=n&menu=statistic"

def fetch_gpf_nav():
    req = urllib.request.Request(
        GPF_URL, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    try:
        raw_data = urllib.request.urlopen(req, timeout=15).read()
        try:
            html = raw_data.decode('utf-8')
        except UnicodeDecodeError:
            html = raw_data.decode('tis-620', errors='ignore')
    except Exception as e:
        print(f"Error fetching GPF website: {e}")
        return {}, None

    # 1. ดึง "วันที่ประกาศใช้" NAV จริงจากหน้าเว็บ กบข. (รองรับคำว่า วันที่ประกาศใช้ / ณ วันที่)
    nav_date_str = None
    date_match = re.search(
        r'(?:วันที่ประกาศใช้|ณ\s*วันที่|ประจำวันที่).*?(\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{4}|[0-9]{1,2}\s+[ก-๙\.]+\s+[0-9]{4})', 
        html, 
        re.DOTALL | re.IGNORECASE
    )
    if date_match:
        nav_date_str = date_match.group(1).strip()

    # 2. ดึงราคา NAV แต่ละแผน
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

    return nav_data, nav_date_str

def update_firebase(nav_data, nav_date_str):
    if not nav_data:
        print("❌ ไม่พบข้อมูล NAV จากหน้าเว็บ กบข.")
        return

    db_url = "https://scb-e-class-default-rtdb.asia-southeast1.firebasedatabase.app/gpf_ports/my-gpf-4750131.json"
    
    req = urllib.request.Request(db_url)
    current_data = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))

    if isinstance(current_data, dict):
        funds_list = current_data.get('funds', [])
    else:
        funds_list = current_data

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

    # สร้างข้อความวันที่แสดงผล
    tz_th = timezone(timedelta(hours=7))
    sync_time = datetime.now(tz_th).strftime('%d/%m %H:%M น.')
    
    # ปรับรูปแบบข้อความให้กระชับ เพื่อต่อกับคำว่า "อัปเดต NAV ล่าสุด:" บนหน้าเว็บ
    if nav_date_str:
        display_text = f"{nav_date_str} (Auto {sync_time})"
    else:
        display_text = f"{datetime.now(tz_th).strftime('%d/%m/%Y %H:%M น.')} (Auto)"

    if isinstance(current_data, dict):
        current_data['funds'] = funds_list
        current_data['lastUpdated'] = display_text
        payload = current_data
    else:
        payload = funds_list

    req = urllib.request.Request(db_url, data=json.dumps(payload).encode('utf-8'), method='PUT')
    req.add_header('Content-Type', 'application/json')
    urllib.request.urlopen(req)
    print(f"🚀 Firebase Updated: {display_text}")

if __name__ == "__main__":
    navs, nav_date = fetch_gpf_nav()
    print("NAV ที่ดึงได้ล่าสุด:", navs)
    print("วันที่ประกาศใช้จาก กบข.:", nav_date)
    update_firebase(navs, nav_date)
