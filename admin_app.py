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
                    'region': auto_region, 'postcode': postcode
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

# --- 4e. 带看小结生成 ---
def gen_viewing_summary(client_name: str, prop_title: str, prop_price: int,
                        prop_rooms: str, prop_region: str,
                        pros: List[str], cons: List[str],
                        intention: str, notes: str) -> str:
    pros_block = "\n".join(f"  • {p}" for p in pros) if pros else "  • 暂无"
    cons_block = "\n".join(f"  • {c}" for c in cons) if cons else "  • 暂无"
    date_str = datetime.now().strftime("%Y-%m-%d")
    return f"""━━━━━━━━━━━━━━━━━━━━━━━━
🏠 带看小结 | Viewing Summary
━━━━━━━━━━━━━━━━━━━━━━━━
📅 日期：{date_str}   👤 客户：{client_name}
📍 房源：{prop_title}
💰 月租：£{prop_price} PCM   🛏 户型：{prop_rooms}   📌 区域：{prop_region}

✅ 亮点
{pros_block}

⚠️ 注意事项
{cons_block}

💬 客户意向：{intention}
📝 备注：{notes if notes else '无'}

📋 建议跟进：3天内联系确认意向 → 如感兴趣准备 Referencing 材料清单

— Hao Harbour 独家中介服务
━━━━━━━━━━━━━━━━━━━━━━━━"""

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
def extract_contract(pdf_file) -> str:
    if not pdfplumber: return "⚠️ 未安装 pdfplumber 依赖，无法解析 PDF。"
    try:
        text = ""
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages[:5]: # 只读前5页
                text += page.extract_text() or ""
        
        api_key = st.secrets["OPENAI_API_KEY"]
        prompt = (
            "你是一个专业的英国租房法务助手。请从这段合同文本中提取以下关键信息并用中文输出：\n"
            "1. 租金金额(PCM) 2. 押金金额 3. 租期起止日期 4. 是否有 Break Clause (几个月) "
            "5. 维修责任归属 6. 其它潜在风险(如不合理的扣款条款)。\n"
            "如果没有提到某项，请写'未提及'。"
        )
        r = requests.post("https://api.deepseek.com/chat/completions",
            json={"model": "deepseek-chat", "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text[:8000]} # 截断防止溢出
            ]},
            headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
        return r.json()['choices'][0]['message']['content'].strip()
    except Exception as e:
        return f"❌ 提取失败: {e}"


ws = get_ws()
if ws:
    t1, t2, t3, t4, t5, t6, t7 = st.tabs([
        "✨ 发布新房源", "⚙️ 管理与统计", "🚀 批量发送引擎",
        "🌐 多平台内容包", "👁️ 带看小结", "📊 对比与简报", "🧰 工具箱"
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
                        ws.append_row([now, p_name, p_reg, p_rooms, int(p_price), img_url, zh_desc, 0, 0])
                        st.success("发布成功！海报已存档。")
                        st.rerun()

    with t2:
        data = ws.get_all_records()
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
                            ws.update(f"A{idx}:I{idx}", [[row['date'], nt, nr, nrm, np, row['poster-link'], nd, row['views'], 1 if isf else 0]])
                            st.rerun()
                        if s2.form_submit_button("删除"):
                            ws.delete_rows(idx)
                            st.rerun()
                    
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
                            ai_copy = call_smart_ai(desc_str[:1000]) if desc_str else "最新豪宅首发，欢迎详询！"
                            # 写入数据库
                            current_date = datetime.now().strftime("%Y-%m-%d")
                            ws.append_row([current_date, p_title, final_reg, rooms_val, p_price, img_url_cloud, ai_copy, 0, 0]) # type: ignore
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
    # =====================================================================
    with t4:
        st.subheader("🌐 多平台内容包生成器")
        st.info("💡 同一套房源，一键生成三个平台专属版本：小红书竖版 / 微信方版 / 抖音竖版，同时生成抖音口播脚本。")

        mp_url = st.text_input("🔗 Rightmove 链接（可选，自动填入）", key="mp_url")
        if st.button("🔍 读取房源", key="mp_fetch"):
            if mp_url:
                with st.spinner("抓取中..."):
                    mp_data, mp_err = scrape_rightmove(mp_url)
                    if mp_err:
                        st.error(mp_err)
                    else:
                        st.session_state['mp_data'] = mp_data
                        st.success("✅ 读取成功！")

        mpd = st.session_state.get('mp_data', {})
        mc1, mc2, mc3, mc4 = st.columns(4)
        mp_name  = mc1.text_input("房源名称", value=mpd.get('title', ''), key="mp_name")
        mp_price = mc2.number_input("月租 (£)", min_value=0, value=mpd.get('price', 0), key="mp_price")
        mp_reg_opts = ["中伦敦", "东伦敦", "西伦敦", "北伦敦", "南伦敦"]
        mp_auto_reg = mpd.get('region', '中伦敦')
        mp_reg = mc3.selectbox("区域", mp_reg_opts,
                               index=mp_reg_opts.index(mp_auto_reg) if mp_auto_reg in mp_reg_opts else 0,
                               key="mp_reg")
        mp_rm_opts = ["Studio", "1房", "2房", "3房", "4房+"]
        mp_default_room = mpd.get('rooms', '')
        mp_rooms = mc4.selectbox("户型", mp_rm_opts,
                                 index=mp_rm_opts.index(mp_default_room) if mp_default_room in mp_rm_opts else 0,
                                 key="mp_rooms")
        mp_desc = st.text_area("房源描述（用于生成口播文案）", value=mpd.get('description', ''), height=80, key="mp_desc")
        mp_imgs = st.file_uploader("上传图片（建议 6-8 张）", accept_multiple_files=True, key="mp_files")

        # 如果没有上传，从 Rightmove 抓取的图片自动使用
        mp_files_to_use = list(mp_imgs) if mp_imgs else []
        if not mp_files_to_use and mpd.get('images'):
            for img_url_item in mpd.get('images', []):
                try:
                    r_i = requests.get(str(img_url_item), timeout=10)
                    if r_i.status_code == 200:
                        mp_files_to_use.append(BytesIO(r_i.content))
                except: pass

        if st.button("🎨 生成三版海报 + 口播脚本", type="primary", key="mp_gen"):
            if not mp_files_to_use:
                st.warning("请先上传图片或读取 Rightmove 链接")
            elif not mp_name:
                st.warning("请填写房源名称")
            else:
                with st.spinner("正在生成三个版本，稍等片刻..."):
                    p_xhs  = create_poster(mp_files_to_use, mp_name, mp_price, mp_rooms, mp_reg)
                    p_wc   = create_wechat_poster(mp_files_to_use, mp_name, mp_price, mp_rooms, mp_reg)
                    p_dy   = create_story_poster(mp_files_to_use, mp_name, mp_price, mp_rooms, mp_reg)
                    script = gen_douyin_script(mp_name, int(mp_price), mp_rooms, mp_reg, mp_desc)

                if p_xhs and p_wc and p_dy:
                    st.session_state['mp_posters'] = (p_xhs, p_wc, p_dy)
                    st.session_state['mp_script'] = script
                    st.success("✅ 三版海报生成完毕！")

        if 'mp_posters' in st.session_state:
            p_xhs, p_wc, p_dy = st.session_state['mp_posters']
            col_xhs, col_wc, col_dy = st.columns(3)
            with col_xhs:
                st.markdown("**📱 小红书竖版** (1200×2350)")
                st.image(p_xhs, use_container_width=True)
                buf_xhs = BytesIO()
                p_xhs.save(buf_xhs, format="JPEG", quality=95)
                st.download_button("⬇️ 下载小红书版", data=buf_xhs.getvalue(),
                                   file_name=f"xhs_{mp_name[:15]}.jpg", mime="image/jpeg", key="dl_xhs")
            with col_wc:
                st.markdown("**💬 微信方版** (1080×1080)")
                st.image(p_wc, use_container_width=True)
                buf_wc = BytesIO()
                p_wc.save(buf_wc, format="JPEG", quality=95)
                st.download_button("⬇️ 下载微信版", data=buf_wc.getvalue(),
                                   file_name=f"wechat_{mp_name[:15]}.jpg", mime="image/jpeg", key="dl_wc")
            with col_dy:
                st.markdown("**🎬 抖音Story版** (1080×1920)")
                st.image(p_dy, use_container_width=True)
                buf_dy = BytesIO()
                p_dy.save(buf_dy, format="JPEG", quality=95)
                st.download_button("⬇️ 下载抖音版", data=buf_dy.getvalue(),
                                   file_name=f"douyin_{mp_name[:15]}.jpg", mime="image/jpeg", key="dl_dy")

            st.markdown("---")
            st.markdown("**🎙️ 抖音/小红书 15秒口播文案**")
            st.text_area("复制后配合视频使用", value=st.session_state.get('mp_script', ''), height=160, key="mp_script_box")

            # 一键打包下载（ZIP）
            import zipfile
            zip_buf = BytesIO()
            with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for label, buf in [("xhs", buf_xhs), ("wechat", buf_wc), ("douyin", buf_dy)]:
                    zf.writestr(f"{label}_{mp_name[:15]}.jpg", buf.getvalue())
                zf.writestr("script.txt", st.session_state.get('mp_script', '').encode('utf-8'))
            st.download_button("📦 一键下载全部（ZIP）", data=zip_buf.getvalue(),
                               file_name=f"hao_harbour_{mp_name[:15]}.zip",
                               mime="application/zip", key="dl_zip")

    # =====================================================================
    # TAB 5 — 👁️ 带看小结生成器
    # =====================================================================
    with t5:
        st.subheader("👁️ 带看小结生成器")
        st.info("填写看房信息，一键生成可直接发给客户的带看小结（中文版）。")

        vs_c1, vs_c2 = st.columns(2)
        vs_client = vs_c1.text_input("👤 客户姓名", placeholder="例：王女士")
        vs_date   = vs_c2.date_input("📅 看房日期", value=datetime.today())

        # 从已发布房源中选择
        all_props = ws.get_all_records()
        prop_titles = [f"{r.get('title','?')} — £{r.get('price','?')} ({r.get('region','?')})" for r in all_props]
        vs_prop_idx = st.selectbox("🏠 看的是哪套房源？", options=range(len(prop_titles)),
                                   format_func=lambda x: prop_titles[x] if prop_titles else "暂无房源",
                                   key="vs_prop") if prop_titles else None

        selected_prop = all_props[vs_prop_idx] if vs_prop_idx is not None and all_props else {}

        st.markdown("**✅ 亮点（多选）**")
        pros_opts = ["采光好/朝南", "交通便利（地铁步行 ≤10 分钟）", "设施全新", "装修现代",
                     "楼层高/视野开阔", "价格合理/性价比高", "管理公司口碑好", "安静低噪", "附近学校/购物方便"]
        vs_pros = []
        pc = st.columns(3)
        for i, opt in enumerate(pros_opts):
            if pc[i % 3].checkbox(opt, key=f"pro_{i}"):
                vs_pros.append(opt)

        st.markdown("**⚠️ 注意事项（多选）**")
        cons_opts = ["不含停车位", "楼层低/噪音", "押金高（>6周）", "无 break clause",
                     "面积偏小", "装修老旧", "厨卫需更新", "临近工地/施工", "采光一般"]
        vs_cons = []
        cc = st.columns(3)
        for i, opt in enumerate(cons_opts):
            if cc[i % 3].checkbox(opt, key=f"con_{i}"):
                vs_cons.append(opt)

        intention_opts = ["😍 非常感兴趣，马上申请", "😊 较感兴趣，需家人商量", "🤔 一般，再看看其他", "😐 不感兴趣"]
        vs_intention = st.selectbox("💬 客户意向", intention_opts, key="vs_intent")
        vs_notes = st.text_area("📝 额外备注（可选）", height=80, key="vs_notes")

        if st.button("📋 生成带看小结", type="primary", key="vs_gen"):
            if not vs_client:
                st.warning("请填写客户姓名")
            elif not selected_prop:
                st.warning("请选择看的房源")
            else:
                summary = gen_viewing_summary(
                    client_name=vs_client,
                    prop_title=str(selected_prop.get('title', '')),
                    prop_price=int(float(str(selected_prop.get('price', 0) or 0))),
                    prop_rooms=str(selected_prop.get('rooms', '')),
                    prop_region=str(selected_prop.get('region', '')),
                    pros=vs_pros,
                    cons=vs_cons,
                    intention=vs_intention,
                    notes=vs_notes
                )
                st.session_state['vs_result'] = summary

        if 'vs_result' in st.session_state:
            st.markdown("---")
            st.markdown("**📄 带看小结（可直接复制发微信）**")
            st.text_area("", value=st.session_state['vs_result'], height=420, key="vs_output")
            st.download_button("⬇️ 下载为 TXT", data=st.session_state['vs_result'].encode('utf-8'),
                               file_name=f"viewing_{vs_client}_{vs_date}.txt",
                               mime="text/plain", key="vs_dl")

    # =====================================================================
    # TAB 6 — 📊 房源对比 + 市场简报
    # =====================================================================
    with t6:
        st.subheader("📊 房源对比 & 市场简报")
        
        st.markdown("#### 1️⃣ 房源横向对比")
        all_props = ws.get_all_records()
        if all_props:
            titles = [f"{r['title']} (£{r['price']})" for r in all_props]
            selected_names = st.multiselect("选择需要对比的房源 (最多4个)", options=titles, max_selections=4)
            
            if st.button("🖼️ 生成对比长图", key="comp_gen"):
                if selected_names:
                    selected_data = [r for r in all_props if f"{r['title']} (£{r['price']})" in selected_names]
                    comp_img = gen_comparison_image(selected_data)
                    st.image(comp_img, use_container_width=True)
                    
                    buf_comp = BytesIO()
                    comp_img.save(buf_comp, format="JPEG")
                    st.download_button("⬇️ 下载对比图", data=buf_comp.getvalue(), 
                                       file_name="comparison.jpg", mime="image/jpeg")
                else:
                    st.warning("请至少选择一个房源")

        st.markdown("---")
        st.markdown("#### 2️⃣ 伦敦租赁市场走势 (Google Trends)")
        kw = st.text_input("输入关键词研究热度", value="London Property")
        if st.button("📈 获取趋势数据"):
            with st.spinner("从 Google 获取数据中..."):
                trend_df = get_market_trends(kw)
                if trend_df is not None and not trend_df.empty:
                    st.line_chart(trend_df[kw])
                    st.caption(f"过去三个月 '{kw}' 在大伦敦地区的搜索热度趋势")
                else:
                    st.info("💡 环境未配置 Pytrends 驱动或访问受限。请确保服务器具备代理或海外环境。")

    # =====================================================================
    # TAB 7 — 🧰 工具箱（合同提取 + 爆款关键词）
    # =====================================================================
    with t7:
        st.subheader("🧰 让效率翻倍的工具箱")
        
        tc1, tc2 = st.columns(2)
        
        with tc1:
            st.markdown("#### 📄 合同关键信息智能提取")
            st.info("上传 PDF 合同，AI 将自动分析核心条款及潜在风险。")
            contract_file = st.file_uploader("点击上传 PDF 合同", type="pdf")
            if st.button("🧠 开始分析合同", type="primary"):
                if contract_file:
                    with st.spinner("AI 正在深度阅读合同..."):
                        res = extract_contract(contract_file)
                        st.markdown("---")
                        st.markdown("**🛡️ 合同摘要与风险提示**")
                        st.write(res)
                else:
                    st.warning("请先上传文件")

        with tc2:
            st.markdown("#### 📱 小红书爆款优化器")
            st.info("根据当前趋势，给出最适合伦敦房产的标题模板与哈希标签。")
            topic = st.selectbox("核心话题", ["新盘推介", "租房避坑", "区域测评", "搬家攻略"])
            
            # 模拟爆款库
            templates = {
                "新盘推介": ["被问爆了！伦敦{region}这个宝藏新盘终于开盘了😭", "伦敦租房｜这可能是{region}性价比的天花板了✨", "[寻房记] 住进这里，每天都被伦敦的阳光叫醒"],
                "租房避坑": ["救命！伦敦租房这5个坑千万别踩❌", "伦敦租房避雷指南：学长学姐带血的教训", "新手必看！伦敦租房合同里藏着的“猫腻”"],
                "区域测评": ["住在{region}是种什么体验？", "伦敦区域测评｜{region}真的值得住吗？", "大数据请把这个视频推给想住{region}的朋友！"]
            }
            
            p_reg_name = st.text_input("填入关键词(如区域名)", value="Canary Wharf")
            if st.button("✨ 随机生成爆款文案建议"):
                st.markdown("**🔥 推荐标题:**")
                for t in templates.get(topic, []):
                    st.code(t.replace("{region}", p_reg_name))
                st.markdown("**🏷️ 推荐标签:**")
                st.write("#伦敦租房 #英国留学 #伦敦生活 #伦敦生活方式 #伦敦找房 #HaoHarbour")

