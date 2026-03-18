import streamlit as st
import gspread
from google.oauth2 import service_account
import pandas as pd
import urllib.parse
import requests

# --- 1. 页面配置与 CSS ---
st.set_page_config(page_title="Hao Harbour | London Luxury", layout="wide")

st.markdown("""
    <style>
    /* 导航标签样式 */
    .stTabs [data-baseweb="tab-list"] { gap: 20px; justify-content: center; }
    .stTabs [aria-selected="true"] { color: #bfa064 !important; border-bottom: 2px solid #bfa064 !important; }

    /* 房源卡片样式 */
    .prop-title { font-weight: bold; font-size: 18px; color: #1a1a1a; margin: 5px 0; }
    .prop-price { color: #bfa064; font-size: 22px; font-weight: bold; }
    .prop-date { font-size: 12px; color: #999; margin-bottom: 10px; }
    
    /* WhatsApp 按钮样式 */
    .wa-link { background-color: #25D366 !important; color: white !important; text-align: center; padding: 10px; border-radius: 8px; font-weight: bold; text-decoration: none; display: block; }
    
    #MainMenu, footer, .stAppDeployButton, [data-testid="stToolbar"] {visibility: hidden; display: none !important;}
    </style>
""", unsafe_allow_html=True)

# --- 2. 数据库连接 ---
def get_data():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        gc = gspread.authorize(creds)
        ws = gc.open("Hao_Harbour_DB").get_worksheet(0)
        return pd.DataFrame(ws.get_all_records()), ws
    except:
        return pd.DataFrame(), None

# --- 3. 详情弹窗 (修复重复，保留功能) ---
@st.dialog("Property Details")
def show_details(item, ws, row_idx):
    # A. 高清海报 (F列)
    img_url = item.get('poster-link', '')
    if img_url:
        st.image(img_url, use_container_width=True)
        try:
            resp = requests.get(img_url, timeout=10)
            st.download_button(label="📥 下载海报", data=resp.content, file_name=f"Hao_{item['title']}.jpg", mime="image/jpeg", use_container_width=True)
        except: pass

    st.markdown(f"## {item['title']}")
    st.markdown(f"📅 **发布日期**: {item.get('date', '近期')}")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("月租", f"£{item['price']}")
    c2.metric("区域", item['region'])
    c3.metric("户型", item['rooms'])
    
    st.markdown("---")
    
    # B. 房源文案 (一键复制且不重复显示)
    st.markdown("### 📜 房源亮点")
    raw_desc = str(item.get('description', ''))
    formatted_desc = raw_desc.replace('✓', '\n✓').strip()
    st.info("💡 点击下方框内右上角一键复制：")
    st.code(formatted_desc, language=None)

    st.markdown("---")
    m_q = urllib.parse.quote(item['title'] + " London")
    st.link_button("📍 在 Google Maps 查看位置", f"https://www.google.com/maps/search/{m_q}", use_container_width=True)

    # 联系方式
    st.markdown("### 📱 预约咨询")
    cl, cr = st.columns(2)
    with cl:
        st.markdown("**微信**")
        st.code("HaoHarbour", language=None)
    with cr:
        wa_url = f"https://wa.me/447450912493?text=Interested in {item['title']}"
        st.markdown(f'<a href="{wa_url}" class="wa-link">💬 WhatsApp</a>', unsafe_allow_html=True)

    # 浏览量
    try:
        new_v = int(item.get('views', 0)) + 1
        ws.update_cell(row_idx, 8, new_v)
    except: pass

# --- 4. 主程序：四大 TAB ---
st.markdown("<h1 style='text-align:center; color:#1a1a1a; font-family:serif; font-size:42px;'>HAO HARBOUR</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#bfa064; letter-spacing:5px; font-size:12px;'>EXCLUSIVE LONDON LIVING</p>", unsafe_allow_html=True)

df, worksheet = get_data()

if not df.empty:
    tabs = st.tabs(["🏠 房源精选", "🛠️ 我们的服务", "👤 关于我们", "📞 联系方式"])
    
    # --- TAB 1: 房源精选 ---
    # --- TAB 1: 房源精选 ---
    with tabs[0]:
        # 1. 顶部筛选器与排序器
        with st.expander("🔍 筛选与高级排序", expanded=False):
            search_q = st.text_input("输入楼盘、地铁站关键词...", "").lower()
            
            f1, f2, f3 = st.columns(3)
            sel_reg = f1.multiselect("区域", options=sorted(df['region'].unique()))
            sel_room = f2.multiselect("户型", options=sorted(df['rooms'].unique()))
            max_p = f3.slider("预算上限 (£)", 1000, 15000, 15000)
            
            st.markdown("---")
            # 新增：排序控制列
            s1, s2 = st.columns(2)
            sort_by = s1.selectbox("排序维度", ["发布时间", "租金价格"])
            sort_order = s2.selectbox("排序方式", ["从高到低 (Newest/Highest)", "从低到高 (Oldest/Lowest)"])
        
        f_df = df.copy()

        # 2. 基础过滤
        if search_q:
            f_df = f_df[f_df['title'].str.lower().str.contains(search_q) | f_df['description'].str.lower().str.contains(search_q)]
        if sel_reg: f_df = f_df[f_df['region'].isin(sel_reg)]
        if sel_room: f_df = f_df[f_df['rooms'].isin(sel_room)]
        
        # 转换租金为数字
        f_df['p_num'] = pd.to_numeric(f_df['price'], errors='coerce').fillna(0)
        f_df = f_df[f_df['p_num'] <= max_p]

        # 转换日期格式 (核心修复)
        f_df['date'] = pd.to_datetime(f_df['date'], errors='coerce')
        
        # 3. 执行用户自定义排序
        is_asc = (sort_order == "从低到高 (Oldest/Lowest)")
        
        if sort_by == "发布时间":
            # 始终保持 is_featured 置顶，然后根据日期排序
            f_df = f_df.sort_values(by=['is_featured', 'date'], ascending=[False, is_asc])
        else:
            # 始终保持 is_featured 置顶，然后根据价格排序
            f_df = f_df.sort_values(by=['is_featured', 'p_num'], ascending=[False, is_asc])

        # 4. 渲染房源
        st.markdown(f"共有 **{len(f_df)}** 套符合条件的房源")
        cols = st.columns(3)
        for i, (idx, row) in enumerate(f_df.iterrows()):
            with cols[i % 3]:
                with st.container(border=True):
                    p_url = row.get('poster-link', '')
                    if p_url: st.image(p_url, use_container_width=True)
                    st.markdown(f'<div class="prop-title">{row["title"]}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="prop-price">£{row["price"]} /mo</div>', unsafe_allow_html=True)
                    
                    # 格式化显示日期
                    d_val = row['date'].strftime('%Y-%m-%d') if pd.notnull(row['date']) else "近期"
                    st.markdown(f'<div class="prop-date">📍 {row["region"]} | 🗓️ {d_val}</div>', unsafe_allow_html=True)
                    
                    if st.button("详情", key=f"btn_{idx}_{i}", use_container_width=True):
                        show_details(row, worksheet, idx + 2)
                        
    # --- TAB 2: 我们的服务 (完全还原你的原始文案) ---
    with tabs[1]:
        st.markdown("### 🛠️ 全生命周期管家式关怀")
        s_c1, s_c2 = st.columns(2)
        with s_c1:
            st.markdown("""
            **精准定向选址 (Bespoke Property Search)**
            * **覆盖城市**：深度覆盖伦敦、曼彻斯特、伯明翰等核心求学区域。
            * **需求画像**：根据校区、预算、安全系数及周边交通进行大数据筛选。
            """)
            st.markdown("""
            **账单管家 (Utility Setting-up Support)**
            * **Utilities 托管**：协助开通水、电、煤气及高性价比宽带网络运营商。
            * **政务处理**：指导申请 Council Tax 免税证明，节省高额开支。
            """)
        with s_c2:
            st.markdown("""
            **文书合规与风控 (Contract & Compliance)**
            * **租房审查协助**：针对留学生无英国担保人痛点提供专业指导。
            * **合同审计**：深度解读 Tenancy Agreement，确保押金受 TDS 保护。
            """)
            st.markdown("""
            **轻松退房 (Easy Check Out)**
            * **设施检查**：协助查看验房报告，确保退房时押金全额退还。
            * **清洁安排**：协助安排深度退租清洁，长期合作，靠谱实惠。
            """)

    # --- TAB 3: 关于我们 (完全还原你的原始文案) ---
    with tabs[2]:
        st.markdown("### 👤 为什么选择 Hao Harbour？")
        st.info("""
        * **【名校精英视角】** 创始人拥有 **UCL（伦敦大学学院）本硕学历**，以校友身份深切理解留学生对学区安全及环境的严苛需求。
        * **【行业巨头背景】** 曾任职于全球房产咨询五大行之一，财富500强公司的 **JLL（仲量联行）**，引入世界级房地产专业标准与合规流程。
        * **【十载英伦深耕】** 扎根英国生活 **10余年**，提供比导航更精准的社区治安、配套及族裔分布解析。
        * **【官方战略合作】** 与众多本土管理公司建立长期稳固合作，掌握大量“独家房源”或优先配额。
        * **【金牌服务口碑】** 成功协助数百位国际留学生完成从“纸上申请”到“温馨入住”的完美过渡。
        """)

    # --- TAB 4: 联系方式 (完全还原你的原始文案) ---
    with tabs[3]:
        st.markdown("### 📞 预约您的私人顾问")
        con_c1, con_c2 = st.columns(2)
        with con_c1:
            st.markdown("**微信咨询 (WeChat)**")
            st.code("HaoHarbour", language=None)
        with con_c2:
            st.markdown("**WhatsApp**")
            st.markdown('<a href="https://wa.me/447450912493" class="wa-link">💬 点击联系咨询</a>', unsafe_allow_html=True)
