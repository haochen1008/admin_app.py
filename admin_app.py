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
                images = [img.get('url') for img in p_data.get('images', []) if img.get('url')]
                floorplans = [fp.get('url') for fp in p_data.get('floorplans', []) if fp.get('url')]
                
                final_images = images[:8]
                if floorplans and len(final_images) >= 7:
                    final_images = final_images[:7] + [floorplans[0]]
                elif floorplans:
                    final_images.append(floorplans[0])
                
                return {
                    'title': title, 'price': price, 'rooms': rooms_str, 'description': desc, 'images': final_images
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
        draw.text((700, 2140), f"|  {rooms}", font=font_title, fill=(120, 120, 120))
        
        # 装饰金色线条
        draw.line([(40, 2260), (1160, 2260)], fill=(200, 200, 200), width=3)
        draw.text((40, 2280), "Hao Harbour Exclusive London Property", font=font_footer, fill=(180, 160, 100))
        
        return canvas
    except Exception as e:
        st.error(f"海报生成出错: {e}")
        return None

# --- 5. 主程序逻辑 ---
ws = get_ws()
if ws:
    t1, t2, t3 = st.tabs(["✨ 发布新房源", "⚙️ 管理与统计", "🚀 批量发送引擎"])
    
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
        st.info("💡 批量粘贴 Rightmove 链接，去泡杯咖啡，系统会为您自动抓取图片、排版海报上云、AI写文案，并在后台静默发房！")
        bulk_urls = st.text_area("输入 Rightmove 链接 (每行一个)", height=200, placeholder="https://www.rightmove.co.uk/properties/12345...\nhttps://www.rightmove.co.uk/properties/67890...")
        
        b_c1, b_c2 = st.columns(2)
        bulk_reg = b_c1.selectbox("统一默认区域", ["中伦敦", "东伦敦", "西伦敦", "北伦敦", "南伦敦"])
        bulk_room_opts = ["Studio", "1房", "2房", "3房", "4房+"]
        bulk_room = b_c2.selectbox("降级默认户型 (抓取不到时的回退值)", bulk_room_opts, index=2)
        
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
                    data, err = scrape_rightmove(url)
                    if data and not err:
                        # Fetch images
                        files_to_use = []
                        for img_url in data.get('images', []):
                            try:
                                r_img = requests.get(img_url, timeout=10)
                                if r_img.status_code == 200:
                                    files_to_use.append(BytesIO(r_img.content))
                            except: pass
                        
                        if files_to_use:
                            rooms = data.get('rooms', bulk_room)
                            if rooms not in bulk_room_opts: rooms = bulk_room
                            # Create Poster
                            p_poster = create_poster(files_to_use, data['title'], data['price'], rooms, bulk_reg)
                            if p_poster:
                                try:
                                    buf = BytesIO()
                                    p_poster.save(buf, format="JPEG", quality=90)
                                    up_res = cloudinary.uploader.upload(buf.getvalue())
                                    img_url_cloud = up_res['secure_url']
                                    
                                    # AI Copy
                                    ai_copy = call_smart_ai(data['description'][:1000]) if data['description'] else "最新豪宅首发，欢迎详询！"
                                    
                                    # Write DB
                                    now = datetime.now().strftime("%Y-%m-%d")
                                    ws.append_row([now, data['title'], bulk_reg, rooms, int(data['price']), img_url_cloud, ai_copy, 0, 0])
                                    success_count += 1
                                except Exception as e:
                                    st.error(f"处理 {url} 时出错: {e}")
                    
                    progress_bar.progress((i + 1) / len(urls))
                
                status_text.success(f"🎉 跑完啦！成功录入 {success_count} 套高级源。去客户端看看吧！")
