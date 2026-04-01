import streamlit as st  # type: ignore
import pandas as pd  # type: ignore
import gspread  # type: ignore
from google.oauth2 import service_account  # type: ignore
from PIL import Image, ImageDraw, ImageFont  # type: ignore
import cloudinary  # type: ignore
import cloudinary.uploader  # type: ignore
import requests  # type: ignore
import json
import re
from io import BytesIO
from datetime import datetime
from typing import List, Dict, Any, Optional
import matplotlib.pyplot as plt
import seaborn as sns
try:
    import pdfplumber
except ImportError:
    pdfplumber = None
try:
    from pytrends.request import TrendReq
except ImportError:
    TrendReq = None


# --- 1.1 报告生成器常量 ---
VIEWING_CONTACT_WECHAT = "HaoHarbour"
VIEWING_CONTACT_PHONE = "07450912493"
VIEWING_DISCLAIMER = (
    "本报告仅基于带看人员在现场的个人观察，不构成任何形式的法律建议、房屋测量报告或合同要约。"
    "带看人员对隐藏缺陷、房屋结构问题或未来环境变化不承担法律责任，请客户在签约前务必自行核实关键信息。"
)

VIEWING_DEFAULT_INTERIOR = [
    "采光/通透度 (Natural Light)", "装修/家具维护 (Condition)", "窗户隔音/保暖 (Window Insulation)",
    "墙体/窗框防潮 (Damp/Mould)", "手机信号 (Signal)", "水压/排水速度 (Water Pressure)",
    "储物/收纳空间 (Storage)", "家电新旧 (Appliances)", "味道 (Smell)"
]
VIEWING_DEFAULT_BUILDING = [
    "24h 前台/安全感 (Concierge)", "快递代收系统 (Parcel Handling)", "公区卫生/气味 (Cleanliness)",
    "电梯数量/速度 (Lift Status)", "公共设施 (Gym/Lounge)"
]
VIEWING_DEFAULT_NEIGHBORHOOD = [
    "居住安静程度 (Quietness)", "街道整洁/安全 (Street Vibe)", "生活配套便利 (Shops/Cafe)",
    "交通便捷程度 (Transport)", "施工/脚手架干扰 (Construction)"
]

# --- 1. 初始化配置 ---
cloudinary.config(
    cloud_name = st.secrets["cloudinary"]["cloud_name"],
    api_key = st.secrets["cloudinary"]["api_key"],
    api_secret = st.secrets["cloudinary"]["api_secret"]
)

st.set_page_config(page_title="Hao Harbour Admin", layout="wide")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    .stAppDeployButton {display:none;} header {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden !important;}
    .stButton>button {width: 100%; background-color: #bfa064; color: white; font-weight: bold;}
    </style>
""", unsafe_allow_html=True)

# --- 2. 数据库连接 ---
def get_ws():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        return gspread.authorize(creds).open("Hao_Harbour_DB").get_worksheet(0)
    except Exception as e:
        st.error(f"数据库连接失败: {e}")
        return None

def get_all_records_safe(ws) -> list:
    """
    安全版 get_all_records：自动处理空列标题导致的 GSpreadException。
    先尝试标准方式，失败则改用 get_values() 手动解析，彻底跳过空列。
    """
    EXPECTED_HEADERS = ["date", "title", "region", "rooms", "price",
                        "poster-link", "description", "views", "is_featured",
                        "station", "walkingMinutes", "lat", "lng"]
    try:
        # 先尝试带 expected_headers 的方式（跳过不在列表里的空列头）
        return ws.get_all_records(expected_headers=EXPECTED_HEADERS)
    except Exception:
        pass
    try:
        # 退路：手动解析 raw values
        all_values = ws.get_all_values()
        if not all_values:
            return []
        raw_headers = all_values[0]
        # 只保留非空且在 EXPECTED_HEADERS 里的列
        col_indices = []
        seen = set()
        for idx, h in enumerate(raw_headers):
            if h and h in EXPECTED_HEADERS and h not in seen:
                col_indices.append((idx, h))
                seen.add(h)
        records = []
        for row in all_values[1:]:
            record = {}
            for idx, h in col_indices:
                record[h] = row[idx] if idx < len(row) else ""
            # 跳过完全空白的行
            if any(v for v in record.values()):
                records.append(record)
        return records
    except Exception as e:
        st.error(f"⚠️ Google Sheets 读取失败：{e}")
        return []

# --- 3. 智能伦敦分区 ---
# 基于英国邮编前缀（outward code）精准定位伦敦五大区
# 数据来源：英国皇家邮政 + Google Maps 地理验证
_POSTCODE_REGION: Dict[str, str] = {
    # 中伦敦 (Central London) — EC / WC / W1 / SW1 / SE1 etc.
    "EC1": "中伦敦", "EC2": "中伦敦", "EC3": "中伦敦", "EC4": "中伦敦",
    "WC1": "中伦敦", "WC2": "中伦敦",
    "W1":  "中伦敦", "W1A": "中伦敦", "W1B": "中伦敦", "W1C": "中伦敦",
    "W1D": "中伦敦", "W1F": "中伦敦", "W1G": "中伦敦", "W1H": "中伦敦",
    "W1J": "中伦敦", "W1K": "中伦敦", "W1S": "中伦敦", "W1T": "中伦敦",
    "W1U": "中伦敦", "W1W": "中伦敦",
    "SW1": "中伦敦", "SW1A": "中伦敦", "SW1E": "中伦敦", "SW1H": "中伦敦",
    "SW1P": "中伦敦", "SW1V": "中伦敦", "SW1W": "中伦敦", "SW1X": "中伦敦",
    "SW1Y": "中伦敦",
    "SE1":  "中伦敦",
    "N1C": "中伦敦",   # King's Cross area
    # 东伦敦 (East London)
    "E1":  "东伦敦", "E1W": "东伦敦", "E2":  "东伦敦", "E3":  "东伦敦",
    "E4":  "东伦敦", "E5":  "东伦敦", "E6":  "东伦敦", "E7":  "东伦敦",
    "E8":  "东伦敦", "E9":  "东伦敦", "E10": "东伦敦", "E11": "东伦敦",
    "E12": "东伦敦", "E13": "东伦敦", "E14": "东伦敦", "E15": "东伦敦",
    "E16": "东伦敦", "E17": "东伦敦", "E18": "东伦敦", "E20": "东伦敦",
    "IG1": "东伦敦", "IG2": "东伦敦", "IG3": "东伦敦", "IG4": "东伦敦",
    "IG5": "东伦敦", "IG6": "东伦敦", "IG7": "东伦敦", "IG8": "东伦敦",
    "IG11": "东伦敦",
    "RM1": "东伦敦", "RM2": "东伦敦", "RM3": "东伦敦", "RM4": "东伦敦",
    "RM5": "东伦敦", "RM6": "东伦敦", "RM7": "东伦敦", "RM8": "东伦敦",
    "RM9": "东伦敦", "RM10": "东伦敦", "RM11": "东伦敦", "RM12": "东伦敦",
    "RM13": "东伦敦", "RM14": "东伦敦",
    "DA1": "东伦敦", "DA2": "东伦敦", "DA5": "东伦敦", "DA6": "东伦敦",
    "DA7": "东伦敦", "DA8": "东伦敦", "DA15": "东伦敦", "DA16": "东伦敦", "DA17": "东伦敦", "DA18": "东伦敦",
    # 西伦敦 (West London)
    "W2":  "西伦敦", "W3":  "西伦敦", "W4":  "西伦敦", "W5":  "西伦敦",
    "W6":  "西伦敦", "W7":  "西伦敦", "W8":  "西伦敦", "W9":  "西伦敦",
    "W10": "西伦敦", "W11": "西伦敦", "W12": "西伦敦", "W13": "西伦敦",
    "W14": "西伦敦",
    "TW1": "西伦敦", "TW2": "西伦敦", "TW3": "西伦敦", "TW4": "西伦敦",
    "TW5": "西伦敦", "TW6": "西伦敦", "TW7": "西伦敦", "TW8": "西伦敦",
    "TW9": "西伦敦", "TW10": "西伦敦", "TW11": "西伦敦", "TW12": "西伦敦",
    "TW13": "西伦敦", "TW14": "西伦敦",
    "UB1": "西伦敦", "UB2": "西伦敦", "UB3": "西伦敦", "UB4": "西伦敦",
    "UB5": "西伦敦", "UB6": "西伦敦", "UB7": "西伦敦", "UB8": "西伦敦",
    "UB9": "西伦敦", "UB10": "西伦敦", "UB11": "西伦敦",
    "HA0": "西伦敦", "HA1": "西伦敦", "HA2": "西伦敦", "HA3": "西伦敦",
    "HA4": "西伦敦", "HA5": "西伦敦", "HA6": "西伦敦", "HA7": "西伦敦",
    "HA8": "西伦敦", "HA9": "西伦敦",
    "SW6": "西伦敦", "SW10": "西伦敦",   # Fulham / Chelsea
    # 北伦敦 (North London)
    "N1":  "北伦敦", "N2":  "北伦敦", "N3":  "北伦敦", "N4":  "北伦敦",
    "N5":  "北伦敦", "N6":  "北伦敦", "N7":  "北伦敦", "N8":  "北伦敦",
    "N9":  "北伦敦", "N10": "北伦敦", "N11": "北伦敦", "N12": "北伦敦",
    "N13": "北伦敦", "N14": "北伦敦", "N15": "北伦敦", "N16": "北伦敦",
    "N17": "北伦敦", "N18": "北伦敦", "N19": "北伦敦", "N20": "北伦敦",
    "N21": "北伦敦", "N22": "北伦敦",
    "NW1": "北伦敦", "NW2": "北伦敦", "NW3": "北伦敦", "NW4": "北伦敦",
    "NW5": "北伦敦", "NW6": "北伦敦", "NW7": "北伦敦", "NW8": "北伦敦",
    "NW9": "北伦敦", "NW10": "北伦敦", "NW11": "北伦敦",
    "EN1": "北伦敦", "EN2": "北伦敦", "EN3": "北伦敦", "EN4": "北伦敦",
    "EN5": "北伦敦", "EN6": "北伦敦",
    "WD6": "北伦敦", "WD17": "北伦敦", "WD18": "北伦敦", "WD19": "北伦敦", "WD23": "北伦敦", "WD24": "北伦敦", "WD25": "北伦敦",
    # 南伦敦 (South London)
    "SE2":  "南伦敦", "SE3":  "南伦敦", "SE4":  "南伦敦", "SE5":  "南伦敦",
    "SE6":  "南伦敦", "SE7":  "南伦敦", "SE8":  "南伦敦", "SE9":  "南伦敦",
    "SE10": "南伦敦", "SE11": "南伦敦", "SE12": "南伦敦", "SE13": "南伦敦",
    "SE14": "南伦敦", "SE15": "南伦敦", "SE16": "南伦敦", "SE17": "南伦敦",
    "SE18": "南伦敦", "SE19": "南伦敦", "SE20": "南伦敦", "SE21": "南伦敦",
    "SE22": "南伦敦", "SE23": "南伦敦", "SE24": "南伦敦", "SE25": "南伦敦",
    "SE26": "南伦敦", "SE27": "南伦敦", "SE28": "南伦敦",
    "SW2":  "南伦敦", "SW3":  "南伦敦", "SW4":  "南伦敦", "SW5":  "南伦敦",
    "SW7":  "南伦敦", "SW8":  "南伦敦", "SW9":  "南伦敦",
    "SW11": "南伦敦", "SW12": "南伦敦", "SW13": "南伦敦", "SW14": "南伦敦",
    "SW15": "南伦敦", "SW16": "南伦敦", "SW17": "南伦敦", "SW18": "南伦敦",
    "SW19": "南伦敦", "SW20": "南伦敦",
    "CR0": "南伦敦", "CR2": "南伦敦", "CR3": "南伦敦", "CR4": "南伦敦",
    "CR5": "南伦敦", "CR6": "南伦敦", "CR7": "南伦敦", "CR8": "南伦敦",
    "SM1": "南伦敦", "SM2": "南伦敦", "SM3": "南伦敦", "SM4": "南伦敦",
    "SM5": "南伦敦", "SM6": "南伦敦", "SM7": "南伦敦",
    "KT1": "南伦敦", "KT2": "南伦敦", "KT3": "南伦敦", "KT4": "南伦敦",
    "KT5": "南伦敦", "KT6": "南伦敦", "KT7": "南伦敦", "KT8": "南伦敦",
    "KT9": "南伦敦", "KT10": "南伦敦", "KT17": "南伦敦", "KT18": "南伦敦",
    "BR1": "南伦敦", "BR2": "南伦敦", "BR3": "南伦敦", "BR4": "南伦敦",
    "BR5": "南伦敦", "BR6": "南伦敦", "BR7": "南伦敦",
}

def infer_london_region(postcode: str) -> str:
    """根据英国邮编智能判断伦敦区域，无需任何 API Key。"""
    if not postcode:
        return "中伦敦"
    pc = postcode.upper().strip()
    # 提取 outward code — 邮编前半部分 (e.g. "SW1A" from "SW1A 1AA")
    if " " in pc:
        outward: str = pc.split()[0]
    else:
        m = re.match(r'^[A-Z]{1,2}[0-9]{1,2}[A-Z]?', pc)
        outward = m.group() if m else pc[:4]
    # 尝试从长到短匹配 (e.g. SW1A -> SW1 -> SW)
    for length in [4, 3, 2]:
        candidate: str = outward[:length]
        if candidate in _POSTCODE_REGION:
            return _POSTCODE_REGION[candidate]
    return "中伦敦"  # 默认回退

# --- 3. AI 文案解析 ---
def call_smart_ai(text):
    if not text: return "✓ 请输入描述"
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
        prompt = "作为一名资深伦敦房产专家，请将这段英文房源描述转化为极具吸引力的小红书爆款文案。要求：1. 标题要吸睛（使用Emoji）；2. 核心卖点提炼清晰（地理位置、交通、设施等）；3. 语言生动活泼，多使用小红书常用Emoji；4. 绝对不要包含微信号或任何扫码加微信等容易被封号的词汇，可以写'欢迎私信或留言咨询'；5. 结尾加上相关的热门标签（如 #伦敦租房 #伦敦公寓 等）。"
        r = requests.post("https://api.deepseek.com/chat/completions",
            json={"model": "deepseek-chat", "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text}]},
            headers={"Authorization": f"Bearer {api_key}"}, timeout=25)
        return r.json()['choices'][0]['message']['content'].replace("**", "")
    except: return "✓ 解析失败，请手动修改"

def scrape_rightmove(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-GB,en;q=0.9'
    }
    try:
        if not url or "rightmove.co.uk" not in url:
            return None, "无效的 Rightmove 链接"
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        html = res.text
        if 'window.PAGE_MODEL = ' in html:
            page_model_raw = html.split('window.PAGE_MODEL = ')[1].strip()
            try:
                data, _ = json.JSONDecoder().raw_decode(page_model_raw)
                p_data = data.get('propertyData', {})
            except json.JSONDecodeError as e:
                return None, f"JSON解析失败: {e}"
            
            if p_data:
                raw_title = p_data.get('text', {}).get('pageTitle', '')
                if " in " in raw_title:
                    title = raw_title.split(" in ", 1)[-1].strip()
                else:
                    title = raw_title
                price_str = p_data.get('prices', {}).get('primaryPrice', '')
                try: price = int(re.sub(r'[^\d]', '', price_str))
                except: price = 0
                desc_html = p_data.get('text', {}).get('description', '')
                desc = re.sub(r'<[^>]+>', '', desc_html).strip()
                bedrooms = p_data.get('bedrooms', 0)
                if bedrooms == 0: rooms_str = "Studio"
                elif bedrooms >= 4: rooms_str = "4房+"
                else: rooms_str = f"{bedrooms}房"
                img_data: Any = p_data.get('images', [])
                images: List[str] = [str(img.get('url')) for img in img_data if isinstance(img, dict) and img.get('url')] if isinstance(img_data, list) else []
                
                fp_data: Any = p_data.get('floorplans', [])
                floorplans: List[str] = [str(fp.get('url')) for fp in fp_data if isinstance(fp, dict) and fp.get('url')] if isinstance(fp_data, list) else []
                
                final_images: List[str] = images[:8]
                if floorplans and len(final_images) >= 7:
                    final_images = final_images[:7] + [floorplans[0]]
                elif floorplans:
                    final_images.append(floorplans[0])
                
                # 提取最近的3个地铁/火车站和具体经纬度
                stations_data = []
                if 'location' in p_data and 'stations' in p_data['location']:
                    stations_data = p_data['location']['stations']
                elif 'stations' in p_data:
                    stations_data = p_data['stations']
                
                nearest_stations = []
                for s in stations_data[:3]:
                    if isinstance(s, dict) and s.get('name'):
                        s_name = s['name']
                        s_dist = s.get('distance', '')
                        s_unit = s.get('unit', 'mi')
                        if s_dist != '':
                            # Format to 1 decimal place if float
                            try:
                                d_val = float(s_dist)
                                s_dist_fmt = f"{d_val:.1f}"
                            except ValueError:
                                s_dist_fmt = str(s_dist)
                            nearest_stations.append(f"{s_name} ({s_dist_fmt}{s_unit})")
                        else:
                            nearest_stations.append(s_name)
                stations_str = ", ".join(nearest_stations)
                
                # Extract exact coordinates for precision mapping
                lat, lng = "", ""
                if 'location' in p_data:
                    lat = p_data['location'].get('latitude', '')
                    lng = p_data['location'].get('longitude', '')
                
                # 智能分区：从房源地址/邮编自动判断伦敦区域
                address_info: Any = p_data.get('address', {})
                postcode: str = ""
                if isinstance(address_info, dict):
                    postcode = str(address_info.get('outcode', '') or address_info.get('postcode', '') or '')
                if not postcode:
                    # 从标题中尝试提取邮编
                    pc_match = re.search(r'\b([A-Z]{1,2}[0-9]{1,2}[A-Z]?\s?[0-9][A-Z]{2})\b', title.upper())
                    if pc_match:
                        postcode = pc_match.group(1)
                auto_region: str = infer_london_region(postcode)
                
                return {
                    'title': title, 'price': price, 'rooms': rooms_str,
                    'description': desc, 'images': final_images,
                    'region': auto_region, 'postcode': postcode,
                    'station': stations_str,
                    'lat': lat,
                    'lng': lng
                }, None
        return None, "无法解析数据，请检查链接是否为房源页"
    except Exception as e:
        return None, f"抓取失败: {e}"

# --- 4. 核心：海报引擎 (仅修改 display_text 拼接) ---
def create_poster(files, title, price, rooms, region="伦敦"):
    try:
        # 1200x2350 高清加长画布 (8宫格)
        canvas = Image.new('RGB', (1200, 2350), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        
        try:
            font_banner = ImageFont.truetype("simhei.ttf", 60)
            font_title = ImageFont.truetype("simhei.ttf", 65)
            font_price = ImageFont.truetype("simhei.ttf", 100)
            font_footer = ImageFont.truetype("simhei.ttf", 38)
            font_wm = ImageFont.truetype("simhei.ttf", 130) # 水印字体
        except:
            font_banner = font_title = font_price = font_footer = font_wm = ImageFont.load_default()

        # A. 顶部横幅 Banner
        draw.rectangle([(0, 0), (1200, 130)], fill=(26, 26, 26))
        
        # 居中 Hao Harbour
        banner_text = "HAO HARBOUR"
        left_padding = 420
        # draw.text_length
        draw.text((left_padding, 35), banner_text, font=font_banner, fill=(191, 160, 100))

        # B. 8 宫格拼接 (2列 x 4行)
        for i, f in enumerate(files[:8]):
            img = Image.open(f).convert('RGB').resize((575, 430), Image.Resampling.LANCZOS)
            x = 20 + (i % 2) * 585
            y = 150 + (i // 2) * 440
            canvas.paste(img, (x, y))

        # C. 双居中加深水印 (一上一下)
        wm_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        wm_draw = ImageDraw.Draw(wm_layer)
        wm_color = (255, 255, 255, 140) 
        
        # 水印位置顺应更长的画布
        wm_draw.text((220, 600), "Hao Harbour", font=font_wm, fill=wm_color)
        wm_draw.text((220, 1500), "Hao Harbour", font=font_wm, fill=wm_color)
        
        rotated_wm = wm_layer.rotate(30, expand=False)
        canvas.paste(rotated_wm, (0, 0), rotated_wm)

        # D. 底部专业信息区 (Y = 1950 起始)
        draw.text((40, 1950), f"{title}", font=font_title, fill=(40, 40, 40))
        draw.text((40, 2030), f"Location: {region}", font=font_footer, fill=(100, 100, 100))
        
        draw.text((40, 2100), f"GBP {price} / PCM", font=font_price, fill=(191, 160, 100))
        # 户型标签：用圆点分隔，避免竖线符号渲染为灰色线条
        draw.text((40, 2225), f"•  {rooms}", font=font_footer, fill=(120, 120, 120))
        
        # 装饰金色线条
        draw.line([(40, 2260), (1160, 2260)], fill=(200, 200, 200), width=3)
        draw.text((40, 2280), "Hao Harbour Exclusive London Property", font=font_footer, fill=(180, 160, 100))
        
        return canvas
    except Exception as e:
        st.error(f"海报生成出错: {e}")
        return None
# --- 4b. 微信方版海报 1080x1080 ---
def create_wechat_poster(files, title, price, rooms, region="伦敦"):
    try:
        canvas = Image.new('RGB', (1080, 1080), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        try:
            fb = ImageFont.truetype("simhei.ttf", 48)
            ft = ImageFont.truetype("simhei.ttf", 44)
            fp = ImageFont.truetype("simhei.ttf", 68)
            ff = ImageFont.truetype("simhei.ttf", 30)
            fw = ImageFont.truetype("simhei.ttf", 100)
        except:
            fb = ft = fp = ff = fw = ImageFont.load_default()
        # Banner
        draw.rectangle([(0, 0), (1080, 100)], fill=(26, 26, 26))
        draw.text((330, 26), "HAO HARBOUR", font=fb, fill=(191, 160, 100))
        # 2x2 图片网格
        for i, f in enumerate(files[:4]):
            img = Image.open(f).convert('RGB').resize((520, 260), Image.Resampling.LANCZOS)
            x = 20 + (i % 2) * 540
            y = 115 + (i // 2) * 270
            canvas.paste(img, (x, y))
        # 水印
        wm = Image.new('RGBA', canvas.size, (0,0,0,0))
        ImageDraw.Draw(wm).text((100, 320), "Hao Harbour", font=fw, fill=(255,255,255,120))
        wm = wm.rotate(20, expand=False)
        canvas.paste(wm, (0, 0), wm)
        # 信息区
        draw.text((30, 680), title[:28], font=ft, fill=(40,40,40))
        draw.text((30, 735), f"Location: {region}", font=ff, fill=(100,100,100))
        draw.text((30, 780), f"GBP {price} / PCM", font=fp, fill=(191,160,100))
        draw.text((30, 870), f"• {rooms}", font=ff, fill=(120,120,120))
        draw.line([(30, 910), (1050, 910)], fill=(200,200,200), width=2)
        draw.text((30, 925), "Hao Harbour Exclusive London Property", font=ff, fill=(180,160,100))
        return canvas
    except Exception as e:
        st.error(f"微信海报生成出错: {e}")
        return None

# --- 4c. 抖音/Story 竖版海报 1080x1920 ---
def create_story_poster(files, title, price, rooms, region="伦敦"):
    try:
        canvas = Image.new('RGB', (1080, 1920), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        try:
            fb = ImageFont.truetype("simhei.ttf", 54)
            ft = ImageFont.truetype("simhei.ttf", 55)
            fp = ImageFont.truetype("simhei.ttf", 85)
            ff = ImageFont.truetype("simhei.ttf", 34)
            fw = ImageFont.truetype("simhei.ttf", 110)
        except:
            fb = ft = fp = ff = fw = ImageFont.load_default()
        # Banner
        draw.rectangle([(0, 0), (1080, 115)], fill=(26, 26, 26))
        draw.text((330, 28), "HAO HARBOUR", font=fb, fill=(191, 160, 100))
        # 3x2 图片网格
        for i, f in enumerate(files[:6]):
            img = Image.open(f).convert('RGB').resize((520, 370), Image.Resampling.LANCZOS)
            x = 20 + (i % 2) * 540
            y = 130 + (i // 2) * 380
            canvas.paste(img, (x, y))
        # 水印
        wm = Image.new('RGBA', canvas.size, (0,0,0,0))
        wd = ImageDraw.Draw(wm)
        wd.text((150, 500), "Hao Harbour", font=fw, fill=(255,255,255,120))
        wd.text((150, 1200), "Hao Harbour", font=fw, fill=(255,255,255,120))
        wm = wm.rotate(25, expand=False)
        canvas.paste(wm, (0,0), wm)
        # 信息区
        draw.text((40, 1278), title[:30], font=ft, fill=(40,40,40))
        draw.text((40, 1345), f"Location: {region}", font=ff, fill=(100,100,100))
        draw.text((40, 1400), f"GBP {price} / PCM", font=fp, fill=(191,160,100))
        draw.text((40, 1510), f"• {rooms}", font=ff, fill=(120,120,120))
        draw.line([(40, 1560), (1040, 1560)], fill=(200,200,200), width=2)
        draw.text((40, 1580), "Hao Harbour Exclusive London Property", font=ff, fill=(180,160,100))
        # 底部装饰条
        draw.rectangle([(0, 1860), (1080, 1920)], fill=(26,26,26))
        draw.text((340, 1874), "@HAO HARBOUR", font=ff, fill=(191,160,100))
        return canvas
    except Exception as e:
        st.error(f"抖音海报生成出错: {e}")
        return None

# --- 4d. 抖音口播脚本生成 ---
def gen_douyin_script(title: str, price: int, rooms: str, region: str, desc: str) -> str:
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
        prompt = (
            "你是一个抖音/小红书房产博主，请根据以下伦敦房源信息，写一段15秒口播文案。"
            "要求：①开头3秒必须有钩子（惊喜/痛点/数字）②语言口语化、有节奏感 "
            "③结尾引导点赞收藏 ④全文不超过120字 ⑤不要用微信/扫码等违禁词。"
        )
        content = f"房源：{title}，位于{region}，{rooms}，月租£{price}。描述：{desc[:300]}"
        r = requests.post("https://api.deepseek.com/chat/completions",
            json={"model": "deepseek-chat", "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content}
            ]},
            headers={"Authorization": f"Bearer {api_key}"}, timeout=20)
        return r.json()['choices'][0]['message']['content'].strip()
    except:
        return f"🎬 【{region}·{rooms}】仅£{price}/月！\n{title}，地段好、装修新，稀缺好房等你！\n👉 点赞收藏，私信了解详情！"


# --- 4e. 专业带看报告生成器 (Text & PDF) ---
def gen_pro_viewing_summary(client_name: str, date: str, address: str, facing: str, items: Dict[str, Dict[str, int]], remarks: Dict[str, str]) -> str:
    """生成带 Emoji 和颜色区分的结构化文案"""
    summary = [
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🏠 专业带看报告 | Viewing Report",
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
        f"👤 客户：{client_name}",
        f"📅 日期：{date}",
        f"📍 地址：{address}",
        f"🧭 朝向：{facing}",
        f"📞 联系：Wechat {VIEWING_CONTACT_WECHAT} | {VIEWING_CONTACT_PHONE}",
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
    ]
    
    for section, section_items in items.items():
        summary.append(f"【{section}】")
        for item, score in section_items.items():
            # 评分 4-5 为绿色，3 为黄色，1-2 为红色
            emoji = "🟢" if score >= 4 else ("🟡" if score == 3 else "🔴")
            stars = "⭐" * score
            summary.append(f" {emoji} {item}: {stars}")
        if remarks.get(section):
            summary.append(f" 📝 备注: {remarks[section]}")
        summary.append("")

    if remarks.get('General'):
        summary.append(f"💬 总体评价: {remarks['General']}\n")
    
    summary.append("⚠️ 免责声明:")
    summary.append(VIEWING_DISCLAIMER)
    summary.append("━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(summary)

def create_viewing_report_pdf(client_name, date_str, address, facing, items_data, remarks, photos):
    """使用 PIL 生成长图并保存为 PDF"""
    try:
        f_header = ImageFont.truetype("simhei.ttf", 40)
        f_body = ImageFont.truetype("simhei.ttf", 32)
        f_star = ImageFont.truetype("simhei.ttf", 35)
        f_footer = ImageFont.truetype("simhei.ttf", 24)
        f_banner = ImageFont.truetype("simhei.ttf", 50)
        f_wm = ImageFont.truetype("simhei.ttf", 120)
    except:
        f_header = f_body = f_star = f_footer = f_banner = f_wm = ImageFont.load_default()

    def draw_wrapped_text(draw, text, x, y, font, max_width, fill=(80, 80, 80)):
        if not text: return y
        lines = []
        current_line = ""
        for char in text:
            test_line = current_line + char
            if draw.textlength(test_line, font=font) <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = char
        lines.append(current_line)
        for line in lines:
            draw.text((x, y), line, font=font, fill=fill)
            y += font.size + 15
        return y

    # 预估高度：基础文本 + 评分项 + 备注自动换行预估 + 照片
    # 每个备注预估占用额外 100 像素
    total_items = sum(len(v) for v in items_data.values())
    photo_rows = (len(photos) + 1) // 2
    estimated_height = 1000 + (total_items * 65) + (len(items_data) * 200) + (photo_rows * 460) + 600
    
    canvas = Image.new('RGB', (1200, int(estimated_height)), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    
    # 1. 页眉 Banner
    draw.rectangle([(0, 0), (1200, 150)], fill=(26, 26, 26))
    draw.text((60, 45), "HAO HARBOUR - 专业带看报告", font=f_banner, fill=(191, 160, 100))
    
    # 2. 基本信息
    y = 190
    draw.text((60, y), f"客户姓名: {client_name}", font=f_body, fill=(50, 50, 50))
    draw.text((600, y), f"看房日期: {date_str}", font=f_body, fill=(50, 50, 50))
    y += 65
    draw.text((60, y), f"房屋地址: {address}", font=f_body, fill=(50, 50, 50))
    y += 65
    draw.text((60, y), f"房屋朝向: {facing}", font=f_body, fill=(50, 50, 50))
    y += 65
    draw.text((60, y), f"联系方式: WeChat {VIEWING_CONTACT_WECHAT} | {VIEWING_CONTACT_PHONE}", font=f_body, fill=(191, 160, 100))
    
    y += 50
    draw.line([(60, y), (1140, y)], fill=(200, 200, 200), width=2)
    y += 50

    # 3. 核心评估板块
    for section, s_items in items_data.items():
        draw.text((60, y), f"【{section}】", font=f_header, fill=(191, 160, 100))
        y += 80
        for item, score in s_items.items():
            star_color = (34, 139, 34) if score >= 4 else ((255, 140, 0) if score == 3 else (220, 20, 60))
            draw.text((80, y), item, font=f_body, fill=(80, 80, 80))
            draw.text((630, y), "★" * score + "☆" * (5 - score), font=f_star, fill=star_color)
            y += 65
        
        if remarks.get(section):
            y = draw_wrapped_text(draw, f"备注: {remarks[section]}", 80, y, f_body, 1040, fill=(110, 110, 110))
        y += 45

    # 4. 总体备注
    if remarks.get('General'):
        draw.text((60, y), "总体备注:", font=f_header, fill=(50, 50, 50))
        y += 70
        y = draw_wrapped_text(draw, remarks['General'], 80, y, f_body, 1040, fill=(80, 80, 80))
        y += 60

    # 5. 照片展示
    if photos:
        draw.text((60, y), "现场照片:", font=f_header, fill=(50, 50, 50))
        y += 80
        for i, photo_data in enumerate(photos):
            try:
                img = Image.open(photo_data).convert("RGB")
                img.thumbnail((520, 420))
                px = 80 + (i % 2) * 540
                py = y + (i // 2) * 460
                canvas.paste(img, (px, py))
            except: pass
        y += photo_rows * 460 + 80

    # 6. 斜向加深水印 (与房子海报一致)
    wm_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    wm_draw = ImageDraw.Draw(wm_layer)
    # 使用白色/浅灰色高透明度水印，多处覆盖
    wm_color = (180, 180, 180, 70) 
    for row in range(0, canvas.size[1], 1000):
        for col in range(0, 1200, 600):
            wm_draw.text((col + 50, row + 400), "Hao Harbour", font=f_wm, fill=wm_color)
    
    rotated_wm = wm_layer.rotate(35, expand=False)
    canvas.paste(rotated_wm, (0, 0), rotated_wm)

    # 7. 页脚免责声明
    footer_height = 280
    pdf_final_height = y + footer_height
    final_canvas = canvas.crop((0, 0, 1200, int(pdf_final_height)))
    final_draw = ImageDraw.Draw(final_canvas)
    
    footer_y = pdf_final_height - footer_height
    final_draw.rectangle([(0, footer_y), (1200, pdf_final_height)], fill=(245, 245, 245))
    words = VIEWING_DISCLAIMER
    draw_wrapped_text(final_draw, words, 60, footer_y + 40, f_footer, 1080, fill=(140, 140, 140))

    return final_canvas

# --- 4f. 房源对比图生成 (PIL) ---
def gen_comparison_image(selected_props: List[Dict]) -> Image.Image:
    # 创建对比长图 (最多4套)
    n = len(selected_props)
    w, h = 1200, 800 + (n * 250)
    img = Image.new('RGB', (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        f_h = ImageFont.truetype("Arial.ttf", 40)
        f_b = ImageFont.truetype("Arial.ttf", 24)
        f_p = ImageFont.truetype("Arial.ttf", 32)
    except:
        f_h = f_b = f_p = ImageFont.load_default()

    # 标题
    draw.rectangle([0, 0, w, 120], fill=(191,160,100))
    draw.text((w//2 - 150, 35), "房源对比表 | Property Comparison", font=f_h, fill=(255,255,255))

    # 表头
    headers = ["照片", "房源名称", "区域", "户型", "价格 (PCM)"]
    x_offsets = [50, 250, 550, 750, 950]
    for i, head in enumerate(headers):
        draw.text((x_offsets[i], 160), head, font=f_b, fill=(100,100,100))
    
    draw.line([(40, 200), (w-40, 200)], fill=(200,200,200), width=2)

    for i, p in enumerate(selected_props):
        y = 250 + (i * 250)
        # 缩略图
        try:
            r = requests.get(p['poster-link'], timeout=5)
            thumb = Image.open(BytesIO(r.content)).convert("RGB")
            thumb.thumbnail((150, 150))
            img.paste(thumb, (50, y))
        except:
            draw.rectangle([50, y, 200, y+150], outline=(200,200,200))
        
        draw.text((250, y + 40), str(p['title'])[:20], font=f_b, fill=(40,40,40))
        draw.text((550, y + 40), str(p['region']), font=f_b, fill=(40,40,40))
        draw.text((750, y + 40), str(p['rooms']), font=f_b, fill=(40,40,40))
        draw.text((950, y + 40), f"£{p['price']}", font=f_p, fill=(191,160,100))
        
        if i < n - 1:
            draw.line([(40, y + 210), (w-40, y + 210)], fill=(240,240,240), width=1)

    return img

# --- 4g. 市场热度研究 (Trends) ---
def get_market_trends(keyword: str = "London Rent"):
    if not TrendReq: return None
    try:
        pytrends = TrendReq(hl='en-US', tz=360)
        pytrends.build_payload([keyword], cat=0, timeframe='today 3-m', geo='GB-LND')
        df = pytrends.interest_over_time()
        return df
    except:
        return None

# --- 4h. 合同提取 (AI) ---

# --- 4h. 合同助手：智能提取与分析 ---
def parse_ai_json(text: str):
    """解析 AI 返回的 JSON，处理 Markdown 代码块和列表/字典两种格式"""
    try:
        clean = re.sub(r"```json\s*|\s*```", "", text).strip()
        # Remove any leading/trailing non-JSON characters
        # Find first [ or { 
        for start_ch, end_ch in [('[', ']'), ('{', '}')]:
            idx = clean.find(start_ch)
            if idx >= 0:
                # find matching close
                sub = clean[idx:]
                try:
                    result = json.loads(sub)
                    return result
                except:
                    pass
        return {}
    except:
        return {}

def extract_contract_pro(pdf_file, target_lang="中文") -> Dict[str, Any]:
    """
    深度合同分析 v4.0 — 三段式多轮 AI 分析策略：
      Pass 1: 提取核心元数据（租金/押金/日期/当事人）
      Pass 2: 逐章节深度解读（所有条款分组摘要）
      Pass 3: 综合风险评估 + 租客行动建议
    """
    if not pdfplumber:
        return {"error": "⚠️ 未安装 pdfplumber 依赖，无法解析 PDF。"}
    try:
        # ── 读取全部页面 ──
        pages_text = []
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t.strip())
        full_text = "\n\n".join(pages_text)
        if not full_text.strip():
            return {"error": "⚠️ 无法从 PDF 中提取文字，可能是扫描版图片，请上传文字版合同。"}

        api_key = st.secrets["OPENAI_API_KEY"]
        lang_note = "请用中文回答所有内容。" if target_lang == "中文" else "Please respond entirely in English."

        def call_ai(system_prompt: str, user_content: str, timeout: int = 120) -> str:
            try:
                r = requests.post(
                    "https://api.deepseek.com/chat/completions",
                    json={"model": "deepseek-chat", "max_tokens": 4096, "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": user_content}
                    ]},
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=timeout
                )
                r.raise_for_status()
                result = r.json()["choices"][0]["message"]["content"]
                return result
            except requests.exceptions.Timeout:
                return '{"error": "API timeout"}'
            except requests.exceptions.RequestException as e:
                return f'{{"error": "API request failed: {str(e)[:100]}"}}'
            except (KeyError, IndexError) as e:
                return f'{{"error": "API response malformed: {str(e)[:100]}"}}'

        # ── 截取前 8000 字符 + 后 4000 字符覆盖合同首尾（元数据/特殊条款通常在头尾）──
        text_head = full_text[:8000]
        text_tail = full_text[-4000:] if len(full_text) > 10000 else ""
        text_middle_chunks = []
        chunk_size = 6000
        middle = full_text[8000:len(full_text)-4000] if len(full_text) > 12000 else ""
        for i in range(0, len(middle), chunk_size):
            text_middle_chunks.append(middle[i:i+chunk_size])

        # ════════════════════════════════════════
        # PASS 1 — 核心元数据精准提取
        # ════════════════════════════════════════
        pass1_system = f"""你是英国顶级租赁法律专家，专注提取 AST（Assured Shorthold Tenancy）合同中的核心元数据。
{lang_note}
请仔细阅读全文，从合同文本中精准提取以下字段。
重要：DPS/TDS/mydeposits 等押金保护计划通常出现在合同中段或附件里，请务必通读全文寻找。
输出严格的 JSON 格式（不要有任何 markdown 包裹，不要输出任何其他文字）：
{{
  "Landlord": "房东全名",
  "LandlordAgent": "房东代理/中介公司（若有，否则填 未提及）",
  "Tenant": "所有租客全名（多人用逗号分隔）",
  "Address": "出租房屋完整地址（含邮编）",
  "StartDate": "起租日期",
  "EndDate": "合同终止日期",
  "Term": "租期时长（如 12 months）",
  "RentPCM": "月租金额（如 GBP1,625 per calendar month）",
  "RentPayDay": "租金支付日（如 every month in advance / 1st of each month）",
  "RentPayMethod": "支付方式（如 standing order / bank transfer）",
  "RentAdvance": "是否要求提前多个月支付（如 6 months in advance）若无则填 按月支付",
  "Deposit": "押金金额（如 GBP1,875）",
  "DepositScheme": "押金保护计划全名（如 The Deposit Protection Service (DPS)）— 请在全文中搜索 DPS/TDS/mydeposits/deposit protection",
  "BreakClause": "解约条款详情（起效时间、提前通知期）若无则填 未提及",
  "NoticePeriod": "到期续约/终止的提前通知要求（如 2 months notice）",
  "PetsAllowed": "是否允许养宠物（明确说明 Yes/No/未提及）",
  "SmokingAllowed": "是否允许吸烟（明确说明 Yes/No/未提及）",
  "Guarantor": "是否需要担保人（Yes/No/未提及）",
  "RentPayDay": "租金支付日"
}}
如某字段合同中真的未提及，填写 "未提及"。绝对不要猜测，只提取合同中明确出现的信息。"""

        # Send full text for pass1 (metadata can be anywhere in contract)
        pass1_input = full_text[:12000] + ("\n\n[合同尾部]\n" + text_tail if text_tail else "")
        pass1_raw = call_ai(pass1_system, pass1_input)
        metadata = parse_ai_json(pass1_raw)
        if not isinstance(metadata, dict) or not metadata:
            metadata = {"RentPCM": "解析失败，请手动填写", "Address": "解析失败，请手动填写"}

        # ════════════════════════════════════════
        # PASS 2 — 逐章节深度解读
        # ════════════════════════════════════════
        clause_groups = {
            "租客义务 (Tenant Obligations)": [
                "rent payment", "utility bills", "council tax", "insurance", "repairs", "maintenance",
                "cleaning", "gardening", "alterations", "subletting", "nuisance", "decoration",
                "tenant shall", "tenant must", "tenant's obligation", "tenant agrees"
            ],
            "房东义务 (Landlord Covenants)": [
                "landlord shall", "landlord must", "landlord's obligation", "quiet enjoyment",
                "gas safety", "electrical safety", "EPC", "HMO", "landlord covenants",
                "landlord agrees", "right to enter", "notice of entry"
            ],
            "维修与保养 (Repairs & Maintenance)": [
                "repair", "maintenance", "damage", "fair wear and tear", "fixtures", "fittings",
                "appliances", "boiler", "structure", "damp", "mould", "emergency repair"
            ],
            "押金与费用 (Deposit & Fees)": [
                "deposit", "holding deposit", "dilapidation", "cleaning fee", "check-out",
                "inventory", "deduction", "deposit scheme", "protected", "adjudication",
                "administration fee", "renewal fee"
            ],
            "合同终止与续签 (Termination & Renewal)": [
                "break clause", "notice", "vacate", "surrender", "periodic tenancy",
                "rolling contract", "renewal", "end of tenancy", "holdover", "section 21",
                "section 8", "possession", "eviction"
            ],
            "入住与离开 (Check-in & Check-out)": [
                "inventory", "check-in", "check-out", "condition report", "professional clean",
                "carpet clean", "key", "meter reading", "forwarding address"
            ],
            "特殊条款与附加条件 (Special Clauses)": [
                "special condition", "additional clause", "addendum", "schedule", "rider",
                "pet clause", "smoking", "guarantor", "parental guarantee", "diplomatic clause",
                "redecoration", "garden maintenance"
            ]
        }

        all_sections = []
        # 处理头部文本
        texts_to_analyze = [("合同主体", text_head)]
        for idx, chunk in enumerate(text_middle_chunks):
            texts_to_analyze.append((f"合同中段 Part {idx+2}", chunk))
        if text_tail:
            texts_to_analyze.append(("合同尾部/特殊条款", text_tail))

        pass2_system = f"""你是英国顶级 AST 租赁合同法律分析师。
{lang_note}
请仔细阅读以下合同文本片段，识别并分析以下类别的条款。
如该片段中没有某类别的内容，请跳过（不要输出空数组项）。

输出严格 JSON 数组格式（直接输出 [ ] 开头，不要任何 markdown 包裹，不要任何其他文字）：
[
  {{
    "Heading": "类别名称（从下方列表选择）",
    "Points": [
      "月租 GBP1,625，每月提前支付 ⚠️",
      "逾期14天收取违约金 ⚠️",
      "需通过银行转账或Standing Order支付",
      "房东银行账户：Nexis Property，账号03964590"
    ],
    "RiskLevel": "HIGH"
  }}
]

规则：
- 每类别3-5条要点，每条15-40字
- 必须引用合同中的具体金额、日期、天数、条款编号
- 对租客不利或高风险要点末尾加 ⚠️
- RiskLevel 只能是 HIGH / MEDIUM / LOW
- 类别名称只能从以下选择：{', '.join(clause_groups.keys())}
- 只输出 JSON，不要解释，不要前言后语"""

        for chunk_name, chunk_text in texts_to_analyze:
            chunk_raw = call_ai(pass2_system, f"[{chunk_name}]\n\n{chunk_text}")
            # Debug: show raw response in UI
            st.caption(f"🔍 [{chunk_name}] API返回 {len(chunk_raw)} 字符，前100字: {chunk_raw[:100]}")
            chunk_result = parse_ai_json(chunk_raw)
            st.caption(f"   解析结果类型: {type(chunk_result).__name__}，项目数: {len(chunk_result) if isinstance(chunk_result, (list,dict)) else 'N/A'}")
            # parse_ai_json may return list or dict
            if isinstance(chunk_result, list):
                all_sections.extend(chunk_result)
            elif isinstance(chunk_result, dict) and chunk_result:
                all_sections.append(chunk_result)

        # 合并相同 Heading 的 sections
        # 兼容 AI 可能返回的各种字段名变体
        def extract_pts(sec):
            """从 sec 中提取要点列表，兼容多种字段名"""
            # Try all possible field name variants
            for key in ["Points", "points", "KeyPoints", "keyPoints", "key_points"]:
                v = sec.get(key, [])
                if v and isinstance(v, list): return v
            # Try Content variants -> convert to points
            for key in ["Content", "content", "Summary", "summary"]:
                v = sec.get(key, "")
                if v and isinstance(v, str) and len(v) > 10:
                    # Split by sentence endings or newlines
                    parts = re.split(r'[。\n；;]', v)
                    pts = ["• " + p.strip() for p in parts if p.strip() and len(p.strip()) > 5][:5]
                    if pts: return pts
            return []

        merged: Dict[str, Dict] = {}
        for sec in all_sections:
            # Normalise heading key
            h = sec.get("Heading") or sec.get("heading") or sec.get("Category") or "其他"
            pts = extract_pts(sec)
            # Normalise risk level
            rl = sec.get("RiskLevel") or sec.get("riskLevel") or sec.get("risk_level") or "LOW"
            rl = str(rl).upper()
            if rl not in ("HIGH","MEDIUM","LOW"): rl = "LOW"

            if h not in merged:
                merged[h] = {"Heading": h, "Points": pts, "RiskLevel": rl}
            else:
                all_pts = merged[h].get("Points", []) + pts
                seen, uniq = set(), []
                for p in all_pts:
                    key = p[:20]
                    if key not in seen:
                        seen.add(key); uniq.append(p)
                merged[h]["Points"] = uniq[:5]
                rl_order = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
                if rl_order.get(rl,0) > rl_order.get(merged[h]["RiskLevel"],0):
                    merged[h]["RiskLevel"] = rl

        final_sections = list(merged.values())

        # ════════════════════════════════════════
        # PASS 3 — 综合风险评估 + 租客行动建议
        # ════════════════════════════════════════
        pass3_system = f"""你是英国 AST 租赁合同专家和租客权益顾问。
{lang_note}
根据以下合同摘要，请生成：
1. 综合风险评估（HIGH/MEDIUM/LOW 总体评级，并给出理由）
2. 前5大风险条款（每条注明风险类型、具体条款内容、对租客的影响）
3. 租客在签约前应重点核查/谈判的条款（至少5点具体建议）
4. 入住前必做事项清单（如拍照留证、检查inventory等，至少6点）
5. 离租前必做事项清单（至少5点）
6. 一句话总结（用于快速告知客户该合同的整体情况）

输出严格 JSON 格式（不要有任何 markdown 包裹）：
{{
  "OverallRisk": "HIGH/MEDIUM/LOW",
  "OverallRiskReason": "总体评级理由（2-3句话）",
  "TopRisks": [
    {{"Title": "风险名称", "Detail": "具体风险内容", "Impact": "对租客的影响"}}
  ],
  "NegotiationPoints": ["谈判建议1", "谈判建议2", ...],
  "CheckinChecklist": ["入住前行动1", "入住前行动2", ...],
  "CheckoutChecklist": ["离租前行动1", "离租前行动2", ...],
  "OneLiner": "一句话总结"
}}"""

        meta_summary = json.dumps(metadata, ensure_ascii=False)
        sections_summary = json.dumps([{"Heading": s["Heading"], "Points": s.get("Points", s.get("Content",""))[:300] if isinstance(s.get("Points", s.get("Content","")), str) else s.get("Points",[])} for s in final_sections[:8]], ensure_ascii=False)
        pass3_input = f"元数据摘要：\n{meta_summary}\n\n章节摘要：\n{sections_summary}"
        pass3_raw = call_ai(pass3_system, pass3_input)
        risk_data = parse_ai_json(pass3_raw)
        if not risk_data:
            risk_data = {"OverallRisk": "MEDIUM", "OverallRiskReason": "解析失败，请手动评估",
                         "TopRisks": [], "NegotiationPoints": [], "CheckinChecklist": [],
                         "CheckoutChecklist": [], "OneLiner": "合同已解析，请查看各章节详情"}

        return {
            "Metadata": metadata,
            "Sections": final_sections,
            "RiskData": risk_data,
            "Risks": risk_data.get("OverallRiskReason", ""),
            "Summary": risk_data.get("OneLiner", ""),
            "lang": target_lang
        }

    except Exception as e:
        return {"error": f"提取失败: {e}"}


def create_contract_analysis_pdf(data: Dict, lang: str = "中文") -> Image.Image:
    """合同深度分析 PDF v4.3 — bullet point layout, no overflow"""

    is_cn = (lang == "中文")
    W, M  = 1200, 56
    CW    = W - M * 2        # 1088 px usable width

    # Fixed line heights — never derived from font.size
    LH_H  = 46   # section header row
    LH_BD = 36   # body / bullet line
    LH_SM = 30   # small line

    # Colours
    WH    = (255,255,255)
    DARK  = (26, 26, 34)
    GOLD  = (191,160,100)
    GLT   = (247,247,249)
    GMD   = (212,212,218)
    TXT   = (42, 42, 52)
    SUB   = (108,108,120)
    HIGH  = (205,30, 30)
    MED   = (200,98, 0)
    LOW   = (18, 148,62)
    BLUE  = (26, 58,170)
    RC    = {"HIGH":HIGH,"MEDIUM":MED,"LOW":LOW}
    RCN   = {"HIGH":"高风险","MEDIUM":"中等风险","LOW":"低风险"}
    REN   = {"HIGH":"HIGH","MEDIUM":"MED","LOW":"LOW"}

    try:
        FT = ImageFont.truetype("simhei.ttf", 40)
        FH = ImageFont.truetype("simhei.ttf", 28)
        FB = ImageFont.truetype("simhei.ttf", 23)
        FS = ImageFont.truetype("simhei.ttf", 19)
        FG = ImageFont.truetype("simhei.ttf", 16)
        FW = ImageFont.truetype("simhei.ttf", 108)
    except:
        FT=FH=FB=FS=FG=FW = ImageFont.load_default()

    _mi = Image.new("RGB",(1,1))
    _md = ImageDraw.Draw(_mi)

    def san(t):
        if not t or not isinstance(t,str): return ""
        for a,b in [("£","GBP"),("\u2013","-"),("\u2014","-"),
                    ("\u2018","'"),("\u2019","'"),("\u201c",'"'),("\u201d",'"'),
                    ("⚠️","[!]"),("⚠","[!]"),("✓","OK"),("✗","X"),
                    ("①","1."),("②","2."),("③","3."),("④","4."),("⑤","5.")]:
            t=t.replace(a,b)
        # Remove any remaining emoji / non-BMP characters (keep ASCII + CJK)
        return "".join(c for c in t if ord(c) < 0x3000 or 0x4E00 <= ord(c) <= 0x9FFF)

    def px(txt, font):
        try:    return int(_md.textlength(san(txt), font=font))
        except: return len(txt)*getattr(font,"size",12)

    def fit(val, font, max_w):
        """Truncate to max_w px, appending … if cut. Falls back to char count if font measurement fails."""
        s = san(str(val))
        try:
            if px(s, font) <= max_w: return s
            while s and px(s+"…", font) > max_w: s=s[:-1]
            return s+"…"
        except:
            # Fallback: estimate ~14px per character for 24px font
            est_chars = max_w // 14
            if len(s) <= est_chars: return s
            return s[:est_chars-1] + "…"

    def wrap(text, font, max_w):
        """Split text into lines that fit max_w."""
        text=san(text)
        if not text: return []
        out,cur=[],""
        for ch in text:
            if px(cur+ch, font) <= max_w: cur+=ch
            else:
                if cur: out.append(cur)
                cur=ch
        if cur: out.append(cur)
        return out

    def draw_lines(drw, text, x, y, font, max_w, fill, lh, max_n=99):
        """Draw wrapped text. Returns y after last line."""
        for ln in wrap(text,font,max_w)[:max_n]:
            drw.text((x,y), ln, font=font, fill=fill)
            y+=lh
        return y

    def lines_h(text, font, max_w, lh, max_n=99):
        return min(len(wrap(text,font,max_w)), max_n)*lh

    # ── Unpack ──
    meta     = data.get("Metadata",{})
    sections = data.get("Sections",[])
    rd       = data.get("RiskData",{})
    overall  = rd.get("OverallRisk","MEDIUM")
    top_r    = rd.get("TopRisks",[])[:5]
    neg      = rd.get("NegotiationPoints",[])[:5]
    ci       = rd.get("CheckinChecklist",[])[:5]
    co       = rd.get("CheckoutChecklist",[])[:5]
    liner    = san(rd.get("OneLiner",data.get("Summary","")))
    rc       = RC.get(overall,MED)
    rl       = (RCN if is_cn else REN).get(overall,overall)

    # ── Height estimate ──
    est = 260
    est += lines_h(liner,FB,CW-52,LH_BD)+32 if liner else 0
    est += 60 + 5*96 + 36        # meta grid
    est += 110                    # risk bar
    est += 66                     # section header
    for s in sections:
        pts = s.get("Points", [])
        # legacy fallback
        if not pts:
            raw = san(s.get("Content",""))
            pts = ["• "+x.strip() for x in raw.split("。") if x.strip()][:5]
        est += LH_H + len(pts)*LH_BD + 20
    if top_r:
        est += 66+len(top_r)*(LH_H+LH_SM*2+18)
    est += 66+len(neg)*(LH_BD+4)
    est += 66+max(len(ci),len(co),1)*(LH_BD+6)
    est += 220

    canvas = Image.new("RGB",(W, est+300), WH)
    draw   = ImageDraw.Draw(canvas)
    y = 0

    # ══ 1. BANNER ══
    draw.rectangle([(0,0),(W,182)], fill=DARK)
    draw.text((M,22), "合同深度分析报告" if is_cn else "AST Contract Analysis", font=FT, fill=GOLD)
    draw.text((M,80), "Hao Harbour Intelligence · AI-Powered Analysis", font=FS, fill=(160,160,175))
    draw.rounded_rectangle([(W-204,28),(W-M,152)], radius=11, fill=rc)
    draw.text((W-190,40), "整体风险" if is_cn else "Overall Risk", font=FS, fill=WH)
    draw.text((W-190,70), rl, font=FH, fill=WH)
    y = 196

    # ══ 2. ONE-LINER ══
    if liner:
        bh = lines_h(liner,FB,CW-52,LH_BD)+28
        draw.rounded_rectangle([(M,y),(W-M,y+bh)], radius=8, fill=(236,248,236))
        draw.text((M+12,y+10),"💡",font=FB,fill=(26,116,46))
        y = draw_lines(draw,liner,M+44,y+10,FB,CW-56,(26,110,46),LH_BD)
        y += 18

    # ══ 3. META GRID — 3 cols ══
    # 3 equal cells that fit exactly within margins
    GAP     = 8
    CELL_W  = (CW - GAP * 2) // 3          # floor division → 357 px
    VAL_W   = CELL_W - 26                  # text safe zone inside cell
    COL_X   = [M, M + CELL_W + GAP, M + (CELL_W + GAP) * 2]
    # Verify third column right edge never exceeds W-M
    assert COL_X[2] + CELL_W <= W - M + 2  # +2 for rounding tolerance

    draw.rectangle([(M,y),(W-M,y+44)], fill=GOLD)
    draw.text((M+14,y+9), "【核心条款】" if is_cn else "[ Key Terms ]", font=FH, fill=WH)
    y += 54

    META=[
        ("房东"    if is_cn else "Landlord",       meta.get("Landlord","—")),
        ("租客"    if is_cn else "Tenant",          meta.get("Tenant","—")),
        ("地址"    if is_cn else "Address",         meta.get("Address","—")),
        ("月租"    if is_cn else "Rent PCM",        meta.get("RentPCM","—")),
        ("押金"    if is_cn else "Deposit",         meta.get("Deposit","—")),
        ("押金保护" if is_cn else "Deposit Scheme", meta.get("DepositScheme","—")),
        ("起租"    if is_cn else "Start Date",      meta.get("StartDate","—")),
        ("到期"    if is_cn else "End Date",        meta.get("EndDate","—")),
        ("租期"    if is_cn else "Term",            meta.get("Term","—")),
        ("解约条款" if is_cn else "Break Clause",   meta.get("BreakClause","—")),
        ("提前通知" if is_cn else "Notice Period",  meta.get("NoticePeriod","—")),
        ("担保人"  if is_cn else "Guarantor",       meta.get("Guarantor","—")),
        ("宠物"    if is_cn else "Pets",            meta.get("PetsAllowed","—")),
        ("吸烟"    if is_cn else "Smoking",         meta.get("SmokingAllowed","—")),
        ("付租日"  if is_cn else "Pay Day",         meta.get("RentPayDay","—")),
    ]
    ROW_H = 110  # taller to allow 2-line values
    for idx,(lbl,val) in enumerate(META):
        cx = COL_X[idx%3]
        cy = y+(idx//3)*ROW_H
        draw.rounded_rectangle([(cx,cy),(cx+CELL_W,cy+102)],
                                 radius=7, fill=GLT, outline=GMD)
        draw.text((cx+10,cy+8), san(lbl), font=FG, fill=SUB)
        # Wrap value to max 2 lines — NO truncation, text wraps cleanly
        val_lines = wrap(san(str(val)), FB, VAL_W)[:2]
        for li, vl in enumerate(val_lines):
            draw.text((cx+10, cy+32+li*LH_BD), vl, font=FB, fill=TXT)

    y += ((len(META)+2)//3)*ROW_H + 28

    # ══ 4. RISK REASON ══
    reason = san(rd.get("OverallRiskReason",""))
    if reason:
        r_lines = wrap(reason,FS,CW-28)[:2]
        bh = LH_H + len(r_lines)*LH_SM + 18
        draw.rounded_rectangle([(M,y),(W-M,y+bh)], radius=8, fill=GLT, outline=rc)
        draw.text((M+14,y+8), ("整体风险：" if is_cn else "Risk: ")+rl, font=FH, fill=rc)
        cy2 = y+LH_H+4
        for ln in r_lines:
            draw.text((M+14,cy2), ln, font=FS, fill=TXT); cy2+=LH_SM
        y = cy2+16

    # ══ 5. SECTIONS — bullet points ══
    draw.rectangle([(M,y),(W-M,y+44)], fill=BLUE)
    draw.text((M+14,y+9), "【逐章节解读】" if is_cn else "[ Clause Analysis ]", font=FH, fill=WH)
    y += 58

    for sec in sections:
        heading  = san(sec.get("Heading",""))
        pts      = sec.get("Points",[])
        sec_risk = sec.get("RiskLevel","LOW")

        # legacy fallback: Content → Points
        if not pts:
            raw = san(sec.get("Content",""))
            pts = ["• "+x.strip() for x in raw.split("。") if x.strip()][:5]
        if not pts: continue

        sc  = RC.get(sec_risk,LOW)
        srl = (RCN if is_cn else REN).get(sec_risk,sec_risk)

        # heading row
        draw.rectangle([(M,y),(M+5,y+36)], fill=sc)
        draw.text((M+14,y+5), heading, font=FH, fill=BLUE)
        pill_w = px(srl,FG)+20
        px0    = W-M-pill_w
        draw.rounded_rectangle([(px0,y+4),(W-M,y+32)], radius=7, fill=sc)
        draw.text((px0+7,y+7), srl, font=FG, fill=WH)
        y += LH_H

        # bullet points — each point on its own line(s)
        for pt in pts[:5]:
            pt_clean = san(str(pt)).strip()
            # Strip any leading bullet/dash chars
            if pt_clean.startswith(("• ","- ","* ","· ")):
                pt_clean = pt_clean[2:]
            elif pt_clean.startswith(("•","·")):
                pt_clean = pt_clean[1:].strip()
            # Draw marker (simhei-safe)
            draw.text((M+14, y), ">>", font=FG, fill=GOLD)
            # Draw text
            y = draw_lines(draw, pt_clean, M+44, y, FB, CW-54, TXT, LH_BD, 2)

        draw.line([(M+6,y+6),(W-M-6,y+6)], fill=GMD, width=1)
        y += 18

    # ══ 6. TOP RISKS ══
    if top_r:
        y+=8
        draw.rectangle([(M,y),(W-M,y+44)], fill=HIGH)
        draw.text((M+14,y+9), "【前5大风险】" if is_cn else "[ Top Risks ]", font=FH, fill=WH)
        y+=56
        for idx,risk in enumerate(top_r):
            title  = fit(risk.get("Title",""), FH, CW-55)
            detail = san(risk.get("Detail",""))
            d_lines= wrap(detail,FS,CW-55)[:2]
            draw.ellipse([(M,y+2),(M+26,y+28)], fill=HIGH)
            draw.text((M+7,y+4), str(idx+1), font=FS, fill=WH)
            draw.text((M+36,y+4), title, font=FH, fill=HIGH)
            y+=LH_H
            for ln in d_lines:
                draw.text((M+36,y), ln, font=FS, fill=TXT); y+=LH_SM
            y+=12

    # ══ 7. NEGOTIATION ══
    if neg:
        y+=8
        draw.rectangle([(M,y),(W-M,y+44)], fill=BLUE)
        draw.text((M+14,y+9), "【签约前要点】" if is_cn else "[ Before Signing ]", font=FH, fill=WH)
        y+=56
        for pt in neg:
            draw.text((M+10,y), ">>", font=FG, fill=GOLD)
            y=draw_lines(draw, san(str(pt))[:120], M+34,y, FB,CW-44, TXT,LH_BD, 2)
            y+=4

    # ══ 8. CHECKLISTS ══
    if ci or co:
        y+=10
        draw.rectangle([(M,y),(W-M,y+44)], fill=LOW)
        draw.text((M+14,y+9), "【行动清单】" if is_cn else "[ Action Checklists ]", font=FH, fill=WH)
        y+=56
        HW   = (CW-14)//2
        xl,xr= M, M+HW+14
        IW   = HW-36      # text width inside each column
        draw.text((xl,y), "入住前" if is_cn else "Move-In",  font=FH, fill=LOW)
        draw.text((xr,y), "离租前" if is_cn else "Move-Out", font=FH, fill=MED)
        y+=LH_H
        for i in range(max(len(ci),len(co))):
            row_y = y
            left_h = right_h = LH_BD  # default single-line height
            if i<len(ci):
                draw.text((xl,row_y),"[ ]",font=FB,fill=LOW)
                ci_lines = wrap(san(ci[i]), FB, IW)[:2]
                for li, ln in enumerate(ci_lines):
                    draw.text((xl+36, row_y+li*LH_BD), ln, font=FB, fill=TXT)
                left_h = len(ci_lines)*LH_BD
            if i<len(co):
                draw.text((xr,row_y),"[ ]",font=FB,fill=MED)
                co_lines = wrap(san(co[i]), FB, IW)[:2]
                for li, ln in enumerate(co_lines):
                    draw.text((xr+36, row_y+li*LH_BD), ln, font=FB, fill=TXT)
                right_h = len(co_lines)*LH_BD
            y += max(left_h, right_h) + 8

    # ══ 9. WATERMARK ══
    wml=Image.new("RGBA",canvas.size,(0,0,0,0))
    wmd=ImageDraw.Draw(wml)
    for wy in range(0, canvas.size[1], 800):
        wmd.text((120,wy+290),"Hao Harbour",font=FW,fill=(192,192,192,42))
    rot=wml.rotate(30,expand=False)
    canvas.paste(rot,(0,0),rot)

    # ══ 10. FOOTER ══
    y+=50
    draw.rectangle([(0,y),(W,y+168)], fill=(234,234,242))
    disc=("本报告仅供参考，不构成法律建议。请在签约前咨询专业英国执业律师。Hao Harbour 不承担法律责任。"
          if is_cn else
          "AI-assisted, for reference only. Not legal advice. Consult a UK solicitor. Hao Harbour accepts no liability.")
    draw_lines(draw,disc,M,y+16,FS,CW,(124,124,138),LH_SM)
    import datetime as _dt
    draw.text((M,y+136),
              f"Hao Harbour Intelligence · {_dt.datetime.now().strftime('%Y-%m-%d')}",
              font=FG, fill=(160,160,174))

    return canvas.crop((0,0,W,int(y+168)))




# --- 初始化带看报告状态 ---
if 'viewing_items' not in st.session_state:
    st.session_state['viewing_items'] = {
        'Interior': {item: 5 for item in VIEWING_DEFAULT_INTERIOR},
        'Building': {item: 5 for item in VIEWING_DEFAULT_BUILDING},
        'Neighborhood': {item: 5 for item in VIEWING_DEFAULT_NEIGHBORHOOD}
    }
    st.session_state['viewing_remarks'] = {'Interior': '', 'Building': '', 'Neighborhood': '', 'General': ''}
    st.session_state['viewing_photos'] = []

ws = get_ws()
if ws:
    t1, t2, t3, t5, t7 = st.tabs([
        "✨ 发布新房源", "⚙️ 管理与统计", "🚀 批量发送引擎",
        "👁️ 带看小结", "🧰 工具箱"
    ])
    
    with t1:
        st.subheader("1. 基础信息")
        
        # --- Rightmove 读取模块 ---
        rm_url = st.text_input("🔗 自动读取 Rightmove 链接 (选填，自动填入房源信息及图片)")
        if st.button("🔍 一键读取 Rightmove"):
            if rm_url:
                with st.spinner("正在抓取 Rightmove 数据，请稍候..."):
                    data, err = scrape_rightmove(rm_url)
                    if err:
                        st.error(err)
                    else:
                        st.session_state['rm_data'] = data
                        st.success("✅ 读取成功！请复核下方自动填充的信息。")
            else:
                st.warning("请输入 Rightmove 链接")
        
        rm_data = st.session_state.get('rm_data', {})
        
        c1, c2, c3, c4 = st.columns(4)
        p_name = c1.text_input("房源名称", value=rm_data.get('title', ''))
        p_price = c2.number_input("月租 (£)", min_value=0, value=rm_data.get('price', 0))
        reg_opts = ["中伦敦", "东伦敦", "西伦敦", "北伦敦", "南伦敦"]
        auto_reg = rm_data.get('region', '中伦敦')
        auto_reg_idx = reg_opts.index(auto_reg) if auto_reg in reg_opts else 0
        detected_pc = rm_data.get('postcode', '')
        reg_label = f"区域 {'🎯 已自动识别 ' + detected_pc if detected_pc else '(可手动修改)'}"
        p_reg = c3.selectbox(reg_label, reg_opts, index=auto_reg_idx)
        
        rooms_opts = ["Studio", "1房", "2房", "3房", "4房+"]
        default_room = rm_data.get('rooms', '')
        idx_room = rooms_opts.index(default_room) if default_room in rooms_opts else 0
        p_rooms = c4.selectbox("户型", rooms_opts, index=idx_room)
        
        en_desc = st.text_area("英文原始描述", value=rm_data.get('description', ''))
        if st.button("🪄 AI 生成中文文案"):
            st.session_state['zh_content'] = call_smart_ai(en_desc)
        
        zh_desc = st.text_area("最终展示描述", value=st.session_state.get('zh_content', ''), height=150)
        up_imgs = st.file_uploader("上传房源图 (建议8张, 将覆盖自动抓取的图片)", accept_multiple_files=True)
        
        # 准备合并图片来源
        files_to_use = up_imgs
        rm_image_urls = rm_data.get('images', [])
        
        if not files_to_use and rm_image_urls:
            files_to_use = []
            for img_url in rm_image_urls:
                try:
                    r_img = requests.get(img_url, timeout=10)
                    if r_img.status_code == 200:
                        files_to_use.append(BytesIO(r_img.content))
                except:
                    pass
        
        if files_to_use:
            # 修改点：传入了 p_reg 区域和 8图排版
            preview_img = create_poster(files_to_use, p_name, p_price, p_rooms, p_reg)
            if preview_img:
                st.image(preview_img, caption="双水印强化海报预览", width=450)
                
                if st.button("🚀 立即发布"):
                    with st.spinner("同步云端中..."):
                        buf = BytesIO()
                        preview_img.save(buf, format="JPEG", quality=95)
                        upload_res = cloudinary.uploader.upload(buf.getvalue())
                        img_url = upload_res['secure_url']
                        
                        now = datetime.now().strftime("%Y-%m-%d")
                        p_station = rm_data.get('station', '')
                        p_lat = rm_data.get('lat', '')
                        p_lng = rm_data.get('lng', '')
                        # Index 10 is reserved for manual walkingMinutes to ensure backward compatibility
                        try:
                            ws.append_row([now, p_name, p_reg, p_rooms, int(p_price), img_url, zh_desc, 0, 0, p_station, "", p_lat, p_lng])
                            st.success("发布成功！海报已存档。")
                            st.rerun()
                        except Exception as e:
                            st.error(f"⚠️ 发布失败，Google Sheets 写入出错：{e}")

    with t2:
        try:
            data = get_all_records_safe(ws)
        except Exception as e:
            st.error(f"⚠️ Google Sheets 读取失败，请检查服务账号权限或网络连接。\n\n错误详情：{e}")
            data = []
        if data:
            df = pd.DataFrame(data)
            
            # --- 增加大盘 (Executive Dashboard) ---
            st.markdown("### 📊 排行榜与数据引擎 (Executive Dashboard)")
            metric_cols = st.columns(3)
            metric_cols[0].metric("累计访问量", int(pd.to_numeric(df['views'], errors='coerce').sum()))
            metric_cols[1].metric("在租房源数", len(df))
            metric_cols[2].metric("精选置顶数", len(df[df.get('is_featured', 0) == 1]))
            
            # 图表
            c_d1, c_d2 = st.columns(2)
            with c_d1:
                st.markdown("**各区域热度分布**")
                reg_views = df.groupby('region')['views'].sum().reset_index()
                st.bar_chart(reg_views.set_index('region'))
            with c_d2:
                st.markdown("**最受关注户型**")
                room_views = df.groupby('rooms')['views'].sum().reset_index()
                st.bar_chart(room_views.set_index('rooms'))
            
            st.markdown("---")
            search = st.text_input("🔍 快速搜索房源...").lower()
            f_df = df[df['title'].astype(str).str.lower().str.contains(search)] if search else df
            
            for i, row in f_df.iterrows():
                idx = i + 2
                with st.expander(f"{row['title']} (浏览: {row.get('views',0)})"):
                    with st.form(f"edit_{idx}"):
                        ca, cb, cc, cd = st.columns(4)
                        nt = ca.text_input("标题", row['title'])
                        np = cb.number_input("价格", value=int(float(row['price'] or 0)))
                        nr = cc.selectbox("区域", ["中伦敦", "东伦敦", "西伦敦", "北伦敦", "南伦敦"], index=["中伦敦", "东伦敦", "西伦敦", "北伦敦", "南伦敦"].index(row['region']) if row['region'] in ["中伦敦", "东伦敦", "西伦敦", "北伦敦", "南伦敦"] else 0)
                        nrm_opts = ["Studio", "1房", "2房", "3房", "4房+"]
                        nrm = cd.selectbox("户型", nrm_opts, index=nrm_opts.index(row['rooms']) if row['rooms'] in nrm_opts else 0)
                        nd = st.text_area("文案", value=row['description'], height=100)
                        isf = st.checkbox("精选置顶", value=bool(row.get('is_featured', 0)))
                        
                        s1, s2 = st.columns(2)
                        if s1.form_submit_button("保存"):
                            try:
                                ws.update(f"A{idx}:I{idx}", [[row['date'], nt, nr, nrm, np, row['poster-link'], nd, row['views'], 1 if isf else 0]])
                                st.rerun()
                            except Exception as e:
                                st.error(f"⚠️ 保存失败，请检查 Google Sheets 权限：{e}")
                        if s2.form_submit_button("删除"):
                            try:
                                ws.delete_rows(idx)
                                st.rerun()
                            except Exception as e:
                                st.error(f"⚠️ 删除失败，请检查 Google Sheets 权限：{e}")
                    
                    # --- Multi-version Copywriting ---
                    st.markdown("💬 **一键私域营销话术**")
                    moments_txt = f"🌟【{row['region']} VIP新盘首发】\n🏢 {row['title']}\n🛏️ {row['rooms']} | 💰 {row['price']}/月\n\n稀缺奢华好房，带有专属设施服务。\n欢迎私信获取完整高清相册及看房名额！"
                    dm_txt = f"哈喽～给您推荐一套在{row['region']}的【{row['title']}】！\n这个是{row['rooms']}，目前租金是 {row['price']}/月。性价比非常高！\n您看下主页这个房源的海报跟详情，如果感兴趣咱们可以随时安排看房哦！"
                    c_m1, c_m2 = st.columns(2)
                    c_m1.text_area("朋友圈高冷名片版", value=moments_txt, height=130, key=f"mom_{idx}")
                    c_m2.text_area("微信亲和私聊版", value=dm_txt, height=130, key=f"dm_{idx}")

    with t3:
        st.subheader("🚀 批量印钞机 (Bulk Scraper Engine)")
        st.info("💡 批量粘贴 Rightmove 链接，去泡杯咖啡，系统会为您自动抓取图片、排版海报上云、AI写文案，并在后台静默发房！区域将自动根据邮编识别，无需手动指定。")
        bulk_urls = st.text_area("输入 Rightmove 链接 (每行一个)", height=200, placeholder="https://www.rightmove.co.uk/properties/12345...\nhttps://www.rightmove.co.uk/properties/67890...")
        
        b_c1, b_c2 = st.columns(2)
        bulk_reg = b_c1.selectbox("兜底默认区域 (邮编识别失败时使用)", ["中伦敦", "东伦敦", "西伦敦", "北伦敦", "南伦敦"])
        bulk_room_opts = ["Studio", "1房", "2房", "3房", "4房+"]
        bulk_room = b_c2.selectbox("降级默认户型 (抓取不到时的回退值)", bulk_room_opts, index=0)
        
        if st.button("⚡ 开始批量全自动处理 (Start Bulk Process)", type="primary"):
            urls = [u.strip() for u in bulk_urls.split('\n') if u.strip().startswith('http')]
            if not urls:
                st.warning("您还没有输入任何链接哦！")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                success_count = 0
                
                for i, url in enumerate(urls):
                    status_text.text(f"正在处理 ({i+1}/{len(urls)}): {url}")
                    scraped_data, err = scrape_rightmove(url)
                    if err:
                        st.warning(f"⚠️ 跳过 [{i+1}]：抓取失败 — {err}")
                        progress_bar.progress((i + 1) / len(urls))
                        continue
                    if not isinstance(scraped_data, dict):
                        st.warning(f"⚠️ 跳过 [{i+1}]：解析数据失败，请检查链接是否为有效房源页")
                        progress_bar.progress((i + 1) / len(urls))
                        continue
                    # 下载图片
                    files_to_use = []
                    img_list: Any = scraped_data.get('images', [])
                    if isinstance(img_list, list):
                        for img_url in img_list:
                            try:
                                r_img = requests.get(str(img_url), timeout=10)
                                if r_img.status_code == 200:
                                    files_to_use.append(BytesIO(r_img.content))
                            except: pass
                    
                    if not files_to_use:
                        st.warning(f"⚠️ 跳过 [{i+1}]：该房源没有可用图片")
                        progress_bar.progress((i + 1) / len(urls))
                        continue
                    
                    rooms_val: str = str(scraped_data.get('rooms', bulk_room))
                    if rooms_val not in bulk_room_opts: rooms_val = bulk_room
                    # 智能分区：优先用邮编自动识别的区域，失败时才用兜底默认值
                    auto_region_bulk: str = str(scraped_data.get('region', bulk_reg))
                    detected_pc_bulk: str = str(scraped_data.get('postcode', ''))
                    final_reg: str = auto_region_bulk if auto_region_bulk in ["中伦敦", "东伦敦", "西伦敦", "北伦敦", "南伦敦"] else bulk_reg
                    pc_hint = f" [{detected_pc_bulk} → {final_reg}]" if detected_pc_bulk else f" [→ {final_reg}]"
                    status_text.text(f"正在处理 ({i+1}/{len(urls)}){pc_hint}: {url}")
                    # 生成海报
                    p_title: str = str(scraped_data.get('title', ''))
                    p_price: int = int(scraped_data.get('price', 0))
                    p_poster = create_poster(files_to_use, p_title, p_price, rooms_val, final_reg)
                    if p_poster:
                        try:
                            buf = BytesIO()
                            p_poster.save(buf, format="JPEG", quality=90)
                            up_res = cloudinary.uploader.upload(buf.getvalue()) # type: ignore
                            img_url_cloud = up_res['secure_url']
                            # AI 文案
                            desc_val = scraped_data.get('description', '')
                            desc_str: str = str(desc_val)
                            p_station = str(scraped_data.get('station', ''))
                            p_lat = str(scraped_data.get('lat', ''))
                            p_lng = str(scraped_data.get('lng', ''))
                            ai_copy = call_smart_ai(desc_str[:1000]) if desc_str else "最新豪宅首发，欢迎详询！"
                            # 写入数据库
                            current_date = datetime.now().strftime("%Y-%m-%d")
                            ws.append_row([current_date, p_title, final_reg, rooms_val, p_price, img_url_cloud, ai_copy, 0, 0, p_station, "", p_lat, p_lng]) # type: ignore
                            success_count = success_count + 1
                            st.success(f"✅ [{i+1}] {p_title} ({final_reg}) 发布成功！")
                        except Exception as e:
                            st.error(f"❌ [{i+1}] 上传出错: {e}")
                    else:
                        st.warning(f"⚠️ 跳过 [{i+1}]：海报渲染失败")
                    
                    progress_bar.progress((i + 1) / len(urls))
                
                status_text.success(f"🎉 全部完成！成功录入 {success_count} / {len(urls)} 套。去客户端看看吧！")

    # =====================================================================
    # TAB 4 — 🌐 多平台内容包
    with t5:
        st.subheader("👁️ 专业带看报告生成器 (Pro Viewing Report)")
        st.info("填写深度测评信息，生成带星级评分的结构化报告及专业 PDF。")

        # 1. 基础信息
        st.markdown("#### 1️⃣ 基本信息")
        vs_c1, vs_c2 = st.columns(2)
        vs_client = vs_c1.text_input("👤 客户姓名", placeholder="例：王女士", key="vr_client")
        vs_date = vs_c2.date_input("📅 看房日期", value=datetime.today(), key="vr_date")
        
        vs_addr = st.text_input("🏠 房子地址", placeholder="例：Canary Wharf, E14", key="vr_addr")
        vs_facing = st.text_input("🧭 房屋朝向", placeholder="例：坐北朝南 (South Facing)", key="vr_facing")
        
        st.write(f"📌 **固定展示联系方式**: 🟢 WeChat: {VIEWING_CONTACT_WECHAT} | 📞 Contact: {VIEWING_CONTACT_PHONE}")

        st.markdown("---")

        # 2. 三大核心评估板块
        st.markdown("#### 2️⃣ 核心评估板块 (1-5 星评分)")
        
        sections = {
            'Interior': '🏠 室内深度评估 (Interior)',
            'Building': '🏢 大楼管理评估 (Building)',
            'Neighborhood': '🌳 周边微环境 (Neighborhood)'
        }
        
        for section_key, section_label in sections.items():
            with st.expander(section_label, expanded=True):
                # 动态增减项目
                cols = st.columns([4, 3, 1])
                cols[0].markdown("**项目名称**")
                cols[1].markdown("**评分 (1-5 星)**")
                
                # 获取当前板块的项目
                current_items = list(st.session_state['viewing_items'][section_key].items())
                
                for item_name, score in current_items:
                    r1, r2, r3 = st.columns([4, 3, 1])
                    r1.text(item_name)
                    # 星级评分选择器
                    new_score = r2.select_slider(
                        f"Rating for {item_name}",
                        options=[1, 2, 3, 4, 5],
                        value=score,
                        format_func=lambda x: "⭐" * x,
                        key=f"score_{section_key}_{item_name}",
                        label_visibility="collapsed"
                    )
                    st.session_state['viewing_items'][section_key][item_name] = new_score
                    
                    if r3.button("🗑️", key=f"del_{section_key}_{item_name}"):
                        del st.session_state['viewing_items'][section_key][item_name]
                        st.rerun()
                
                # 添加新项目
                with st.container():
                    a1, a2 = st.columns([5, 1])
                    new_item_name = a1.text_input(f"添加新项目到 {section_key}", key=f"add_input_{section_key}", label_visibility="collapsed", placeholder="输入项目名称...")
                    if a2.button("➕", key=f"add_btn_{section_key}"):
                        if new_item_name:
                            st.session_state['viewing_items'][section_key][new_item_name] = 5
                            st.rerun()
                
                st.session_state['viewing_remarks'][section_key] = st.text_area(f"【{section_key}】额外备注", value=st.session_state['viewing_remarks'][section_key], placeholder="输入该板块的补充说明...", key=f"rem_{section_key}")

        st.markdown("---")
        
        # 3. 照片管理
        st.markdown("#### 3️⃣ 现场照片管理")
        uploaded_photos = st.file_uploader("上传现场照片 (支持多选)", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
        if uploaded_photos:
            # 将新上传的照片合并（避免重复）
            for up in uploaded_photos:
                if up not in st.session_state['viewing_photos']:
                    st.session_state['viewing_photos'].append(up)

        if st.session_state['viewing_photos']:
            st.write("📸 已上传照片预览:")
            pcols = st.columns(4)
            for i, p in enumerate(st.session_state['viewing_photos']):
                with pcols[i % 4]:
                    st.image(p, use_container_width=True)
                    if st.button("删除", key=f"del_photo_{i}"):
                        st.session_state['viewing_photos'].pop(i)
                        st.rerun()

        st.markdown("---")
        
        # 4. 总体评价与生成
        st.markdown("#### 4️⃣ 总体评价 & 导出报告")
        st.session_state['viewing_remarks']['General'] = st.text_area("✍️ 总体评价 (General Remarks)", value=st.session_state['viewing_remarks']['General'], height=100)
        
        st.warning(f"📄 **免责声明将自动包含在报告中**:\n{VIEWING_DISCLAIMER}")

        c_g1, c_g2 = st.columns(2)
        if c_g1.button("📝 生成带看小结 (文字版)", type="primary", use_container_width=True):
            if not vs_client or not vs_addr:
                st.error("请至少填写客户姓名和地址")
            else:
                summary_text = gen_pro_viewing_summary(
                    vs_client, str(vs_date), vs_addr, vs_facing,
                    st.session_state['viewing_items'],
                    st.session_state['viewing_remarks']
                )
                st.session_state['vr_summary_output'] = summary_text

        if c_g2.button("🎨 生成专业 PDF 报告", use_container_width=True):
            if not vs_client or not vs_addr:
                st.error("请至少填写客户姓名和地址")
            else:
                with st.spinner("正在排版并生成 PDF..."):
                    pdf_canvas = create_viewing_report_pdf(
                        vs_client, str(vs_date), vs_addr, vs_facing,
                        st.session_state['viewing_items'],
                        st.session_state['viewing_remarks'],
                        st.session_state['viewing_photos']
                    )
                    st.session_state['vr_pdf_output'] = pdf_canvas

        if 'vr_summary_output' in st.session_state:
            st.markdown("### 📄 文字版小结")
            st.text_area("复制发给客户:", value=st.session_state['vr_summary_output'], height=400)
        
        if 'vr_pdf_output' in st.session_state:
            st.markdown("### 🖼️ PDF 报告预览")
            st.image(st.session_state['vr_pdf_output'], caption="这就是最终生成的 PDF 布局预览", use_container_width=True)
            
            # 提供下载
            buf_pdf = BytesIO()
            st.session_state['vr_pdf_output'].save(buf_pdf, format="PDF", resolution=100.0)
            st.download_button(
                "⬇️ 立即下载 PDF 报告",
                data=buf_pdf.getvalue(),
                file_name=f"Viewing_Report_{vs_client}_{vs_date}.pdf",
                mime="application/pdf"
            )

    # =====================================================================
    # TAB 7 — 🧰 工具箱（合同深度分析 v4.0 + 爆款关键词）
    # =====================================================================
    with t7:
        st.subheader("🧰 让效率翻倍的工具箱")

        tc1, tc2 = st.columns([3, 2])

        with tc1:
            st.markdown("#### 📄 AST 合同深度分析 v4.0")
            st.info("上传 PDF 合同，AI 将通过三轮分析：① 精准提取元数据 ② 逐章节深度解读 ③ 综合风险评估 + 行动建议")
            contract_file = st.file_uploader("点击上传 PDF 合同", type="pdf")
            v3_lang = st.radio("报告语言", ["中文", "English"], horizontal=True)

            if st.button("🧠 开始深度解析 (约90-120秒)", type="primary", use_container_width=True):
                if contract_file:
                    progress = st.progress(0, text="Pass 1/3：提取核心元数据...")
                    with st.spinner("AI 正在三段式深度分析合同，请耐心等待..."):
                        res = extract_contract_pro(contract_file, target_lang=v3_lang)
                    progress.progress(100, text="分析完成！")
                    if "error" in res:
                        st.error(res["error"])
                    else:
                        st.session_state['contract_v4'] = res
                        st.session_state['contract_v4_lang'] = v3_lang
                        st.success("✅ 深度分析完成！请查看下方结果。")
                else:
                    st.warning("请先上传 PDF 合同文件")

            if 'contract_v4' in st.session_state:
                v4 = st.session_state['contract_v4']
                v4_lang = st.session_state.get('contract_v4_lang', '中文')
                is_cn = (v4_lang == "中文")
                meta      = v4.get('Metadata', {})
                sections  = v4.get('Sections', [])
                risk_data = v4.get('RiskData', {})

                st.markdown("---")

                # ── 整体风险评级 ──
                overall = risk_data.get('OverallRisk', 'MEDIUM')
                risk_color = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(overall, "🟡")
                risk_label_cn = {"HIGH": "高风险", "MEDIUM": "中等风险", "LOW": "低风险"}.get(overall, overall)
                st.markdown(f"### {risk_color} 整体风险评级：**{risk_label_cn if is_cn else overall}**")
                if risk_data.get('OverallRiskReason'):
                    st.info(risk_data['OverallRiskReason'])
                if risk_data.get('OneLiner'):
                    st.success(f"💡 **一句话总结：** {risk_data['OneLiner']}")

                st.markdown("---")

                # ── 核心元数据 ──
                with st.expander("📌 核心条款速览（可编辑）", expanded=True):
                    META_DISPLAY = [
                        ("房东 Landlord",          "Landlord"),
                        ("房东代理 Agent",          "LandlordAgent"),
                        ("租客 Tenant",             "Tenant"),
                        ("房屋地址 Address",         "Address"),
                        ("月租 Rent PCM",           "RentPCM"),
                        ("押金 Deposit",            "Deposit"),
                        ("押金保护 Deposit Scheme",  "DepositScheme"),
                        ("起租日期 Start Date",      "StartDate"),
                        ("终止日期 End Date",        "EndDate"),
                        ("租期 Term",               "Term"),
                        ("租金支付日 Pay Day",       "RentPayDay"),
                        ("支付方式 Pay Method",      "RentPayMethod"),
                        ("解约条款 Break Clause",    "BreakClause"),
                        ("提前通知期 Notice Period", "NoticePeriod"),
                        ("是否需担保人 Guarantor",   "Guarantor"),
                        ("养宠物 Pets",              "PetsAllowed"),
                        ("吸烟 Smoking",             "SmokingAllowed"),
                    ]
                    cols_meta = st.columns(2)
                    for idx, (label, key) in enumerate(META_DISPLAY):
                        with cols_meta[idx % 2]:
                            meta[key] = st.text_input(label, value=meta.get(key, ""), key=f"meta_{key}")

                # ── 章节深度解读 ──
                with st.expander("📖 逐章节深度解读（可编辑）", expanded=True):
                    st.caption("AI 已将合同分章节分析，每节均注明风险等级与关键要点。")
                    new_sections = []
                    for i, sec in enumerate(sections):
                        sec_risk = sec.get('RiskLevel', 'LOW')
                        emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(sec_risk, "🟢")
                        # Get points — support both Points and legacy Content/KeyPoints
                        pts = sec.get('Points', [])
                        if not pts:
                            pts = sec.get('KeyPoints', [])
                        if not pts and sec.get('Content'):
                            pts = [p.strip() for p in sec['Content'].split('\n') if p.strip()]
                        pts_str = "\n".join(pts)

                        with st.expander(f"{emoji} {sec.get('Heading', '未命名')} [{sec_risk}]", expanded=(sec_risk == "HIGH")):
                            h_val = st.text_input("章节标题", sec.get('Heading', ''), key=f"sh_{i}")
                            pts_val = st.text_area("要点（每行一条，• 开头）", pts_str, height=200, key=f"sc_{i}")
                            rl_val = st.selectbox("风险等级", ["LOW", "MEDIUM", "HIGH"],
                                                  index=["LOW", "MEDIUM", "HIGH"].index(sec_risk) if sec_risk in ["LOW","MEDIUM","HIGH"] else 0,
                                                  key=f"srl_{i}")
                            if not st.button(f"🗑️ 删除", key=f"sdel_{i}"):
                                new_sections.append({
                                    "Heading": h_val,
                                    "Points": [k.strip() for k in pts_val.split("\n") if k.strip()],
                                    "RiskLevel": rl_val
                                })
                    if st.button("➕ 添加自定义章节"):
                        new_sections.append({"Heading": "自定义条款", "Points": [], "RiskLevel": "LOW"})
                    v4['Sections'] = new_sections

                # ── 风险 & 建议 ──
                with st.expander("⚠️ 风险评估 & 行动建议（可编辑）", expanded=True):
                    top_risks = risk_data.get('TopRisks', [])
                    if top_risks:
                        st.markdown("**🔴 前5大风险条款：**")
                        for idx, r in enumerate(top_risks[:5]):
                            st.markdown(f"**{idx+1}. {r.get('Title','')}**")
                            st.caption(r.get('Detail',''))
                            st.warning(f"影响：{r.get('Impact','')}")

                    neg = risk_data.get('NegotiationPoints', [])
                    if neg:
                        st.markdown("**💬 签约前谈判要点：**")
                        for n in neg:
                            st.markdown(f"◆ {n}")

                    ci = risk_data.get('CheckinChecklist', [])
                    co = risk_data.get('CheckoutChecklist', [])
                    if ci or co:
                        col_ci, col_co = st.columns(2)
                        with col_ci:
                            st.markdown("**✅ 入住前必做：**")
                            for item in ci:
                                st.markdown(f"☐ {item}")
                        with col_co:
                            st.markdown("**📦 离租前必做：**")
                            for item in co:
                                st.markdown(f"☐ {item}")

                st.markdown("---")
                if st.button("🎨 导出完整深度分析 PDF", key="v4_pdf_gen", use_container_width=True, type="primary"):
                    with st.spinner("正在生成精美 PDF 报告..."):
                        try:
                            p_img = create_contract_analysis_pdf(v4, lang=v4_lang)
                            buf_v4 = BytesIO()
                            p_img.save(buf_v4, format="PDF", resolution=150.0)
                            st.download_button(
                                "⬇️ 立即下载 PDF 报告",
                                data=buf_v4.getvalue(),
                                file_name=f"Contract_DeepDive_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                                mime="application/pdf",
                                key="dl_v4_pdf"
                            )
                        except Exception as e:
                            st.error(f"PDF 生成失败：{e}")

# --- End of Admin Tool ---
