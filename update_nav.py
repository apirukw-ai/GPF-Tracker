import urllib.request
import re
import json

GPF_URL = "https://www.gpf.or.th/thai2019/About/main.php?page=memberfund&lang=th&size=n&pattern=n&menu=statistic"

def fetch_gpf_nav():
    req = urllib.request.Request(
        GPF_URL, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    html = urllib.request.urlopen(req).read().decode('utf-8')

    nav_data = {}
    # แยกอ่านทีละแถวของตาราง HTML (<tr>...</tr>) เพื่อล็อคค่า NAV ให้ตรงแผน
    rows = re.findall(r'<tr.*?>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)

    for row in rows:
        # ค้นหาตัวเลข NAV (ทศนิยม 4 ตำแหน่ง) ในแถวนั้นๆ
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

    return nav_data

def update_firebase(nav_data):
    if not nav_data:
        print("ไม่พบข้อมูล NAV จากหน้าเว็บ")
        return

    db_url = "https://scb-e-class-default-rtdb.asia-southeast1.firebasedatabase.app/gpf_ports/my-gpf-4750131.json"
    
    req = urllib.request.Request(db_url)
    current_data = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))

    for fund in current_data:
        code = fund.get('code')
        if code in nav_data:
            new_nav = nav_data[code]
            old_nav = fund.get('currentNav', 0)

            # หากมี NAV เดิม และ NAV มีการเปลี่ยนแปลง ให้คำนวณ % รายวัน
            if old_nav > 0 and new_nav != old_nav:
                pct_change = ((new_nav - old_nav) / old_nav) * 100
                fund['prevNav'] = old_nav
                fund['change1d'] = round(pct_change, 2)
            
            fund['currentNav'] = new_nav
            print(f"Updated {code} -> NAV: {new_nav} (1D: {fund.get('change1d', 0)}%)")

    req = urllib.request.Request(db_url, data=json.dumps(current_data).encode('utf-8'), method='PUT')
    req.add_header('Content-Type', 'application/json')
    urllib.request.urlopen(req)
    print("Firebase Updated Successfully!")

if __name__ == "__main__":
    navs = fetch_gpf_nav()
    print("NAV ที่ดึงได้ล่าสุด:", navs)
    update_firebase(navs)
