import urllib.request
import re
import json
import urllib.parse

# URL หน้าแสดง NAV ของ กบข.
GPF_URL = "https://www.gpf.or.th/thai2019/About/main.php?page=memberfund&lang=th&size=n&pattern=n&menu=statistic"

def fetch_gpf_nav():
    req = urllib.request.Request(
        GPF_URL, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    html = urllib.request.urlopen(req).read().decode('utf-8')

    # ตัวอย่างการดึงค่า NAV ของแต่ละแผนจากโครงสร้าง HTML ของ กบข.
    # (ระบบจะค้นหาข้อความชื่อแผน แล้วดึงตัวเลข NAV ถัดไป)
    nav_data = {}
    
    # Matching pattern สำหรับแผนต่าง ๆ
    patterns = {
        'แผนหุ้นต่างประเทศ': r'แผนหุ้นต่างประเทศ.*?(\d+\.\d{4})',
        'แผนหุ้นไทย': r'แผนหุ้นไทย.*?(\d+\.\d{4})',
        'แผนกองทุนอสังหาริมทรัพย์ไทย': r'แผนกองทุนอสังหาริมทรัพย์ไทย.*?(\d+\.\d{4})'
    }

    for fund_name, pattern in patterns.items():
        match = re.search(pattern, html, re.DOTALL)
        if match:
            nav_data[fund_name] = float(match.group(1))

    return nav_data

def update_firebase(nav_data):
    if not nav_data:
        print("ไม่พบข้อมูล NAV")
        return

    # URL Realtime Database ของคุณ
    db_url = "https://scb-e-class-default-rtdb.asia-southeast1.firebasedatabase.app/gpf_ports/my-gpf-4750131.json"
    
    # อ่านข้อมูลปัจจุบันจาก Firebase
    req = urllib.request.Request(db_url)
    current_data = json.loads(urllib.request.urlopen(req).read().decode('utf-8'))

    # อัปเดต NAV ปัจจุบันของแต่ละแผน
    for fund in current_data:
        code = fund.get('code')
        if code in nav_data:
            fund['currentNav'] = nav_data[code]
            print(f"Updated {code} -> {nav_data[code]}")

    # ส่งข้อมูลกลับไปยัง Firebase
    req = urllib.request.Request(db_url, data=json.dumps(current_data).encode('utf-8'), method='PUT')
    req.add_header('Content-Type', 'application/json')
    urllib.request.urlopen(req)
    print("Firebase Updated Successfully!")

if __name__ == "__main__":
    navs = fetch_gpf_nav()
    update_firebase(navs)