import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account
from PIL import Image, ImageDraw, ImageFont
import cloudinary
import cloudinary.uploader
import requests
import json
import re
from io import BytesIO
from datetime import datetime


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

# --- 3. AI 文案解析 ---
def call_smart_ai(text):
    if not text: return "✓ 请输入描述"
    try:
        api_key = st.secrets["OPENAI_API_KEY"]
        prompt = "作为房产专家，总结为中文列表。每行✓开头，保留楼盘和地铁站名。"
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
                title = p_data.get('text', {}).get('pageTitle', '')
                price_str = p_data.get('prices', {}).get('primaryPrice', '')
                try: price = int(re.sub(r'[^\d]', '', price_str))
                except: price = 0
                desc_html = p_data.get('text', {}).get('description', '')
                desc = re.sub(r'<[^>]+>', '', desc_html).strip()
                bedrooms = p_data.get('bedrooms', 0)
                if bedrooms == 0: rooms_str = "Studio"
                elif bedrooms >= 4: rooms_str = "4房+"
                else: rooms_str = f"{bedrooms}房"
                images = [img.get('url') for img in p_data.get('images', []) if img.get('url')]
                
                return {
                    'title': title, 'price': price, 'rooms': rooms_str, 'description': desc, 'images': images[:6]
                }, None
        return None, "无法解析数据，请检查链接是否为房源页"
    except Exception as e:
        return None, f"抓取失败: {e}"

# --- 4. 核心：海报引擎 (仅修改 display_text 拼接) ---
def create_poster(files, title, price, rooms):
    try:
        # 1200x1800 高清画布
        canvas = Image.new('RGB', (1200, 1800), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        
        try:
            font_title = ImageFont.truetype("simhei.ttf", 65)
            font_footer = ImageFont.truetype("simhei.ttf", 38)
            font_wm = ImageFont.truetype("simhei.ttf", 130) # 水印字体
        except:
            font_title = font_footer = font_wm = ImageFont.load_default()

        # A. 6 宫格拼接
        for i, f in enumerate(files[:6]):
            img = Image.open(f).convert('RGB').resize((590, 450), Image.Resampling.LANCZOS)
            x = 7 + (i % 2) * 597
            y = 7 + (i // 2) * 457
            canvas.paste(img, (x, y))

        # B. 双居中加深水印 (一上一下)
        wm_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        wm_draw = ImageDraw.Draw(wm_layer)
        wm_color = (255, 255, 255, 160) 
        
        # 上水印
        wm_draw.text((220, 400), "Hao Harbour", font=font_wm, fill=wm_color)
        # 下水印
        wm_draw.text((220, 900), "Hao Harbour", font=font_wm, fill=wm_color)
        
        rotated_wm = wm_layer.rotate(30, expand=False)
        canvas.paste(rotated_wm, (0, 0), rotated_wm)

        # C. 底部信息排版 (在此处修改展示文案)
        # 拼接后的文案示例: TITLE | GBP 2500/PCM | 2房
        display_text = f"{title} | {price}/PM | {rooms}"
        draw.text((60, 1460), display_text, font=font_title, fill=(0, 0, 0))
        
        # 装饰金色线条
        draw.line([(60, 1550), (1140, 1550)], fill=(200, 200, 200), width=3)
        
        # 副标题 (London Excellence)
        draw.text((60, 1585), "Hao Harbour | London Excellence", font=font_footer, fill=(180, 160, 100))
        
        return canvas
    except Exception as e:
        st.error(f"海报生成出错: {e}")
        return None

# --- 5. 主程序逻辑 ---
ws = get_ws()
if ws:
    t1, t2 = st.tabs(["✨ 发布新房源", "⚙️ 管理与统计"])
    
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
        p_reg = c3.selectbox("区域", ["中伦敦", "东伦敦", "西伦敦", "北伦敦", "南伦敦"])
        
        rooms_opts = ["Studio", "1房", "2房", "3房", "4房+"]
        default_room = rm_data.get('rooms', "2房")
        idx_room = rooms_opts.index(default_room) if default_room in rooms_opts else 2
        p_rooms = c4.selectbox("户型", rooms_opts, index=idx_room)
        
        en_desc = st.text_area("英文原始描述", value=rm_data.get('description', ''))
        if st.button("🪄 AI 生成中文文案"):
            st.session_state['zh_content'] = call_smart_ai(en_desc)
        
        zh_desc = st.text_area("最终展示描述", value=st.session_state.get('zh_content', ''), height=150)
        up_imgs = st.file_uploader("上传房源图 (建议6张, 将覆盖自动抓取的图片)", accept_multiple_files=True)
        
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
            # 修改点：这里传入了 p_rooms 给海报引擎
            preview_img = create_poster(files_to_use, p_name, p_price, p_rooms)
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
            st.metric("累计访问量", int(pd.to_numeric(df['views'], errors='coerce').sum()))
            search = st.text_input("🔍 快速搜索房源...").lower()
            f_df = df[df['title'].astype(str).str.lower().str.contains(search)] if search else df
            
            for i, row in f_df.iterrows():
                idx = i + 2
                with st.expander(f"{row['title']} (浏览: {row.get('views',0)})"):
                    with st.form(f"edit_{idx}"):
                        ca, cb, cc, cd = st.columns(4)
                        nt = ca.text_input("标题", row['title'])
                        np = cb.number_input("价格", value=int(float(row['price'] or 0)))
                        nr = cc.selectbox("区域", ["中伦敦", "东伦敦", "西伦敦", "北伦敦", "南伦敦"], index=0)
                        nrm = cd.selectbox("户型", ["Studio", "1房", "2房", "3房", "4房+"], index=0)
                        nd = st.text_area("文案", value=row['description'], height=100)
                        isf = st.checkbox("精选置顶", value=bool(row.get('is_featured', 0)))
                        
                        s1, s2 = st.columns(2)
                        if s1.form_submit_button("保存"):
                            ws.update(f"A{idx}:I{idx}", [[row['date'], nt, nr, nrm, np, row['poster-link'], nd, row['views'], 1 if isf else 0]])
                            st.rerun()
                        if s2.form_submit_button("删除"):
                            ws.delete_rows(idx)
                            st.rerun()
