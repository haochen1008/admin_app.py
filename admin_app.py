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


# --- 1.1 鎶ュ憡鐢熸垚鍣ㄥ父閲?---
VIEWING_CONTACT_WECHAT = "HaoHarbour"
VIEWING_CONTACT_PHONE = "07450912493"
VIEWING_DISCLAIMER = (
    "鏈姤鍛婁粎鍩轰簬甯︾湅浜哄憳鍦ㄧ幇鍦虹殑涓汉瑙傚療锛屼笉鏋勬垚浠讳綍褰㈠紡鐨勬硶寰嬪缓璁€佹埧灞嬫祴閲忔姤鍛婃垨鍚堝悓瑕佺害銆?
    "甯︾湅浜哄憳瀵归殣钘忕己闄枫€佹埧灞嬬粨鏋勯棶棰樻垨鏈潵鐜鍙樺寲涓嶆壙鎷呮硶寰嬭矗浠伙紝璇峰鎴峰湪绛剧害鍓嶅姟蹇呰嚜琛屾牳瀹炲叧閿俊鎭€?
)

VIEWING_DEFAULT_INTERIOR = [
    "閲囧厜/閫氶€忓害 (Natural Light)", "瑁呬慨/瀹跺叿缁存姢 (Condition)", "绐楁埛闅旈煶/淇濇殩 (Window Insulation)",
    "澧欎綋/绐楁闃叉疆 (Damp/Mould)", "鎵嬫満淇″彿 (Signal)", "姘村帇/鎺掓按閫熷害 (Water Pressure)",
    "鍌ㄧ墿/鏀剁撼绌洪棿 (Storage)", "瀹剁數鏂版棫 (Appliances)", "鍛抽亾 (Smell)"
]
VIEWING_DEFAULT_BUILDING = [
    "24h 鍓嶅彴/瀹夊叏鎰?(Concierge)", "蹇€掍唬鏀剁郴缁?(Parcel Handling)", "鍏尯鍗敓/姘斿懗 (Cleanliness)",
    "鐢垫鏁伴噺/閫熷害 (Lift Status)", "鍏叡璁炬柦 (Gym/Lounge)"
]
VIEWING_DEFAULT_NEIGHBORHOOD = [
    "灞呬綇瀹夐潤绋嬪害 (Quietness)", "琛楅亾鏁存磥/瀹夊叏 (Street Vibe)", "鐢熸椿閰嶅渚垮埄 (Shops/Cafe)",
    "浜ら€氫究鎹风▼搴?(Transport)", "鏂藉伐/鑴氭墜鏋跺共鎵?(Construction)"
]

# --- 1. 鍒濆鍖栭厤缃?---
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

# --- 2. 鏁版嵁搴撹繛鎺?---
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
        st.error(f"鏁版嵁搴撹繛鎺ュけ璐? {e}")
        return None

def get_safe_records(ws):
    """
    Robust version of get_all_records() that avoids GSpreadException
    by filtering out empty headers and handling duplicates.
    """
    try:
        raw_rows = ws.get_all_values()
        if not raw_rows: return []
        headers = raw_rows[0]
        data_rows = raw_rows[1:]
        clean_headers = []
        seen = {}
        for i, h in enumerate(headers):
            h = str(h).strip()
            if not h: h = f"Unnamed_{i}"
            if h in seen:
                seen[h] += 1
                clean_headers.append(f"{h}_{seen[h]}")
            else:
                seen[h] = 0
                clean_headers.append(h)
        records = []
        for row in data_rows:
            if len(row) < len(clean_headers): row.extend([""] * (len(clean_headers) - len(row)))
            records.append(dict(zip(clean_headers, row)))
        return records
    except Exception as e:
        import streamlit as st
        st.error(f"鈿狅笍 Read Error: {e}")
        return []


# --- 3. 鏅鸿兘浼︽暒鍒嗗尯 ---
# 鍩轰簬鑻卞浗閭紪鍓嶇紑锛坥utward code锛夌簿鍑嗗畾浣嶄鸡鏁︿簲澶у尯
# 鏁版嵁鏉ユ簮锛氳嫳鍥界殗瀹堕偖鏀?+ Google Maps 鍦扮悊楠岃瘉
_POSTCODE_REGION: Dict[str, str] = {
    # 涓鸡鏁?(Central London) 鈥?EC / WC / W1 / SW1 / SE1 etc.
    "EC1": "涓鸡鏁?, "EC2": "涓鸡鏁?, "EC3": "涓鸡鏁?, "EC4": "涓鸡鏁?,
    "WC1": "涓鸡鏁?, "WC2": "涓鸡鏁?,
    "W1":  "涓鸡鏁?, "W1A": "涓鸡鏁?, "W1B": "涓鸡鏁?, "W1C": "涓鸡鏁?,
    "W1D": "涓鸡鏁?, "W1F": "涓鸡鏁?, "W1G": "涓鸡鏁?, "W1H": "涓鸡鏁?,
    "W1J": "涓鸡鏁?, "W1K": "涓鸡鏁?, "W1S": "涓鸡鏁?, "W1T": "涓鸡鏁?,
    "W1U": "涓鸡鏁?, "W1W": "涓鸡鏁?,
    "SW1": "涓鸡鏁?, "SW1A": "涓鸡鏁?, "SW1E": "涓鸡鏁?, "SW1H": "涓鸡鏁?,
    "SW1P": "涓鸡鏁?, "SW1V": "涓鸡鏁?, "SW1W": "涓鸡鏁?, "SW1X": "涓鸡鏁?,
    "SW1Y": "涓鸡鏁?,
    "SE1":  "涓鸡鏁?,
    "N1C": "涓鸡鏁?,   # King's Cross area
    # 涓滀鸡鏁?(East London)
    "E1":  "涓滀鸡鏁?, "E1W": "涓滀鸡鏁?, "E2":  "涓滀鸡鏁?, "E3":  "涓滀鸡鏁?,
    "E4":  "涓滀鸡鏁?, "E5":  "涓滀鸡鏁?, "E6":  "涓滀鸡鏁?, "E7":  "涓滀鸡鏁?,
    "E8":  "涓滀鸡鏁?, "E9":  "涓滀鸡鏁?, "E10": "涓滀鸡鏁?, "E11": "涓滀鸡鏁?,
    "E12": "涓滀鸡鏁?, "E13": "涓滀鸡鏁?, "E14": "涓滀鸡鏁?, "E15": "涓滀鸡鏁?,
    "E16": "涓滀鸡鏁?, "E17": "涓滀鸡鏁?, "E18": "涓滀鸡鏁?, "E20": "涓滀鸡鏁?,
    "IG1": "涓滀鸡鏁?, "IG2": "涓滀鸡鏁?, "IG3": "涓滀鸡鏁?, "IG4": "涓滀鸡鏁?,
    "IG5": "涓滀鸡鏁?, "IG6": "涓滀鸡鏁?, "IG7": "涓滀鸡鏁?, "IG8": "涓滀鸡鏁?,
    "IG11": "涓滀鸡鏁?,
    "RM1": "涓滀鸡鏁?, "RM2": "涓滀鸡鏁?, "RM3": "涓滀鸡鏁?, "RM4": "涓滀鸡鏁?,
    "RM5": "涓滀鸡鏁?, "RM6": "涓滀鸡鏁?, "RM7": "涓滀鸡鏁?, "RM8": "涓滀鸡鏁?,
    "RM9": "涓滀鸡鏁?, "RM10": "涓滀鸡鏁?, "RM11": "涓滀鸡鏁?, "RM12": "涓滀鸡鏁?,
    "RM13": "涓滀鸡鏁?, "RM14": "涓滀鸡鏁?,
    "DA1": "涓滀鸡鏁?, "DA2": "涓滀鸡鏁?, "DA5": "涓滀鸡鏁?, "DA6": "涓滀鸡鏁?,
    "DA7": "涓滀鸡鏁?, "DA8": "涓滀鸡鏁?, "DA15": "涓滀鸡鏁?, "DA16": "涓滀鸡鏁?, "DA17": "涓滀鸡鏁?, "DA18": "涓滀鸡鏁?,
    # 瑗夸鸡鏁?(West London)
    "W2":  "瑗夸鸡鏁?, "W3":  "瑗夸鸡鏁?, "W4":  "瑗夸鸡鏁?, "W5":  "瑗夸鸡鏁?,
    "W6":  "瑗夸鸡鏁?, "W7":  "瑗夸鸡鏁?, "W8":  "瑗夸鸡鏁?, "W9":  "瑗夸鸡鏁?,
    "W10": "瑗夸鸡鏁?, "W11": "瑗夸鸡鏁?, "W12": "瑗夸鸡鏁?, "W13": "瑗夸鸡鏁?,
    "W14": "瑗夸鸡鏁?,
    "TW1": "瑗夸鸡鏁?, "TW2": "瑗夸鸡鏁?, "TW3": "瑗夸鸡鏁?, "TW4": "瑗夸鸡鏁?,
    "TW5": "瑗夸鸡鏁?, "TW6": "瑗夸鸡鏁?, "TW7": "瑗夸鸡鏁?, "TW8": "瑗夸鸡鏁?,
    "TW9": "瑗夸鸡鏁?, "TW10": "瑗夸鸡鏁?, "TW11": "瑗夸鸡鏁?, "TW12": "瑗夸鸡鏁?,
    "TW13": "瑗夸鸡鏁?, "TW14": "瑗夸鸡鏁?,
    "UB1": "瑗夸鸡鏁?, "UB2": "瑗夸鸡鏁?, "UB3": "瑗夸鸡鏁?, "UB4": "瑗夸鸡鏁?,
    "UB5": "瑗夸鸡鏁?, "UB6": "瑗夸鸡鏁?, "UB7": "瑗夸鸡鏁?, "UB8": "瑗夸鸡鏁?,
    "UB9": "瑗夸鸡鏁?, "UB10": "瑗夸鸡鏁?, "UB11": "瑗夸鸡鏁?,
    "HA0": "瑗夸鸡鏁?, "HA1": "瑗夸鸡鏁?, "HA2": "瑗夸鸡鏁?, "HA3": "瑗夸鸡鏁?,
    "HA4": "瑗夸鸡鏁?, "HA5": "瑗夸鸡鏁?, "HA6": "瑗夸鸡鏁?, "HA7": "瑗夸鸡鏁?,
    "HA8": "瑗夸鸡鏁?, "HA9": "瑗夸鸡鏁?,
    "SW6": "瑗夸鸡鏁?, "SW10": "瑗夸鸡鏁?,   # Fulham / Chelsea
    # 鍖椾鸡鏁?(North London)
    "N1":  "鍖椾鸡鏁?, "N2":  "鍖椾鸡鏁?, "N3":  "鍖椾鸡鏁?, "N4":  "鍖椾鸡鏁?,
    "N5":  "鍖椾鸡鏁?, "N6":  "鍖椾鸡鏁?, "N7":  "鍖椾鸡鏁?, "N8":  "鍖椾鸡鏁?,
    "N9":  "鍖椾鸡鏁?, "N10": "鍖椾鸡鏁?, "N11": "鍖椾鸡鏁?, "N12": "鍖椾鸡鏁?,
    "N13": "鍖椾鸡鏁?, "N14": "鍖椾鸡鏁?, "N15": "鍖椾鸡鏁?, "N16": "鍖椾鸡鏁?,
    "N17": "鍖椾鸡鏁?, "N18": "鍖椾鸡鏁?, "N19": "鍖椾鸡鏁?, "N20": "鍖椾鸡鏁?,
    "N21": "鍖椾鸡鏁?, "N22": "鍖椾鸡鏁?,
    "NW1": "鍖椾鸡鏁?, "NW2": "鍖椾鸡鏁?, "NW3": "鍖椾鸡鏁?, "NW4": "鍖椾鸡鏁?,
    "NW5": "鍖椾鸡鏁?, "NW6": "鍖椾鸡鏁?, "NW7": "鍖椾鸡鏁?, "NW8": "鍖椾鸡鏁?,
    "NW9": "鍖椾鸡鏁?, "NW10": "鍖椾鸡鏁?, "NW11": "鍖椾鸡鏁?,
    "EN1": "鍖椾鸡鏁?, "EN2": "鍖椾鸡鏁?, "EN3": "鍖椾鸡鏁?, "EN4": "鍖椾鸡鏁?,
    "EN5": "鍖椾鸡鏁?, "EN6": "鍖椾鸡鏁?,
    "WD6": "鍖椾鸡鏁?, "WD17": "鍖椾鸡鏁?, "WD18": "鍖椾鸡鏁?, "WD19": "鍖椾鸡鏁?, "WD23": "鍖椾鸡鏁?, "WD24": "鍖椾鸡鏁?, "WD25": "鍖椾鸡鏁?,
    # 鍗椾鸡鏁?(South London)
    "SE2":  "鍗椾鸡鏁?, "SE3":  "鍗椾鸡鏁?, "SE4":  "鍗椾鸡鏁?, "SE5":  "鍗椾鸡鏁?,
    "SE6":  "鍗椾鸡鏁?, "SE7":  "鍗椾鸡鏁?, "SE8":  "鍗椾鸡鏁?, "SE9":  "鍗椾鸡鏁?,
    "SE10": "鍗椾鸡鏁?, "SE11": "鍗椾鸡鏁?, "SE12": "鍗椾鸡鏁?, "SE13": "鍗椾鸡鏁?,
    "SE14": "鍗椾鸡鏁?, "SE15": "鍗椾鸡鏁?, "SE16": "鍗椾鸡鏁?, "SE17": "鍗椾鸡鏁?,
    "SE18": "鍗椾鸡鏁?, "SE19": "鍗椾鸡鏁?, "SE20": "鍗椾鸡鏁?, "SE21": "鍗椾鸡鏁?,
    "SE22": "鍗椾鸡鏁?, "SE23": "鍗椾鸡鏁?, "SE24": "鍗椾鸡鏁?, "SE25": "鍗椾鸡鏁?,
    "SE26": "鍗椾鸡鏁?, "SE27": "鍗椾鸡鏁?, "SE28": "鍗椾鸡鏁?,
    "SW2":  "鍗椾鸡鏁?, "SW3":  "鍗椾鸡鏁?, "SW4":  "鍗椾鸡鏁?, "SW5":  "鍗椾鸡鏁?,
    "SW7":  "鍗椾鸡鏁?, "SW8":  "鍗椾鸡鏁?, "SW9":  "鍗椾鸡鏁?,
    "SW11": "鍗椾鸡鏁?, "SW12": "鍗椾鸡鏁?, "SW13": "鍗椾鸡鏁?, "SW14": "鍗椾鸡鏁?,
    "SW15": "鍗椾鸡鏁?, "SW16": "鍗椾鸡鏁?, "SW17": "鍗椾鸡鏁?, "SW18": "鍗椾鸡鏁?,
    "SW19": "鍗椾鸡鏁?, "SW20": "鍗椾鸡鏁?,
    "CR0": "鍗椾鸡鏁?, "CR2": "鍗椾鸡鏁?, "CR3": "鍗椾鸡鏁?, "CR4": "鍗椾鸡鏁?,
    "CR5": "鍗椾鸡鏁?, "CR6": "鍗椾鸡鏁?, "CR7": "鍗椾鸡鏁?, "CR8": "鍗椾鸡鏁?,
    "SM1": "鍗椾鸡鏁?, "SM2": "鍗椾鸡鏁?, "SM3": "鍗椾鸡鏁?, "SM4": "鍗椾鸡鏁?,
    "SM5": "鍗椾鸡鏁?, "SM6": "鍗椾鸡鏁?, "SM7": "鍗椾鸡鏁?,
    "KT1": "鍗椾鸡鏁?, "KT2": "鍗椾鸡鏁?, "KT3": "鍗椾鸡鏁?, "KT4": "鍗椾鸡鏁?,
    "KT5": "鍗椾鸡鏁?, "KT6": "鍗椾鸡鏁?, "KT7": "鍗椾鸡鏁?, "KT8": "鍗椾鸡鏁?,
    "KT9": "鍗椾鸡鏁?, "KT10": "鍗椾鸡鏁?, "KT17": "鍗椾鸡鏁?, "KT18": "鍗椾鸡鏁?,
    "BR1": "鍗椾鸡鏁?, "BR2": "鍗椾鸡鏁?, "BR3": "鍗椾鸡鏁?, "BR4": "鍗椾鸡鏁?,
    "BR5": "鍗椾鸡鏁?, "BR6": "鍗椾鸡鏁?, "BR7": "鍗椾鸡鏁?,
}

def infer_london_region(postcode: str) -> str:
    """鏍规嵁鑻卞浗閭紪鏅鸿兘鍒ゆ柇浼︽暒鍖哄煙锛屾棤闇€浠讳綍 API Key銆?""
    if not postcode:
        return "涓鸡鏁?
    pc = postcode.upper().strip()
    # 鎻愬彇 outward code 鈥?閭紪鍓嶅崐閮ㄥ垎 (e.g. "SW1A" from "SW1A 1AA")
    if " " in pc:
        outward: str = pc.split()[0]
    else:
        m = re.match(r'^[A-Z]{1,2}[0-9]{1,2}[A-Z]?', pc)
        outward = m.group() if m else pc[:4]
    # 灏濊瘯浠庨暱鍒扮煭鍖归厤 (e.g. SW1A -> SW1 -> SW)
    for length in [4, 3, 2]:
        candidate: str = outward[:length]
        if candidate in _POSTCODE_REGION:
            return _POSTCODE_REGION[candidate]
    return "涓鸡鏁?  # 榛樿鍥為€€

# --- 3. AI 鏂囨瑙ｆ瀽 ---
def call_smart_ai(text):
    if not text: return "鉁?璇疯緭鍏ユ弿杩?
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
        prompt = "浣滀负涓€鍚嶈祫娣变鸡鏁︽埧浜т笓瀹讹紝璇峰皢杩欐鑻辨枃鎴挎簮鎻忚堪杞寲涓烘瀬鍏峰惛寮曞姏鐨勫皬绾功鐖嗘鏂囨銆傝姹傦細1. 鏍囬瑕佸惛鐫涳紙浣跨敤Emoji锛夛紱2. 鏍稿績鍗栫偣鎻愮偧娓呮櫚锛堝湴鐞嗕綅缃€佷氦閫氥€佽鏂界瓑锛夛紱3. 璇█鐢熷姩娲绘臣锛屽浣跨敤灏忕孩涔﹀父鐢‥moji锛?. 缁濆涓嶈鍖呭惈寰俊鍙锋垨浠讳綍鎵爜鍔犲井淇＄瓑瀹规槗琚皝鍙风殑璇嶆眹锛屽彲浠ュ啓'娆㈣繋绉佷俊鎴栫暀瑷€鍜ㄨ'锛?. 缁撳熬鍔犱笂鐩稿叧鐨勭儹闂ㄦ爣绛撅紙濡?#浼︽暒绉熸埧 #浼︽暒鍏瘬 绛夛級銆?
        r = requests.post("https://api.deepseek.com/chat/completions",
            json={"model": "deepseek-chat", "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text}]},
            headers={"Authorization": f"Bearer {api_key}"}, timeout=25)
        return r.json()['choices'][0]['message']['content'].replace("**", "")
    except: return "鉁?瑙ｆ瀽澶辫触锛岃鎵嬪姩淇敼"

def scrape_rightmove(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-GB,en;q=0.9'
    }
    try:
        if not url or "rightmove.co.uk" not in url:
            return None, "鏃犳晥鐨?Rightmove 閾炬帴"
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        html = res.text
        if 'window.PAGE_MODEL = ' in html:
            page_model_raw = html.split('window.PAGE_MODEL = ')[1].strip()
            try:
                data, _ = json.JSONDecoder().raw_decode(page_model_raw)
                p_data = data.get('propertyData', {})
            except json.JSONDecodeError as e:
                return None, f"JSON瑙ｆ瀽澶辫触: {e}"
            
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
                elif bedrooms >= 4: rooms_str = "4鎴?"
                else: rooms_str = f"{bedrooms}鎴?
                img_data: Any = p_data.get('images', [])
                images: List[str] = [str(img.get('url')) for img in img_data if isinstance(img, dict) and img.get('url')] if isinstance(img_data, list) else []
                
                fp_data: Any = p_data.get('floorplans', [])
                floorplans: List[str] = [str(fp.get('url')) for fp in fp_data if isinstance(fp, dict) and fp.get('url')] if isinstance(fp_data, list) else []
                
                final_images: List[str] = images[:8]
                if floorplans and len(final_images) >= 7:
                    final_images = final_images[:7] + [floorplans[0]]
                elif floorplans:
                    final_images.append(floorplans[0])
                
                # 鎻愬彇鏈€杩戠殑3涓湴閾?鐏溅绔欏拰鍏蜂綋缁忕含搴?
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
                
                # 鏅鸿兘鍒嗗尯锛氫粠鎴挎簮鍦板潃/閭紪鑷姩鍒ゆ柇浼︽暒鍖哄煙
                address_info: Any = p_data.get('address', {})
                postcode: str = ""
                if isinstance(address_info, dict):
                    postcode = str(address_info.get('outcode', '') or address_info.get('postcode', '') or '')
                if not postcode:
                    # 浠庢爣棰樹腑灏濊瘯鎻愬彇閭紪
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
        return None, "鏃犳硶瑙ｆ瀽鏁版嵁锛岃妫€鏌ラ摼鎺ユ槸鍚︿负鎴挎簮椤?
    except Exception as e:
        return None, f"鎶撳彇澶辫触: {e}"

# --- 4. 鏍稿績锛氭捣鎶ュ紩鎿?(浠呬慨鏀?display_text 鎷兼帴) ---
def create_poster(files, title, price, rooms, region="浼︽暒"):
    try:
        # 1200x2350 楂樻竻鍔犻暱鐢诲竷 (8瀹牸)
        canvas = Image.new('RGB', (1200, 2350), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        
        try:
            font_banner = ImageFont.truetype("simhei.ttf", 60)
            font_title = ImageFont.truetype("simhei.ttf", 65)
            font_price = ImageFont.truetype("simhei.ttf", 100)
            font_footer = ImageFont.truetype("simhei.ttf", 38)
            font_wm = ImageFont.truetype("simhei.ttf", 130) # 姘村嵃瀛椾綋
        except:
            font_banner = font_title = font_price = font_footer = font_wm = ImageFont.load_default()

        # A. 椤堕儴妯箙 Banner
        draw.rectangle([(0, 0), (1200, 130)], fill=(26, 26, 26))
        
        # 灞呬腑 Hao Harbour
        banner_text = "HAO HARBOUR"
        left_padding = 420
        # draw.text_length
        draw.text((left_padding, 35), banner_text, font=font_banner, fill=(191, 160, 100))

        # B. 8 瀹牸鎷兼帴 (2鍒?x 4琛?
        for i, f in enumerate(files[:8]):
            img = Image.open(f).convert('RGB').resize((575, 430), Image.Resampling.LANCZOS)
            x = 20 + (i % 2) * 585
            y = 150 + (i // 2) * 440
            canvas.paste(img, (x, y))

        # C. 鍙屽眳涓姞娣辨按鍗?(涓€涓婁竴涓?
        wm_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        wm_draw = ImageDraw.Draw(wm_layer)
        wm_color = (255, 255, 255, 140) 
        
        # 姘村嵃浣嶇疆椤哄簲鏇撮暱鐨勭敾甯?
        wm_draw.text((220, 600), "Hao Harbour", font=font_wm, fill=wm_color)
        wm_draw.text((220, 1500), "Hao Harbour", font=font_wm, fill=wm_color)
        
        rotated_wm = wm_layer.rotate(30, expand=False)
        canvas.paste(rotated_wm, (0, 0), rotated_wm)

        # D. 搴曢儴涓撲笟淇℃伅鍖?(Y = 1950 璧峰)
        draw.text((40, 1950), f"{title}", font=font_title, fill=(40, 40, 40))
        draw.text((40, 2030), f"Location: {region}", font=font_footer, fill=(100, 100, 100))
        
        draw.text((40, 2100), f"GBP {price} / PCM", font=font_price, fill=(191, 160, 100))
        # 鎴峰瀷鏍囩锛氱敤鍦嗙偣鍒嗛殧锛岄伩鍏嶇珫绾跨鍙锋覆鏌撲负鐏拌壊绾挎潯
        draw.text((40, 2225), f"鈥? {rooms}", font=font_footer, fill=(120, 120, 120))
        
        # 瑁呴グ閲戣壊绾挎潯
        draw.line([(40, 2260), (1160, 2260)], fill=(200, 200, 200), width=3)
        draw.text((40, 2280), "Hao Harbour Exclusive London Property", font=font_footer, fill=(180, 160, 100))
        
        return canvas
    except Exception as e:
        st.error(f"娴锋姤鐢熸垚鍑洪敊: {e}")
        return None
# --- 4b. 寰俊鏂圭増娴锋姤 1080x1080 ---
def create_wechat_poster(files, title, price, rooms, region="浼︽暒"):
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
        # 2x2 鍥剧墖缃戞牸
        for i, f in enumerate(files[:4]):
            img = Image.open(f).convert('RGB').resize((520, 260), Image.Resampling.LANCZOS)
            x = 20 + (i % 2) * 540
            y = 115 + (i // 2) * 270
            canvas.paste(img, (x, y))
        # 姘村嵃
        wm = Image.new('RGBA', canvas.size, (0,0,0,0))
        ImageDraw.Draw(wm).text((100, 320), "Hao Harbour", font=fw, fill=(255,255,255,120))
        wm = wm.rotate(20, expand=False)
        canvas.paste(wm, (0, 0), wm)
        # 淇℃伅鍖?
        draw.text((30, 680), title[:28], font=ft, fill=(40,40,40))
        draw.text((30, 735), f"Location: {region}", font=ff, fill=(100,100,100))
        draw.text((30, 780), f"GBP {price} / PCM", font=fp, fill=(191,160,100))
        draw.text((30, 870), f"鈥?{rooms}", font=ff, fill=(120,120,120))
        draw.line([(30, 910), (1050, 910)], fill=(200,200,200), width=2)
        draw.text((30, 925), "Hao Harbour Exclusive London Property", font=ff, fill=(180,160,100))
        return canvas
    except Exception as e:
        st.error(f"寰俊娴锋姤鐢熸垚鍑洪敊: {e}")
        return None

# --- 4c. 鎶栭煶/Story 绔栫増娴锋姤 1080x1920 ---
def create_story_poster(files, title, price, rooms, region="浼︽暒"):
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
        # 3x2 鍥剧墖缃戞牸
        for i, f in enumerate(files[:6]):
            img = Image.open(f).convert('RGB').resize((520, 370), Image.Resampling.LANCZOS)
            x = 20 + (i % 2) * 540
            y = 130 + (i // 2) * 380
            canvas.paste(img, (x, y))
        # 姘村嵃
        wm = Image.new('RGBA', canvas.size, (0,0,0,0))
        wd = ImageDraw.Draw(wm)
        wd.text((150, 500), "Hao Harbour", font=fw, fill=(255,255,255,120))
        wd.text((150, 1200), "Hao Harbour", font=fw, fill=(255,255,255,120))
        wm = wm.rotate(25, expand=False)
        canvas.paste(wm, (0,0), wm)
        # 淇℃伅鍖?
        draw.text((40, 1278), title[:30], font=ft, fill=(40,40,40))
        draw.text((40, 1345), f"Location: {region}", font=ff, fill=(100,100,100))
        draw.text((40, 1400), f"GBP {price} / PCM", font=fp, fill=(191,160,100))
        draw.text((40, 1510), f"鈥?{rooms}", font=ff, fill=(120,120,120))
        draw.line([(40, 1560), (1040, 1560)], fill=(200,200,200), width=2)
        draw.text((40, 1580), "Hao Harbour Exclusive London Property", font=ff, fill=(180,160,100))
        # 搴曢儴瑁呴グ鏉?
        draw.rectangle([(0, 1860), (1080, 1920)], fill=(26,26,26))
        draw.text((340, 1874), "@HAO HARBOUR", font=ff, fill=(191,160,100))
        return canvas
    except Exception as e:
        st.error(f"鎶栭煶娴锋姤鐢熸垚鍑洪敊: {e}")
        return None

# --- 4d. 鎶栭煶鍙ｆ挱鑴氭湰鐢熸垚 ---
def gen_douyin_script(title: str, price: int, rooms: str, region: str, desc: str) -> str:
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
        prompt = (
            "浣犳槸涓€涓姈闊?灏忕孩涔︽埧浜у崥涓伙紝璇锋牴鎹互涓嬩鸡鏁︽埧婧愪俊鎭紝鍐欎竴娈?5绉掑彛鎾枃妗堛€?
            "瑕佹眰锛氣憼寮€澶?绉掑繀椤绘湁閽╁瓙锛堟儕鍠?鐥涚偣/鏁板瓧锛夆憽璇█鍙ｈ鍖栥€佹湁鑺傚鎰?"
            "鈶㈢粨灏惧紩瀵肩偣璧炴敹钘?鈶ｅ叏鏂囦笉瓒呰繃120瀛?鈶や笉瑕佺敤寰俊/鎵爜绛夎繚绂佽瘝銆?
        )
        content = f"鎴挎簮锛歿title}锛屼綅浜巤region}锛寋rooms}锛屾湀绉熉price}銆傛弿杩帮細{desc[:300]}"
        r = requests.post("https://api.deepseek.com/chat/completions",
            json={"model": "deepseek-chat", "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content}
            ]},
            headers={"Authorization": f"Bearer {api_key}"}, timeout=20)
        return r.json()['choices'][0]['message']['content'].strip()
    except:
        return f"馃幀 銆恵region}路{rooms}銆戜粎拢{price}/鏈堬紒\n{title}锛屽湴娈靛ソ銆佽淇柊锛岀█缂哄ソ鎴跨瓑浣狅紒\n馃憠 鐐硅禐鏀惰棌锛岀淇′簡瑙ｈ鎯咃紒"


# --- 4e. 涓撲笟甯︾湅鎶ュ憡鐢熸垚鍣?(Text & PDF) ---
def gen_pro_viewing_summary(client_name: str, date: str, address: str, facing: str, items: Dict[str, Dict[str, int]], remarks: Dict[str, str]) -> str:
    """鐢熸垚甯?Emoji 鍜岄鑹插尯鍒嗙殑缁撴瀯鍖栨枃妗?""
    summary = [
        f"鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣",
        f"馃彔 涓撲笟甯︾湅鎶ュ憡 | Viewing Report",
        f"鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣",
        f"馃懁 瀹㈡埛锛歿client_name}",
        f"馃搮 鏃ユ湡锛歿date}",
        f"馃搷 鍦板潃锛歿address}",
        f"馃Л 鏈濆悜锛歿facing}",
        f"馃摓 鑱旂郴锛歐echat {VIEWING_CONTACT_WECHAT} | {VIEWING_CONTACT_PHONE}",
        f"鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣\n"
    ]
    
    for section, section_items in items.items():
        summary.append(f"銆恵section}銆?)
        for item, score in section_items.items():
            # 璇勫垎 4-5 涓虹豢鑹诧紝3 涓洪粍鑹诧紝1-2 涓虹孩鑹?
            emoji = "馃煝" if score >= 4 else ("馃煛" if score == 3 else "馃敶")
            stars = "猸? * score
            summary.append(f" {emoji} {item}: {stars}")
        if remarks.get(section):
            summary.append(f" 馃摑 澶囨敞: {remarks[section]}")
        summary.append("")

    if remarks.get('General'):
        summary.append(f"馃挰 鎬讳綋璇勪环: {remarks['General']}\n")
    
    summary.append("鈿狅笍 鍏嶈矗澹版槑:")
    summary.append(VIEWING_DISCLAIMER)
    summary.append("鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣鈹佲攣")
    return "\n".join(summary)

def create_viewing_report_pdf(client_name, date_str, address, facing, items_data, remarks, photos):
    """浣跨敤 PIL 鐢熸垚闀垮浘骞朵繚瀛樹负 PDF"""
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

    # 棰勪及楂樺害锛氬熀纭€鏂囨湰 + 璇勫垎椤?+ 澶囨敞鑷姩鎹㈣棰勪及 + 鐓х墖
    # 姣忎釜澶囨敞棰勪及鍗犵敤棰濆 100 鍍忕礌
    total_items = sum(len(v) for v in items_data.values())
    photo_rows = (len(photos) + 1) // 2
    estimated_height = 1000 + (total_items * 65) + (len(items_data) * 200) + (photo_rows * 460) + 600
    
    canvas = Image.new('RGB', (1200, int(estimated_height)), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    
    # 1. 椤电湁 Banner
    draw.rectangle([(0, 0), (1200, 150)], fill=(26, 26, 26))
    draw.text((60, 45), "HAO HARBOUR - 涓撲笟甯︾湅鎶ュ憡", font=f_banner, fill=(191, 160, 100))
    
    # 2. 鍩烘湰淇℃伅
    y = 190
    draw.text((60, y), f"瀹㈡埛濮撳悕: {client_name}", font=f_body, fill=(50, 50, 50))
    draw.text((600, y), f"鐪嬫埧鏃ユ湡: {date_str}", font=f_body, fill=(50, 50, 50))
    y += 65
    draw.text((60, y), f"鎴垮眿鍦板潃: {address}", font=f_body, fill=(50, 50, 50))
    y += 65
    draw.text((60, y), f"鎴垮眿鏈濆悜: {facing}", font=f_body, fill=(50, 50, 50))
    y += 65
    draw.text((60, y), f"鑱旂郴鏂瑰紡: WeChat {VIEWING_CONTACT_WECHAT} | {VIEWING_CONTACT_PHONE}", font=f_body, fill=(191, 160, 100))
    
    y += 50
    draw.line([(60, y), (1140, y)], fill=(200, 200, 200), width=2)
    y += 50

    # 3. 鏍稿績璇勪及鏉垮潡
    for section, s_items in items_data.items():
        draw.text((60, y), f"銆恵section}銆?, font=f_header, fill=(191, 160, 100))
        y += 80
        for item, score in s_items.items():
            star_color = (34, 139, 34) if score >= 4 else ((255, 140, 0) if score == 3 else (220, 20, 60))
            draw.text((80, y), item, font=f_body, fill=(80, 80, 80))
            draw.text((630, y), "鈽? * score + "鈽? * (5 - score), font=f_star, fill=star_color)
            y += 65
        
        if remarks.get(section):
            y = draw_wrapped_text(draw, f"澶囨敞: {remarks[section]}", 80, y, f_body, 1040, fill=(110, 110, 110))
        y += 45

    # 4. 鎬讳綋澶囨敞
    if remarks.get('General'):
        draw.text((60, y), "鎬讳綋澶囨敞:", font=f_header, fill=(50, 50, 50))
        y += 70
        y = draw_wrapped_text(draw, remarks['General'], 80, y, f_body, 1040, fill=(80, 80, 80))
        y += 60

    # 5. 鐓х墖灞曠ず
    if photos:
        draw.text((60, y), "鐜板満鐓х墖:", font=f_header, fill=(50, 50, 50))
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

    # 6. 鏂滃悜鍔犳繁姘村嵃 (涓庢埧瀛愭捣鎶ヤ竴鑷?
    wm_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    wm_draw = ImageDraw.Draw(wm_layer)
    # 浣跨敤鐧借壊/娴呯伆鑹查珮閫忔槑搴︽按鍗帮紝澶氬瑕嗙洊
    wm_color = (180, 180, 180, 70) 
    for row in range(0, canvas.size[1], 1000):
        for col in range(0, 1200, 600):
            wm_draw.text((col + 50, row + 400), "Hao Harbour", font=f_wm, fill=wm_color)
    
    rotated_wm = wm_layer.rotate(35, expand=False)
    canvas.paste(rotated_wm, (0, 0), rotated_wm)

    # 7. 椤佃剼鍏嶈矗澹版槑
    footer_height = 280
    pdf_final_height = y + footer_height
    final_canvas = canvas.crop((0, 0, 1200, int(pdf_final_height)))
    final_draw = ImageDraw.Draw(final_canvas)
    
    footer_y = pdf_final_height - footer_height
    final_draw.rectangle([(0, footer_y), (1200, pdf_final_height)], fill=(245, 245, 245))
    words = VIEWING_DISCLAIMER
    draw_wrapped_text(final_draw, words, 60, footer_y + 40, f_footer, 1080, fill=(140, 140, 140))

    return final_canvas

# --- 4f. 鎴挎簮瀵规瘮鍥剧敓鎴?(PIL) ---
def gen_comparison_image(selected_props: List[Dict]) -> Image.Image:
    # 鍒涘缓瀵规瘮闀垮浘 (鏈€澶?濂?
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

    # 鏍囬
    draw.rectangle([0, 0, w, 120], fill=(191,160,100))
    draw.text((w//2 - 150, 35), "鎴挎簮瀵规瘮琛?| Property Comparison", font=f_h, fill=(255,255,255))

    # 琛ㄥご
    headers = ["鐓х墖", "鎴挎簮鍚嶇О", "鍖哄煙", "鎴峰瀷", "浠锋牸 (PCM)"]
    x_offsets = [50, 250, 550, 750, 950]
    for i, head in enumerate(headers):
        draw.text((x_offsets[i], 160), head, font=f_b, fill=(100,100,100))
    
    draw.line([(40, 200), (w-40, 200)], fill=(200,200,200), width=2)

    for i, p in enumerate(selected_props):
        y = 250 + (i * 250)
        # 缂╃暐鍥?
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
        draw.text((950, y + 40), f"拢{p['price']}", font=f_p, fill=(191,160,100))
        
        if i < n - 1:
            draw.line([(40, y + 210), (w-40, y + 210)], fill=(240,240,240), width=1)

    return img

# --- 4g. 甯傚満鐑害鐮旂┒ (Trends) ---
def get_market_trends(keyword: str = "London Rent"):
    if not TrendReq: return None
    try:
        pytrends = TrendReq(hl='en-US', tz=360)
        pytrends.build_payload([keyword], cat=0, timeframe='today 3-m', geo='GB-LND')
        df = pytrends.interest_over_time()
        return df
    except:
        return None

# --- 4h. 鍚堝悓鎻愬彇 (AI) ---

# --- 4h. 鍚堝悓鍔╂墜锛氭櫤鑳芥彁鍙栦笌鍒嗘瀽 ---
def parse_ai_json(text: str) -> Dict[str, Any]:
    """瑙ｆ瀽 AI 杩斿洖鐨?JSON锛屽鐞嗗彲鑳界殑 Markdown 浠ｇ爜鍧?""
    try:
        clean = re.sub(r"```json\n|\n```|```", "", text).strip()
        return json.loads(clean)
    except:
        return {}

def extract_contract_pro(pdf_file, target_lang="涓枃") -> Dict[str, Any]:
    """娣卞害鎻愬彇鍚堝悓鍏抽敭淇℃伅骞惰繑鍥炵粨鏋勫寲鏁版嵁锛圖eep Dive 3.0锛?""
    if not pdfplumber: return {"error": "鈿狅笍 鏈畨瑁?pdfplumber 渚濊禆锛屾棤娉曡В鏋?PDF銆?}
    try:
        text = ""
        with pdfplumber.open(pdf_file) as pdf:
            # 澧炲姞鎵弿娣卞害锛氳鍙栧墠 15 椤典互瑕嗙洊澶у鏁?AST 鍚堝悓鐨勬墍鏈夊叧閿潯娆?
            for page in pdf.pages[:15]: 
                text += page.extract_text() or ""
        
        api_key = st.secrets["OPENAI_API_KEY"]
        lang_instruction = f"All your summaries and highlights MUST be written in {target_lang}."
        if target_lang == "涓枃":
            lang_instruction += " 鍐呭蹇呴』浣跨敤涓枃銆?
        
        prompt = (
            f"浣犳槸涓€涓笓涓氱殑鑻卞浗鎴垮眿绉熻祦娉曞姟涓撳銆傝娣卞害闃呰骞跺垎鏋愯繖娈?AST 鍚堝悓鏂囨湰锛屽苟灏嗗叾鍒嗚В涓哄涓儴鍒嗭紝浠?JSON 鏍煎紡杈撳嚭銆俓n"
            f"瑕佹眰锛歕n"
            f"1. 鍔″繀鎻愬彇鍩虹鍏冩暟鎹細鎴夸笢銆佺瀹€佹埧灞嬪湴鍧€銆佹湀绉?Rent PCM)銆佹娂閲?Deposit)銆佽捣绉熸棩鏈?Starting Date/Commencement Date)銆佺粓姝㈡棩鏈熴€佺鏈熸椂闀裤€佽В绾︽潯娆?Break Clause)銆俓n"
            f"2. 闄や簡鍏冩暟鎹紝璇疯瘑鍒悎鍚屼腑鐨勬瘡涓ぇ妯″潡锛堝 Tenant's Obligation, Landlord's Covenants, End of Tenancy, Special Clauses 绛夛級銆俓n"
                        f"3. 瀵规瘡涓ā鍧楄繘琛屾繁搴︾殑鍒嗘瀽锛屾€荤粨鏍稿績鏉℃銆佹綔鍦ㄩ闄╋紝骞堕珮浜绉熷涓嶅埄鐨勫唴瀹广€俓n"
            f"{lang_instruction}\n"
            f"蹇呴』浠?JSON 鏍煎紡杩斿洖锛屽寘鍚? Metadata (Dict), Sections (List of Headings/Content), Risks (String), Summary (String)銆?
        )
        
        r = requests.post("https://api.deepseek.com/chat/completions",
            json={
                "model": "deepseek-chat", 
                "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text[:30000]}],
                "response_format": {"type": "json_object"}
            },
            headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
        
        data = parse_ai_json(r.json()['choices'][0]['message']['content'])
        return data
    except Exception as e:
        return {"error": str(e)}

def create_contract_analysis_pdf(data, lang="中文"):
    """使用 PIL 生成极具设计感的合同分析长图 (Premium Version)"""
    from PIL import Image, ImageDraw, ImageFont
    import streamlit as st
    try:
        banner_size = 50 if lang == "English" else 62
        try:
            f_header = ImageFont.truetype("simhei.ttf", 36)
            f_section = ImageFont.truetype("simhei.ttf", 34)
            f_body = ImageFont.truetype("simhei.ttf", 28)
            f_label = ImageFont.truetype("simhei.ttf", 28)
            f_footer = ImageFont.truetype("simhei.ttf", 20)
            f_banner = ImageFont.truetype("simhei.ttf", banner_size)
            f_wm = ImageFont.truetype("simhei.ttf", 150)
        except:
            f_header = f_section = f_body = f_label = f_footer = f_banner = f_wm = ImageFont.load_default()

        def sanitize_text(t):
            if not t or not isinstance(t, str): return "N/A"
            t = t.replace("£", "GBP").replace("ø", "o").replace("–", "-").replace("—", "-")
            return "".join(c for c in t if ord(c) < 0xFFFF)
        
        _dummy_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))

        def get_lines(text, font, max_width):
            text = sanitize_text(text)
            if not text: return []
            lines, current_line = [], ""
            for char in str(text):
                test_line = current_line + char
                if _dummy_draw.textlength(test_line, font=font) <= max_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = char
            lines.append(current_line)
            return lines

        def draw_wrapped_text(draw, text, x, y, font, max_width, fill=(60, 60, 60), line_h=1.5):
            lines = get_lines(text, font, max_width)
            for line in lines:
                draw.text((x, y), line, font=font, fill=fill)
                y += int(font.size * line_h)
            return y

        def draw_meta_row_full(draw, y, label, val, font_label, font_val):
            draw.text((80, y), f"{label}:", font=font_label, fill=(130, 130, 130))
            y += 40
            new_y = draw_wrapped_text(draw, val, 100, y, font_val, 1020, fill=(30, 30, 30), line_h=1.4)
            return max(y + 65, new_y + 35)

        def draw_meta_grid(draw, y, l1, v1, l2, v2, font_label, font_val):
            draw.text((80, y), f"{l1}:", font=font_label, fill=(130, 130, 130))
            draw_wrapped_text(draw, str(v1), 80, y + 35, font_val, 480, fill=(30, 30, 30), line_h=1.3)
            draw.text((600, y), f"{l2}:", font=font_label, fill=(130, 130, 130))
            draw_wrapped_text(draw, str(v2), 600, y + 35, font_val, 520, fill=(30, 30, 30), line_h=1.3)
            return y + 120

        meta = {k: sanitize_text(v) for k, v in data.get('Metadata', {}).items()}
        sections = []
        for s in data.get('Sections', []):
            sections.append({"Heading": sanitize_text(s.get('Heading', '')), "Content": sanitize_text(s.get('Content', ''))})
        risks_txt = sanitize_text(data.get('Risks', ''))
        summary_txt = sanitize_text(data.get('Summary', ''))

        L = {
            "中文": {"Title": "Hao Harbour - 合同解析报告", "MetaTitle": "1. 合同元数据", "RiskTitle": "风险提醒", "SummaryTitle": "总体评价", "Landlord": "房东", "Tenant": "租客", "Address": "房屋地址", "Rent": "月租金", "Deposit": "押金", "StartDate": "起租日期", "EndDate": "到期日期", "Term": "租期", "Break": "解约条款", "Disclaimer": "免责声明: 此报告由 AI 自动生成，仅供参考。"},
            "English": {"Title": "Hao Harbour - Contract Analysis", "MetaTitle": "1. Metadata", "RiskTitle": "Risk Analysis", "SummaryTitle": "Conclusion", "Landlord": "Landlord", "Tenant": "Tenant", "Address": "Address", "Rent": "Rent PCM", "Deposit": "Deposit", "StartDate": "Start Date", "EndDate": "End Date", "Term": "Term", "Break": "Break Clause", "Disclaimer": "Disclaimer: AI-generated for reference."}
        }.get(lang, "中文")

        y_ptr = 450 + (len(sections) * 200) + (len(get_lines(risks_txt, f_body, 1000)) * 50) + 1200
        canvas = Image.new('RGB', (1200, int(y_ptr)), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        draw.rectangle([(0, 0), (1200, 180)], fill=(35, 35, 35))
        draw.text((80, 55), L["Title"], font=f_banner, fill=(191, 160, 100))
        y = 230
        draw.text((60, y), L["MetaTitle"], font=f_section, fill=(191, 160, 100))
        y += 100
        y = draw_meta_row_full(draw, y, L["Landlord"], meta.get('Landlord', 'N/A'), f_label, f_body)
        y = draw_meta_row_full(draw, y, L["Tenant"], meta.get('Tenant', 'N/A'), f_label, f_body)
        y = draw_meta_row_full(draw, y, L["Address"], meta.get('Address', 'N/A'), f_label, f_body)
        y = draw_meta_grid(draw, y, L["Rent"], meta.get('RentPCM', 'N/A'), L["Deposit"], meta.get('Deposit', 'N/A'), f_label, f_body)
        y = draw_meta_grid(draw, y, L["StartDate"], meta.get('StartDate', 'N/A'), L["EndDate"], meta.get('EndDate', 'N/A'), f_label, f_body)
        y = draw_meta_row_full(draw, y, L["Break"], meta.get('BreakClause', 'N/A'), f_label, f_body)
        
        y += 80
        for s in sections:
            header, content = s['Heading'], s['Content']
            if not content: continue
            draw.rectangle([(60, y), (1140, y + 2)], fill=(230, 230, 230))
            y += 40
            draw.text((80, y), f"▶ {header}", font=f_section, fill=(191, 160, 100))
            y += 80
            y = draw_wrapped_text(draw, content, 100, y, f_body, 1000, line_h=1.5)
            y += 80

        y += 50
        draw.text((60, y), L["RiskTitle"], font=f_section, fill=(200, 0, 0))
        y += 80
        y = draw_wrapped_text(draw, risks_txt, 80, y, f_body, 1040, fill=(180, 0, 0))
        
        y += 50
        draw.text((60, y), L["SummaryTitle"], font=f_section, fill=(50, 50, 50))
        y += 80
        y = draw_wrapped_text(draw, summary_txt, 80, y, f_body, 1040)
        
        wm = Image.new('RGBA', canvas.size, (0,0,0,0))
        ImageDraw.Draw(wm).text((200, 1000), "Hao Harbour Analysis", font=f_wm, fill=(180,180,180,60))
        canvas.paste(wm.rotate(30, expand=False), (0,0), wm.rotate(30, expand=False))
        
        draw.rectangle([(0, y + 200), (1200, y + 450)], fill=(245, 245, 245))
        draw_wrapped_text(draw, L["Disclaimer"], 80, y + 280, f_footer, 1040, fill=(150, 150, 150))
        
        return canvas.crop((0, 0, 1200, y + 450))
    except Exception as e:
        st.error(f"PDF生成失败: {e}")
        return None


    def sanitize_text(t):
        if not t or not isinstance(t, str): return ""
        # 鏇挎崲甯歌鐗规畩绗﹀彿锛孲imHei 鏈夋椂鏃犳硶澶勭悊
        t = t.replace("拢", "GBP").replace("酶", "o").replace("鈥?, "-").replace("鈥?, "-")
        # 杩囨护鎺夋棤娉曟覆鏌撶殑 Emoji 鎴栭潪 BMP 瀛楃 (鍖呮嫭 0xFFFF 鍙婁互涓?
        return "".join(c for c in t if ord(c) < 0xFFFF)

    # 鍒涘缓涓€涓叏灞€鐢ㄤ簬娴嬮噺鐨?dummy image
    _dummy_img = Image.new('RGB', (1, 1))
    _dummy_draw = ImageDraw.Draw(_dummy_img)

    def get_lines(text, font, max_width):
        text = sanitize_text(text)
        if not text: return []
        lines = []
        current_line = ""
        for char in str(text):
            test_line = current_line + char
            try:
                # 浣跨敤鍏ㄥ眬娴嬮噺瀵硅薄锛岄伩鍏嶉噸澶嶅垱寤?Image
                w = _dummy_draw.textlength(test_line, font=font)
                if w <= max_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = char
            except:
                lines.append(current_line)
                current_line = char
        lines.append(current_line)
        return lines

    # 绗竴姝ワ細娓呮礂骞惰绠楅珮搴?
    meta = {k: sanitize_text(v) for k, v in data.get('Metadata', {}).items()}
    sections = []
    for s in data.get('Sections', []):
        sections.append({
            "Heading": sanitize_text(s.get('Heading', '')),
            "Content": sanitize_text(s.get('Content', ''))
        })
    
    risks_txt = sanitize_text(data.get('Risks', ''))
    summary_txt = sanitize_text(data.get('Summary', ''))
    
    y_ptr = 400 
    y_ptr += 3 * 100 # Metadata Rows
    y_ptr += 3 * 85  # Metadata Grid
    
    for s in sections:
        y_ptr += 140
        lines = get_lines(s["Content"], f_body, 1000)
        y_ptr += len(lines) * 50 + 60
    
    y_ptr += 250 + len(get_lines(risks_txt, f_body, 1000)) * 50
    y_ptr += 150 + len(get_lines(summary_txt, f_body, 1000)) * 50
    
    total_est_height = y_ptr + 800
    
    canvas = Image.new('RGB', (1200, int(total_est_height)), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    
    def draw_wrapped_text(draw, text, x, y, font, max_width, fill=(60, 60, 60), line_h=1.6):
        lines = get_lines(text, font, max_width)
        for line in lines:
            draw.text((x, y), line, font=font, fill=fill)
            y += int(font.size * line_h)
        return y

    def draw_meta_row_full(draw, y, label, val, font_label, font_val):
        draw.text((80, y), f"{label}:", font=font_label, fill=(100, 100, 100))
        new_y = draw_wrapped_text(draw, val, 400, y, font_val, 720, fill=(40, 40, 40), line_h=1.4)
        return max(y + 80, new_y + 20)

    def draw_meta_grid(draw, y, l1, v1, l2, v2, font_label, font_val):
        # 宸﹀垪
        draw.text((80, y), f"{l1}:", font=font_label, fill=(100, 100, 100))
        draw.text((320, y), str(v1), font=font_val, fill=(40, 40, 40))
        # 鍙冲垪
        draw.text((600, y), f"{l2}:", font=font_label, fill=(100, 100, 100))
        draw.text((840, y), str(v2), font=font_val, fill=(40, 40, 40))
        return y + 80

    # 1. 椤电湁 Banner
    draw.rectangle([(0, 0), (1200, 160)], fill=(26, 26, 26))
    draw.text((60, 50), L["Title"], font=f_banner, fill=(191, 160, 100))
    
    y = 220
    # 2. 鍩虹璐㈠姟 & 鍏抽敭鏃ユ湡 (绮惧搧缃戞牸甯冨眬)
    draw.text((60, y), L["MetaTitle"], font=f_section, fill=(191, 160, 100))
    y += 95
    # 瀹介」
    y = draw_meta_row_full(draw, y, L["Landlord"], meta.get('Landlord', ''), f_label, f_body)
    y = draw_meta_row_full(draw, y, L["Tenant"], meta.get('Tenant', ''), f_label, f_body)
    y = draw_meta_row_full(draw, y, L["Address"], meta.get('Address', ''), f_label, f_body)
    # 缃戞牸椤?(2x2)
    y = draw_meta_grid(draw, y, L["Rent"], meta.get('RentPCM', ''), L["Deposit"], meta.get('Deposit', ''), f_label, f_body)
    y = draw_meta_grid(draw, y, L["StartDate"], meta.get('StartDate', ''), L["EndDate"], meta.get('EndDate', ''), f_label, f_body)
    y = draw_meta_grid(draw, y, L["Term"], meta.get('Term', ''), "Break Clause", meta.get('BreakClause', ''), f_label, f_body)
    
    y += 70
    # 3. 閫愮珷鑺傛牳蹇冨垎鏋?(Card-based Layout)
    for s in sections:
        # 缁樺埗鑳屾櫙鍗＄墖 (娴呯伆鑹插渾瑙掔煩褰㈡晥鏋?
        header = s.get('Heading', 'Summary')
        # 棰勪及楂樺害鐢ㄤ簬缁樺埗鑳屾櫙
        sec_lines = get_lines(s["Content"], f_body, 1000)
        card_h = 110 + len(sec_lines) * 45
        draw.rectangle([(70, y), (1130, y + card_h)], fill=(250, 250, 250), outline=(230, 230, 230))
        draw.rectangle([(70, y), (85, y + card_h)], fill=(191, 160, 100)) # 宸︿晶瑁呴グ鏉?
        
        draw.text((110, y + 30), f"馃搷 {header}", font=f_section, fill=(191, 160, 100))
        y += 100
        y = draw_wrapped_text(draw, s.get('Content', ''), 110, y, f_body, 980, line_h=1.6)
        y += 80 # Section spacing

    y += 40
    # 4. 椋庨櫓寤鸿
    draw.text((60, y), L["RiskTitle"], font=f_section, fill=(220, 20, 60))
    y += 85
    y = draw_wrapped_text(draw, risks_txt if risks_txt else L["RiskDefault"], 110, y, f_body, 980, fill=(200, 20, 20), line_h=1.6)
    
    y += 40
    # 5. 鎬讳綋缁撹 (Summary Section)
    if summary_txt:
        draw.text((60, y), L["SummaryTitle"], font=f_section, fill=(50, 50, 50))
        y += 85
        y = draw_wrapped_text(draw, summary_txt, 110, y, f_body, 980, line_h=1.6)
        y += 60

    # 6. 姘村嵃
    wm_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    wm_draw = ImageDraw.Draw(wm_layer)
    wm_color = (180, 180, 180, 75)
    wm_txt = "Hao Harbour Intelligence" if lang == "English" else "Hao Harbour 鍚堝悓娣卞害鍒嗘瀽"
    for i in range(0, canvas.size[1], 1000):
        wm_draw.text((150, i + 400), wm_txt, font=f_wm, fill=wm_color)
    rotated_wm = wm_layer.rotate(35, expand=False)
    canvas.paste(rotated_wm, (0, 0), rotated_wm)

    # 7. 椤佃剼
    footer_height = 320
    total_y = y + 250 + footer_height
    final_canvas = canvas.crop((0, 0, 1200, int(total_y)))
    f_draw = ImageDraw.Draw(final_canvas)
    f_y = total_y - (footer_height - 30)
    f_draw.rectangle([(0, f_y), (1200, total_y)], fill=(245, 245, 245))
    draw_wrapped_text(f_draw, L["Disclaimer"], 60, f_y + 80, f_footer, 1080, fill=(140, 140, 140), line_h=1.5)

    return final_canvas


# --- 鍒濆鍖栧甫鐪嬫姤鍛婄姸鎬?---
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
    t1, t2, t3, t4, t5, t6, t7 = st.tabs([
        "鉁?鍙戝竷鏂版埧婧?, "鈿欙笍 绠＄悊涓庣粺璁?, "馃殌 鎵归噺鍙戦€佸紩鎿?,
        "馃寪 澶氬钩鍙板唴瀹瑰寘", "馃憗锔?甯︾湅灏忕粨", "馃搳 瀵规瘮涓庣畝鎶?, "馃О 宸ュ叿绠?
    ])
    
    with t1:
        st.subheader("1. 鍩虹淇℃伅")
        
        # --- Rightmove 璇诲彇妯″潡 ---
        rm_url = st.text_input("馃敆 鑷姩璇诲彇 Rightmove 閾炬帴 (閫夊～锛岃嚜鍔ㄥ～鍏ユ埧婧愪俊鎭強鍥剧墖)")
        if st.button("馃攳 涓€閿鍙?Rightmove"):
            if rm_url:
                with st.spinner("姝ｅ湪鎶撳彇 Rightmove 鏁版嵁锛岃绋嶅€?.."):
                    data, err = scrape_rightmove(rm_url)
                    if err:
                        st.error(err)
                    else:
                        st.session_state['rm_data'] = data
                        st.success("鉁?璇诲彇鎴愬姛锛佽澶嶆牳涓嬫柟鑷姩濉厖鐨勪俊鎭€?)
            else:
                st.warning("璇疯緭鍏?Rightmove 閾炬帴")
        
        rm_data = st.session_state.get('rm_data', {})
        
        c1, c2, c3, c4 = st.columns(4)
        p_name = c1.text_input("鎴挎簮鍚嶇О", value=rm_data.get('title', ''))
        p_price = c2.number_input("鏈堢 (拢)", min_value=0, value=rm_data.get('price', 0))
        reg_opts = ["涓鸡鏁?, "涓滀鸡鏁?, "瑗夸鸡鏁?, "鍖椾鸡鏁?, "鍗椾鸡鏁?]
        auto_reg = rm_data.get('region', '涓鸡鏁?)
        auto_reg_idx = reg_opts.index(auto_reg) if auto_reg in reg_opts else 0
        detected_pc = rm_data.get('postcode', '')
        reg_label = f"鍖哄煙 {'馃幆 宸茶嚜鍔ㄨ瘑鍒?' + detected_pc if detected_pc else '(鍙墜鍔ㄤ慨鏀?'}"
        p_reg = c3.selectbox(reg_label, reg_opts, index=auto_reg_idx)
        
        rooms_opts = ["Studio", "1鎴?, "2鎴?, "3鎴?, "4鎴?"]
        default_room = rm_data.get('rooms', '')
        idx_room = rooms_opts.index(default_room) if default_room in rooms_opts else 0
        p_rooms = c4.selectbox("鎴峰瀷", rooms_opts, index=idx_room)
        
        en_desc = st.text_area("鑻辨枃鍘熷鎻忚堪", value=rm_data.get('description', ''))
        if st.button("馃獎 AI 鐢熸垚涓枃鏂囨"):
            st.session_state['zh_content'] = call_smart_ai(en_desc)
        
        zh_desc = st.text_area("鏈€缁堝睍绀烘弿杩?, value=st.session_state.get('zh_content', ''), height=150)
        up_imgs = st.file_uploader("涓婁紶鎴挎簮鍥?(寤鸿8寮? 灏嗚鐩栬嚜鍔ㄦ姄鍙栫殑鍥剧墖)", accept_multiple_files=True)
        
        # 鍑嗗鍚堝苟鍥剧墖鏉ユ簮
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
            # 淇敼鐐癸細浼犲叆浜?p_reg 鍖哄煙鍜?8鍥炬帓鐗?
            preview_img = create_poster(files_to_use, p_name, p_price, p_rooms, p_reg)
            if preview_img:
                st.image(preview_img, caption="鍙屾按鍗板己鍖栨捣鎶ラ瑙?, width=450)
                
                if st.button("馃殌 绔嬪嵆鍙戝竷"):
                    with st.spinner("鍚屾浜戠涓?.."):
                        buf = BytesIO()
                        preview_img.save(buf, format="JPEG", quality=95)
                        upload_res = cloudinary.uploader.upload(buf.getvalue())
                        img_url = upload_res['secure_url']
                        
                        now = datetime.now().strftime("%Y-%m-%d")
                        p_station = rm_data.get('station', '')
                        p_lat = rm_data.get('lat', '')
                        p_lng = rm_data.get('lng', '')
                        # Index 10 is reserved for manual walkingMinutes to ensure backward compatibility
                        ws.append_row([now, p_name, p_reg, p_rooms, int(p_price), img_url, zh_desc, 0, 0, p_station, "", p_lat, p_lng])
                        st.success("鍙戝竷鎴愬姛锛佹捣鎶ュ凡瀛樻。銆?)
                        st.rerun()

    with t2:
        data = get_safe_records(ws)
        if data:
            df = pd.DataFrame(data)
            
            # --- 澧炲姞澶х洏 (Executive Dashboard) ---
            st.markdown("### 馃搳 鎺掕姒滀笌鏁版嵁寮曟搸 (Executive Dashboard)")
            metric_cols = st.columns(3)
            metric_cols[0].metric("绱璁块棶閲?, int(pd.to_numeric(df['views'], errors='coerce').sum()))
            metric_cols[1].metric("鍦ㄧ鎴挎簮鏁?, len(df))
            metric_cols[2].metric("绮鹃€夌疆椤舵暟", len(df[df.get('is_featured', 0) == 1]))
            
            # 鍥捐〃
            c_d1, c_d2 = st.columns(2)
            with c_d1:
                st.markdown("**鍚勫尯鍩熺儹搴﹀垎甯?*")
                reg_views = df.groupby('region')['views'].sum().reset_index()
                st.bar_chart(reg_views.set_index('region'))
            with c_d2:
                st.markdown("**鏈€鍙楀叧娉ㄦ埛鍨?*")
                room_views = df.groupby('rooms')['views'].sum().reset_index()
                st.bar_chart(room_views.set_index('rooms'))
            
            st.markdown("---")
            search = st.text_input("馃攳 蹇€熸悳绱㈡埧婧?..").lower()
            f_df = df[df['title'].astype(str).str.lower().str.contains(search)] if search else df
            
            for i, row in f_df.iterrows():
                idx = i + 2
                with st.expander(f"{row['title']} (娴忚: {row.get('views',0)})"):
                    with st.form(f"edit_{idx}"):
                        ca, cb, cc, cd = st.columns(4)
                        nt = ca.text_input("鏍囬", row['title'])
                        np = cb.number_input("浠锋牸", value=int(float(row['price'] or 0)))
                        nr = cc.selectbox("鍖哄煙", ["涓鸡鏁?, "涓滀鸡鏁?, "瑗夸鸡鏁?, "鍖椾鸡鏁?, "鍗椾鸡鏁?], index=["涓鸡鏁?, "涓滀鸡鏁?, "瑗夸鸡鏁?, "鍖椾鸡鏁?, "鍗椾鸡鏁?].index(row['region']) if row['region'] in ["涓鸡鏁?, "涓滀鸡鏁?, "瑗夸鸡鏁?, "鍖椾鸡鏁?, "鍗椾鸡鏁?] else 0)
                        nrm_opts = ["Studio", "1鎴?, "2鎴?, "3鎴?, "4鎴?"]
                        nrm = cd.selectbox("鎴峰瀷", nrm_opts, index=nrm_opts.index(row['rooms']) if row['rooms'] in nrm_opts else 0)
                        nd = st.text_area("鏂囨", value=row['description'], height=100)
                        isf = st.checkbox("绮鹃€夌疆椤?, value=bool(row.get('is_featured', 0)))
                        
                        s1, s2 = st.columns(2)
                        if s1.form_submit_button("淇濆瓨"):
                            ws.update(f"A{idx}:I{idx}", [[row['date'], nt, nr, nrm, np, row['poster-link'], nd, row['views'], 1 if isf else 0]])
                            st.rerun()
                        if s2.form_submit_button("鍒犻櫎"):
                            ws.delete_rows(idx)
                            st.rerun()
                    
                    # --- Multi-version Copywriting ---
                    st.markdown("馃挰 **涓€閿鍩熻惀閿€璇濇湳**")
                    moments_txt = f"馃専銆恵row['region']} VIP鏂扮洏棣栧彂銆慭n馃彚 {row['title']}\n馃洀锔?{row['rooms']} | 馃挵 {row['price']}/鏈圽n\n绋€缂哄ア鍗庡ソ鎴匡紝甯︽湁涓撳睘璁炬柦鏈嶅姟銆俓n娆㈣繋绉佷俊鑾峰彇瀹屾暣楂樻竻鐩稿唽鍙婄湅鎴垮悕棰濓紒"
                    dm_txt = f"鍝堝柦锝炵粰鎮ㄦ帹鑽愪竴濂楀湪{row['region']}鐨勩€恵row['title']}銆戯紒\n杩欎釜鏄瘂row['rooms']}锛岀洰鍓嶇閲戞槸 {row['price']}/鏈堛€傛€т环姣旈潪甯搁珮锛乗n鎮ㄧ湅涓嬩富椤佃繖涓埧婧愮殑娴锋姤璺熻鎯咃紝濡傛灉鎰熷叴瓒ｅ挶浠彲浠ラ殢鏃跺畨鎺掔湅鎴垮摝锛?
                    c_m1, c_m2 = st.columns(2)
                    c_m1.text_area("鏈嬪弸鍦堥珮鍐峰悕鐗囩増", value=moments_txt, height=130, key=f"mom_{idx}")
                    c_m2.text_area("寰俊浜插拰绉佽亰鐗?, value=dm_txt, height=130, key=f"dm_{idx}")

    with t3:
        st.subheader("馃殌 鎵归噺鍗伴挒鏈?(Bulk Scraper Engine)")
        st.info("馃挕 鎵归噺绮樿创 Rightmove 閾炬帴锛屽幓娉℃澂鍜栧暋锛岀郴缁熶細涓烘偍鑷姩鎶撳彇鍥剧墖銆佹帓鐗堟捣鎶ヤ笂浜戙€丄I鍐欐枃妗堬紝骞跺湪鍚庡彴闈欓粯鍙戞埧锛佸尯鍩熷皢鑷姩鏍规嵁閭紪璇嗗埆锛屾棤闇€鎵嬪姩鎸囧畾銆?)
        bulk_urls = st.text_area("杈撳叆 Rightmove 閾炬帴 (姣忚涓€涓?", height=200, placeholder="https://www.rightmove.co.uk/properties/12345...\nhttps://www.rightmove.co.uk/properties/67890...")
        
        b_c1, b_c2 = st.columns(2)
        bulk_reg = b_c1.selectbox("鍏滃簳榛樿鍖哄煙 (閭紪璇嗗埆澶辫触鏃朵娇鐢?", ["涓鸡鏁?, "涓滀鸡鏁?, "瑗夸鸡鏁?, "鍖椾鸡鏁?, "鍗椾鸡鏁?])
        bulk_room_opts = ["Studio", "1鎴?, "2鎴?, "3鎴?, "4鎴?"]
        bulk_room = b_c2.selectbox("闄嶇骇榛樿鎴峰瀷 (鎶撳彇涓嶅埌鏃剁殑鍥為€€鍊?", bulk_room_opts, index=0)
        
        if st.button("鈿?寮€濮嬫壒閲忓叏鑷姩澶勭悊 (Start Bulk Process)", type="primary"):
            urls = [u.strip() for u in bulk_urls.split('\n') if u.strip().startswith('http')]
            if not urls:
                st.warning("鎮ㄨ繕娌℃湁杈撳叆浠讳綍閾炬帴鍝︼紒")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                success_count = 0
                
                for i, url in enumerate(urls):
                    status_text.text(f"姝ｅ湪澶勭悊 ({i+1}/{len(urls)}): {url}")
                    scraped_data, err = scrape_rightmove(url)
                    if err:
                        st.warning(f"鈿狅笍 璺宠繃 [{i+1}]锛氭姄鍙栧け璐?鈥?{err}")
                        progress_bar.progress((i + 1) / len(urls))
                        continue
                    if not isinstance(scraped_data, dict):
                        st.warning(f"鈿狅笍 璺宠繃 [{i+1}]锛氳В鏋愭暟鎹け璐ワ紝璇锋鏌ラ摼鎺ユ槸鍚︿负鏈夋晥鎴挎簮椤?)
                        progress_bar.progress((i + 1) / len(urls))
                        continue
                    # 涓嬭浇鍥剧墖
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
                        st.warning(f"鈿狅笍 璺宠繃 [{i+1}]锛氳鎴挎簮娌℃湁鍙敤鍥剧墖")
                        progress_bar.progress((i + 1) / len(urls))
                        continue
                    
                    rooms_val: str = str(scraped_data.get('rooms', bulk_room))
                    if rooms_val not in bulk_room_opts: rooms_val = bulk_room
                    # 鏅鸿兘鍒嗗尯锛氫紭鍏堢敤閭紪鑷姩璇嗗埆鐨勫尯鍩燂紝澶辫触鏃舵墠鐢ㄥ厹搴曢粯璁ゅ€?
                    auto_region_bulk: str = str(scraped_data.get('region', bulk_reg))
                    detected_pc_bulk: str = str(scraped_data.get('postcode', ''))
                    final_reg: str = auto_region_bulk if auto_region_bulk in ["涓鸡鏁?, "涓滀鸡鏁?, "瑗夸鸡鏁?, "鍖椾鸡鏁?, "鍗椾鸡鏁?] else bulk_reg
                    pc_hint = f" [{detected_pc_bulk} 鈫?{final_reg}]" if detected_pc_bulk else f" [鈫?{final_reg}]"
                    status_text.text(f"姝ｅ湪澶勭悊 ({i+1}/{len(urls)}){pc_hint}: {url}")
                    # 鐢熸垚娴锋姤
                    p_title: str = str(scraped_data.get('title', ''))
                    p_price: int = int(scraped_data.get('price', 0))
                    p_poster = create_poster(files_to_use, p_title, p_price, rooms_val, final_reg)
                    if p_poster:
                        try:
                            buf = BytesIO()
                            p_poster.save(buf, format="JPEG", quality=90)
                            up_res = cloudinary.uploader.upload(buf.getvalue()) # type: ignore
                            img_url_cloud = up_res['secure_url']
                            # AI 鏂囨
                            desc_val = scraped_data.get('description', '')
                            desc_str: str = str(desc_val)
                            p_station = str(scraped_data.get('station', ''))
                            p_lat = str(scraped_data.get('lat', ''))
                            p_lng = str(scraped_data.get('lng', ''))
                            ai_copy = call_smart_ai(desc_str[:1000]) if desc_str else "鏈€鏂拌豹瀹呴鍙戯紝娆㈣繋璇﹁锛?
                            # 鍐欏叆鏁版嵁搴?
                            current_date = datetime.now().strftime("%Y-%m-%d")
                            ws.append_row([current_date, p_title, final_reg, rooms_val, p_price, img_url_cloud, ai_copy, 0, 0, p_station, "", p_lat, p_lng]) # type: ignore
                            success_count = success_count + 1
                            st.success(f"鉁?[{i+1}] {p_title} ({final_reg}) 鍙戝竷鎴愬姛锛?)
                        except Exception as e:
                            st.error(f"鉂?[{i+1}] 涓婁紶鍑洪敊: {e}")
                    else:
                        st.warning(f"鈿狅笍 璺宠繃 [{i+1}]锛氭捣鎶ユ覆鏌撳け璐?)
                    
                    progress_bar.progress((i + 1) / len(urls))
                
                status_text.success(f"馃帀 鍏ㄩ儴瀹屾垚锛佹垚鍔熷綍鍏?{success_count} / {len(urls)} 濂椼€傚幓瀹㈡埛绔湅鐪嬪惂锛?)

    # =====================================================================
    # TAB 4 鈥?馃寪 澶氬钩鍙板唴瀹瑰寘
    # =====================================================================
    with t4:
        st.subheader("馃寪 澶氬钩鍙板唴瀹瑰寘鐢熸垚鍣?)
        st.info("馃挕 鍚屼竴濂楁埧婧愶紝涓€閿敓鎴愪笁涓钩鍙颁笓灞炵増鏈細灏忕孩涔︾珫鐗?/ 寰俊鏂圭増 / 鎶栭煶绔栫増锛屽悓鏃剁敓鎴愭姈闊冲彛鎾剼鏈€?)

        mp_url = st.text_input("馃敆 Rightmove 閾炬帴锛堝彲閫夛紝鑷姩濉叆锛?, key="mp_url")
        if st.button("馃攳 璇诲彇鎴挎簮", key="mp_fetch"):
            if mp_url:
                with st.spinner("鎶撳彇涓?.."):
                    mp_data, mp_err = scrape_rightmove(mp_url)
                    if mp_err:
                        st.error(mp_err)
                    else:
                        st.session_state['mp_data'] = mp_data
                        st.success("鉁?璇诲彇鎴愬姛锛?)

        mpd = st.session_state.get('mp_data', {})
        mc1, mc2, mc3, mc4 = st.columns(4)
        mp_name  = mc1.text_input("鎴挎簮鍚嶇О", value=mpd.get('title', ''), key="mp_name")
        mp_price = mc2.number_input("鏈堢 (拢)", min_value=0, value=mpd.get('price', 0), key="mp_price")
        mp_reg_opts = ["涓鸡鏁?, "涓滀鸡鏁?, "瑗夸鸡鏁?, "鍖椾鸡鏁?, "鍗椾鸡鏁?]
        mp_auto_reg = mpd.get('region', '涓鸡鏁?)
        mp_reg = mc3.selectbox("鍖哄煙", mp_reg_opts,
                               index=mp_reg_opts.index(mp_auto_reg) if mp_auto_reg in mp_reg_opts else 0,
                               key="mp_reg")
        mp_rm_opts = ["Studio", "1鎴?, "2鎴?, "3鎴?, "4鎴?"]
        mp_default_room = mpd.get('rooms', '')
        mp_rooms = mc4.selectbox("鎴峰瀷", mp_rm_opts,
                                 index=mp_rm_opts.index(mp_default_room) if mp_default_room in mp_rm_opts else 0,
                                 key="mp_rooms")
        mp_desc = st.text_area("鎴挎簮鎻忚堪锛堢敤浜庣敓鎴愬彛鎾枃妗堬級", value=mpd.get('description', ''), height=80, key="mp_desc")
        mp_imgs = st.file_uploader("涓婁紶鍥剧墖锛堝缓璁?6-8 寮狅級", accept_multiple_files=True, key="mp_files")

        # 濡傛灉娌℃湁涓婁紶锛屼粠 Rightmove 鎶撳彇鐨勫浘鐗囪嚜鍔ㄤ娇鐢?
        mp_files_to_use = list(mp_imgs) if mp_imgs else []
        if not mp_files_to_use and mpd.get('images'):
            for img_url_item in mpd.get('images', []):
                try:
                    r_i = requests.get(str(img_url_item), timeout=10)
                    if r_i.status_code == 200:
                        mp_files_to_use.append(BytesIO(r_i.content))
                except: pass

        if st.button("馃帹 鐢熸垚涓夌増娴锋姤 + 鍙ｆ挱鑴氭湰", type="primary", key="mp_gen"):
            if not mp_files_to_use:
                st.warning("璇峰厛涓婁紶鍥剧墖鎴栬鍙?Rightmove 閾炬帴")
            elif not mp_name:
                st.warning("璇峰～鍐欐埧婧愬悕绉?)
            else:
                with st.spinner("姝ｅ湪鐢熸垚涓変釜鐗堟湰锛岀◢绛夌墖鍒?.."):
                    p_xhs  = create_poster(mp_files_to_use, mp_name, mp_price, mp_rooms, mp_reg)
                    p_wc   = create_wechat_poster(mp_files_to_use, mp_name, mp_price, mp_rooms, mp_reg)
                    p_dy   = create_story_poster(mp_files_to_use, mp_name, mp_price, mp_rooms, mp_reg)
                    script = gen_douyin_script(mp_name, int(mp_price), mp_rooms, mp_reg, mp_desc)

                if p_xhs and p_wc and p_dy:
                    st.session_state['mp_posters'] = (p_xhs, p_wc, p_dy)
                    st.session_state['mp_script'] = script
                    st.success("鉁?涓夌増娴锋姤鐢熸垚瀹屾瘯锛?)

        if 'mp_posters' in st.session_state:
            p_xhs, p_wc, p_dy = st.session_state['mp_posters']
            col_xhs, col_wc, col_dy = st.columns(3)
            with col_xhs:
                st.markdown("**馃摫 灏忕孩涔︾珫鐗?* (1200脳2350)")
                st.image(p_xhs, use_container_width=True)
                buf_xhs = BytesIO()
                p_xhs.save(buf_xhs, format="JPEG", quality=95)
                st.download_button("猬囷笍 涓嬭浇灏忕孩涔︾増", data=buf_xhs.getvalue(),
                                   file_name=f"xhs_{mp_name[:15]}.jpg", mime="image/jpeg", key="dl_xhs")
            with col_wc:
                st.markdown("**馃挰 寰俊鏂圭増** (1080脳1080)")
                st.image(p_wc, use_container_width=True)
                buf_wc = BytesIO()
                p_wc.save(buf_wc, format="JPEG", quality=95)
                st.download_button("猬囷笍 涓嬭浇寰俊鐗?, data=buf_wc.getvalue(),
                                   file_name=f"wechat_{mp_name[:15]}.jpg", mime="image/jpeg", key="dl_wc")
            with col_dy:
                st.markdown("**馃幀 鎶栭煶Story鐗?* (1080脳1920)")
                st.image(p_dy, use_container_width=True)
                buf_dy = BytesIO()
                p_dy.save(buf_dy, format="JPEG", quality=95)
                st.download_button("猬囷笍 涓嬭浇鎶栭煶鐗?, data=buf_dy.getvalue(),
                                   file_name=f"douyin_{mp_name[:15]}.jpg", mime="image/jpeg", key="dl_dy")

            st.markdown("---")
            st.markdown("**馃帣锔?鎶栭煶/灏忕孩涔?15绉掑彛鎾枃妗?*")
            st.text_area("澶嶅埗鍚庨厤鍚堣棰戜娇鐢?, value=st.session_state.get('mp_script', ''), height=160, key="mp_script_box")

            # 涓€閿墦鍖呬笅杞斤紙ZIP锛?
            import zipfile
            zip_buf = BytesIO()
            with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for label, buf in [("xhs", buf_xhs), ("wechat", buf_wc), ("douyin", buf_dy)]:
                    zf.writestr(f"{label}_{mp_name[:15]}.jpg", buf.getvalue())
                zf.writestr("script.txt", st.session_state.get('mp_script', '').encode('utf-8'))
            st.download_button("馃摝 涓€閿笅杞藉叏閮紙ZIP锛?, data=zip_buf.getvalue(),
                               file_name=f"hao_harbour_{mp_name[:15]}.zip",
                               mime="application/zip", key="dl_zip")


    # =====================================================================
    # TAB 5 鈥?馃憗锔?涓撲笟甯︾湅鎶ュ憡鐢熸垚鍣?
    # =====================================================================
    with t5:
        st.subheader("馃憗锔?涓撲笟甯︾湅鎶ュ憡鐢熸垚鍣?(Pro Viewing Report)")
        st.info("濉啓娣卞害娴嬭瘎淇℃伅锛岀敓鎴愬甫鏄熺骇璇勫垎鐨勭粨鏋勫寲鎶ュ憡鍙婁笓涓?PDF銆?)

        # 1. 鍩虹淇℃伅
        st.markdown("#### 1锔忊儯 鍩烘湰淇℃伅")
        vs_c1, vs_c2 = st.columns(2)
        vs_client = vs_c1.text_input("馃懁 瀹㈡埛濮撳悕", placeholder="渚嬶細鐜嬪コ澹?, key="vr_client")
        vs_date = vs_c2.date_input("馃搮 鐪嬫埧鏃ユ湡", value=datetime.today(), key="vr_date")
        
        vs_addr = st.text_input("馃彔 鎴垮瓙鍦板潃", placeholder="渚嬶細Canary Wharf, E14", key="vr_addr")
        vs_facing = st.text_input("馃Л 鎴垮眿鏈濆悜", placeholder="渚嬶細鍧愬寳鏈濆崡 (South Facing)", key="vr_facing")
        
        st.write(f"馃搶 **鍥哄畾灞曠ず鑱旂郴鏂瑰紡**: 馃煝 WeChat: {VIEWING_CONTACT_WECHAT} | 馃摓 Contact: {VIEWING_CONTACT_PHONE}")

        st.markdown("---")

        # 2. 涓夊ぇ鏍稿績璇勪及鏉垮潡
        st.markdown("#### 2锔忊儯 鏍稿績璇勪及鏉垮潡 (1-5 鏄熻瘎鍒?")
        
        sections = {
            'Interior': '馃彔 瀹ゅ唴娣卞害璇勪及 (Interior)',
            'Building': '馃彚 澶фゼ绠＄悊璇勪及 (Building)',
            'Neighborhood': '馃尦 鍛ㄨ竟寰幆澧?(Neighborhood)'
        }
        
        for section_key, section_label in sections.items():
            with st.expander(section_label, expanded=True):
                # 鍔ㄦ€佸鍑忛」鐩?
                cols = st.columns([4, 3, 1])
                cols[0].markdown("**椤圭洰鍚嶇О**")
                cols[1].markdown("**璇勫垎 (1-5 鏄?**")
                
                # 鑾峰彇褰撳墠鏉垮潡鐨勯」鐩?
                current_items = list(st.session_state['viewing_items'][section_key].items())
                
                for item_name, score in current_items:
                    r1, r2, r3 = st.columns([4, 3, 1])
                    r1.text(item_name)
                    # 鏄熺骇璇勫垎閫夋嫨鍣?
                    new_score = r2.select_slider(
                        f"Rating for {item_name}",
                        options=[1, 2, 3, 4, 5],
                        value=score,
                        format_func=lambda x: "猸? * x,
                        key=f"score_{section_key}_{item_name}",
                        label_visibility="collapsed"
                    )
                    st.session_state['viewing_items'][section_key][item_name] = new_score
                    
                    if r3.button("馃棏锔?, key=f"del_{section_key}_{item_name}"):
                        del st.session_state['viewing_items'][section_key][item_name]
                        st.rerun()
                
                # 娣诲姞鏂伴」鐩?
                with st.container():
                    a1, a2 = st.columns([5, 1])
                    new_item_name = a1.text_input(f"娣诲姞鏂伴」鐩埌 {section_key}", key=f"add_input_{section_key}", label_visibility="collapsed", placeholder="杈撳叆椤圭洰鍚嶇О...")
                    if a2.button("鉃?, key=f"add_btn_{section_key}"):
                        if new_item_name:
                            st.session_state['viewing_items'][section_key][new_item_name] = 5
                            st.rerun()
                
                st.session_state['viewing_remarks'][section_key] = st.text_area(f"銆恵section_key}銆戦澶栧娉?, value=st.session_state['viewing_remarks'][section_key], placeholder="杈撳叆璇ユ澘鍧楃殑琛ュ厖璇存槑...", key=f"rem_{section_key}")

        st.markdown("---")
        
        # 3. 鐓х墖绠＄悊
        st.markdown("#### 3锔忊儯 鐜板満鐓х墖绠＄悊")
        uploaded_photos = st.file_uploader("涓婁紶鐜板満鐓х墖 (鏀寔澶氶€?", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
        if uploaded_photos:
            # 灏嗘柊涓婁紶鐨勭収鐗囧悎骞讹紙閬垮厤閲嶅锛?
            for up in uploaded_photos:
                if up not in st.session_state['viewing_photos']:
                    st.session_state['viewing_photos'].append(up)

        if st.session_state['viewing_photos']:
            st.write("馃摳 宸蹭笂浼犵収鐗囬瑙?")
            pcols = st.columns(4)
            for i, p in enumerate(st.session_state['viewing_photos']):
                with pcols[i % 4]:
                    st.image(p, use_container_width=True)
                    if st.button("鍒犻櫎", key=f"del_photo_{i}"):
                        st.session_state['viewing_photos'].pop(i)
                        st.rerun()

        st.markdown("---")
        
        # 4. 鎬讳綋璇勪环涓庣敓鎴?
        st.markdown("#### 4锔忊儯 鎬讳綋璇勪环 & 瀵煎嚭鎶ュ憡")
        st.session_state['viewing_remarks']['General'] = st.text_area("鉁嶏笍 鎬讳綋璇勪环 (General Remarks)", value=st.session_state['viewing_remarks']['General'], height=100)
        
        st.warning(f"馃搫 **鍏嶈矗澹版槑灏嗚嚜鍔ㄥ寘鍚湪鎶ュ憡涓?*:\n{VIEWING_DISCLAIMER}")

        c_g1, c_g2 = st.columns(2)
        if c_g1.button("馃摑 鐢熸垚甯︾湅灏忕粨 (鏂囧瓧鐗?", type="primary", use_container_width=True):
            if not vs_client or not vs_addr:
                st.error("璇疯嚦灏戝～鍐欏鎴峰鍚嶅拰鍦板潃")
            else:
                summary_text = gen_pro_viewing_summary(
                    vs_client, str(vs_date), vs_addr, vs_facing,
                    st.session_state['viewing_items'],
                    st.session_state['viewing_remarks']
                )
                st.session_state['vr_summary_output'] = summary_text

        if c_g2.button("馃帹 鐢熸垚涓撲笟 PDF 鎶ュ憡", use_container_width=True):
            if not vs_client or not vs_addr:
                st.error("璇疯嚦灏戝～鍐欏鎴峰鍚嶅拰鍦板潃")
            else:
                with st.spinner("姝ｅ湪鎺掔増骞剁敓鎴?PDF..."):
                    pdf_canvas = create_viewing_report_pdf(
                        vs_client, str(vs_date), vs_addr, vs_facing,
                        st.session_state['viewing_items'],
                        st.session_state['viewing_remarks'],
                        st.session_state['viewing_photos']
                    )
                    st.session_state['vr_pdf_output'] = pdf_canvas

        if 'vr_summary_output' in st.session_state:
            st.markdown("### 馃搫 鏂囧瓧鐗堝皬缁?)
            st.text_area("澶嶅埗鍙戠粰瀹㈡埛:", value=st.session_state['vr_summary_output'], height=400)
        
        if 'vr_pdf_output' in st.session_state:
            st.markdown("### 馃柤锔?PDF 鎶ュ憡棰勮")
            st.image(st.session_state['vr_pdf_output'], caption="杩欏氨鏄渶缁堢敓鎴愮殑 PDF 甯冨眬棰勮", use_container_width=True)
            
            # 鎻愪緵涓嬭浇
            buf_pdf = BytesIO()
            st.session_state['vr_pdf_output'].save(buf_pdf, format="PDF", resolution=100.0)
            st.download_button(
                "猬囷笍 绔嬪嵆涓嬭浇 PDF 鎶ュ憡",
                data=buf_pdf.getvalue(),
                file_name=f"Viewing_Report_{vs_client}_{vs_date}.pdf",
                mime="application/pdf"
            )

    # =====================================================================
    # TAB 6 鈥?馃搳 鎴挎簮瀵规瘮 + 甯傚満绠€鎶?
    # =====================================================================
    with t6:
        st.subheader("馃搳 鎴挎簮瀵规瘮 & 甯傚満绠€鎶?)
        
        st.markdown("#### 1锔忊儯 鎴挎簮妯悜瀵规瘮")
        all_props = get_safe_records(ws)
        if all_props:
            titles = [f"{r['title']} (拢{r['price']})" for r in all_props]
            selected_names = st.multiselect("閫夋嫨闇€瑕佸姣旂殑鎴挎簮 (鏈€澶?涓?", options=titles, max_selections=4)
            
            if st.button("馃柤锔?鐢熸垚瀵规瘮闀垮浘", key="comp_gen"):
                if selected_names:
                    selected_data = [r for r in all_props if f"{r['title']} (拢{r['price']})" in selected_names]
                    comp_img = gen_comparison_image(selected_data)
                    st.image(comp_img, use_container_width=True)
                    
                    buf_comp = BytesIO()
                    comp_img.save(buf_comp, format="JPEG")
                    st.download_button("猬囷笍 涓嬭浇瀵规瘮鍥?, data=buf_comp.getvalue(), 
                                       file_name="comparison.jpg", mime="image/jpeg")
                else:
                    st.warning("璇疯嚦灏戦€夋嫨涓€涓埧婧?)

        st.markdown("---")
        st.markdown("#### 2锔忊儯 浼︽暒绉熻祦甯傚満璧板娍 (Google Trends)")
        kw = st.text_input("杈撳叆鍏抽敭璇嶇爺绌剁儹搴?, value="London Property")
        if st.button("馃搱 鑾峰彇瓒嬪娍鏁版嵁"):
            with st.spinner("浠?Google 鑾峰彇鏁版嵁涓?.."):
                trend_df = get_market_trends(kw)
                if trend_df is not None and not trend_df.empty:
                    st.line_chart(trend_df[kw])
                    st.caption(f"杩囧幓涓変釜鏈?'{kw}' 鍦ㄥぇ浼︽暒鍦板尯鐨勬悳绱㈢儹搴﹁秼鍔?)
                else:
                    st.info("馃挕 鐜鏈厤缃?Pytrends 椹卞姩鎴栬闂彈闄愩€傝纭繚鏈嶅姟鍣ㄥ叿澶囦唬鐞嗘垨娴峰鐜銆?)

    # =====================================================================
    # TAB 7 鈥?馃О 宸ュ叿绠憋紙鍚堝悓鎻愬彇 + 鐖嗘鍏抽敭璇嶏級
    # =====================================================================
    with t7:
        st.subheader("馃О 璁╂晥鐜囩炕鍊嶇殑宸ュ叿绠?)
        
        tc1, tc2 = st.columns(2)
        
        with tc1:
            st.markdown("#### 馃搫 鍚堝悓鍏抽敭淇℃伅鏅鸿兘鎻愬彇")
            st.info("涓婁紶 PDF 鍚堝悓锛孉I 灏嗚嚜鍔ㄥ垎鏋愭牳蹇冩潯娆惧強娼滃湪椋庨櫓銆?)
            contract_file = st.file_uploader("鐐瑰嚮涓婁紶 PDF 鍚堝悓", type="pdf")
            v3_lang = st.radio("甯屾湜鍒嗘瀽鍑虹殑璇█ (Language)", ["涓枃", "English"], horizontal=True)

            if st.button("馃 寮€濮嬪叏鍚堝悓娣卞害瑙ｆ瀽 (Deep Dive 3.0)", type="primary"):
                if contract_file:
                    with st.spinner("AI 姝ｅ湪閫愮珷鑺傞槄璇诲苟鎻愬彇鏍稿績鏉℃ (绾?0-90绉?..."):
                        res = extract_contract_pro(contract_file, target_lang=v3_lang)
                        if "error" in res:
                            st.error(res["error"])
                        else:
                            # 瀛樺偍 Deep Dive 鏁版嵁缁撴瀯
                            st.session_state['contract_v3'] = res
                            st.session_state['contract_v3_lang'] = v3_lang
                else:
                    st.warning("璇峰厛涓婁紶鏂囦欢")

            if 'contract_v3' in st.session_state:
                st.markdown("---")
                st.subheader("馃搵 鍚堝悓娣卞害瑙ｆ瀽棰勮 (鍙紪杈?")
                st.info("馃挕 姣忛」鍐呭鍧囧彲鐐瑰嚮淇敼銆傚鏋?AI 婕忔帀浜嗘煇浜涚珷鑺傦紝鎮ㄥ彲浠ユ墜鍔ㄦ坊鍔犮€?)
                
                v3 = st.session_state['contract_v3']
                meta = v3.get('Metadata', {})
                sections = v3.get('Sections', [])

                # 1. 鏍稿績鍏冩暟鎹紪杈?
                with st.expander("馃搶 1. 鏍稿績鏉℃ (Metadata)", expanded=True):
                    m1, m2 = st.columns(2)
                    meta['Landlord'] = m1.text_input("鎴夸笢 (Landlord)", meta.get('Landlord',''))
                    meta['Tenant'] = m2.text_input("绉熷 (Tenant)", meta.get('Tenant',''))
                    meta['Address'] = st.text_input("鎴垮眿鍦板潃", meta.get('Address',''))
                    
                    d1, d2, d3 = st.columns(3)
                    meta['StartDate'] = d1.text_input("馃彔 璧风鏃ユ湡 (Starting Date)", meta.get('StartDate',''))
                    meta['EndDate'] = d2.text_input("缁堟鏃ユ湡 (End Date)", meta.get('EndDate',''))
                    meta['Term'] = d3.text_input("绉熸湡鏃堕暱 (Term)", meta.get('Term',''))
                    
                    p1, p2, p3 = st.columns(3)
                    meta['RentPCM'] = p1.text_input("鏈堢 (Rent PCM)", meta.get('RentPCM',''))
                    meta['Deposit'] = p2.text_input("鎶奸噾 (Deposit)", meta.get('Deposit',''))
                    meta['BreakClause'] = p3.text_input("瑙ｇ害鏉℃ (Break Clause)", meta.get('BreakClause',''))

                # 2. 鍔ㄦ€佺珷鑺傜紪杈?
                st.markdown("#### 馃摉 閫愮珷鑺傛繁搴︽憳瑕?(Clause Breakdown)")
                new_sections = []
                for i, sec in enumerate(sections):
                    with st.expander(f"馃搷 {sec.get('Heading', '鏈懡鍚嶇珷鑺?)}", expanded=True):
                        h_val = st.text_input(f"绔犺妭鏍囬", sec.get('Heading',''), key=f"h_{i}")
                        c_val = st.text_area(f"绔犺妭瑕佺偣鎬荤粨", sec.get('Content',''), height=150, key=f"c_{i}")
                        if st.button(f"馃棏锔?鍒犻櫎姝ょ珷鑺?, key=f"rem_{i}"):
                            # 鏍囪鍒犻櫎閫昏緫锛堥€氳繃涓嶅姞鍏?new_sections 瀹炵幇锛?
                            continue
                        new_sections.append({"Heading": h_val, "Content": c_val})
                
                # 娣诲姞鏂扮珷鑺傚姛鑳?
                if st.button("鉃?娣诲姞涓€澶勮嚜瀹氫箟绔犺妭/澶囨敞"):
                    new_sections.append({"Heading": "鑷畾涔夋潯娆?, "Content": ""})
                
                v3['Sections'] = new_sections

                # 3. 椋庨櫓涓庢€荤粨
                with st.expander("鈿狅笍 椋庨櫓鎻愮ず涓庢牳蹇冩€荤粨", expanded=True):
                    v3['Risks'] = st.text_area("娼滃湪椋庨櫓鐐?, v3.get('Risks',''), height=100)
                    v3['Summary'] = st.text_area("鍏ㄧ瘒鎬荤粨", v3.get('Summary',''), height=80)

                st.markdown("---")
                if st.button("馃帹 瀵煎嚭鍏ㄥ悎鍚屾繁搴﹀垎鏋?PDF", key="v3_pdf_gen", use_container_width=True):
                    with st.spinner("姝ｅ湪鎺掔増闀跨瘒鎶ュ憡 PDF (鍚按鍗?..."):
                        p_img = create_contract_analysis_pdf(v3, lang=st.session_state.get('contract_v3_lang', '涓枃'))
                        buf_v3 = BytesIO()
                        p_img.save(buf_v3, format="PDF", resolution=100.0)
                        st.download_button("猬囷笍 绔嬪嵆涓嬭浇娣卞害鎶ュ憡 PDF", data=buf_v3.getvalue(), 
                                           file_name=f"Full_Contract_Report_{datetime.now().strftime('%Y%m%d')}.pdf", 
                                           mime="application/pdf", key="dl_v3_pdf")

        with tc2:
            st.markdown("#### 馃摫 灏忕孩涔︾垎娆句紭鍖栧櫒")
            st.info("鏍规嵁褰撳墠瓒嬪娍锛岀粰鍑烘渶閫傚悎浼︽暒鎴夸骇鐨勬爣棰樻ā鏉夸笌鍝堝笇鏍囩銆?)
            topic = st.selectbox("鏍稿績璇濋", ["鏂扮洏鎺ㄤ粙", "绉熸埧閬垮潙", "鍖哄煙娴嬭瘎", "鎼鏀荤暐"])
            
            # 妯℃嫙鐖嗘搴?
            templates = {
                "鏂扮洏鎺ㄤ粙": ["琚棶鐖嗕簡锛佷鸡鏁region}杩欎釜瀹濊棌鏂扮洏缁堜簬寮€鐩樹簡馃槶", "浼︽暒绉熸埧锝滆繖鍙兘鏄瘂region}鎬т环姣旂殑澶╄姳鏉夸簡鉁?, "[瀵绘埧璁癩 浣忚繘杩欓噷锛屾瘡澶╅兘琚鸡鏁︾殑闃冲厜鍙啋"],
                "绉熸埧閬垮潙": ["鏁戝懡锛佷鸡鏁︾鎴胯繖5涓潙鍗冧竾鍒俯鉂?, "浼︽暒绉熸埧閬块浄鎸囧崡锛氬闀垮濮愬甫琛€鐨勬暀璁?, "鏂版墜蹇呯湅锛佷鸡鏁︾鎴垮悎鍚岄噷钘忕潃鐨勨€滅尗鑵烩€?],
                "鍖哄煙娴嬭瘎": ["浣忓湪{region}鏄浠€涔堜綋楠岋紵", "浼︽暒鍖哄煙娴嬭瘎锝渰region}鐪熺殑鍊煎緱浣忓悧锛?, "澶ф暟鎹鎶婅繖涓棰戞帹缁欐兂浣弡region}鐨勬湅鍙嬶紒"]
            }
            
            p_reg_name = st.text_input("濉叆鍏抽敭璇?濡傚尯鍩熷悕)", value="Canary Wharf")
            if st.button("鉁?闅忔満鐢熸垚鐖嗘鏂囨寤鸿"):
                st.markdown("**馃敟 鎺ㄨ崘鏍囬:**")
                for t in templates.get(topic, []):
                    st.code(t.replace("{region}", p_reg_name))
                st.markdown("**馃彿锔?鎺ㄨ崘鏍囩:**")
                st.write("#浼︽暒绉熸埧 #鑻卞浗鐣欏 #浼︽暒鐢熸椿 #浼︽暒鐢熸椿鏂瑰紡 #浼︽暒鎵炬埧 #HaoHarbour")

# --- End of Admin Tool ---


