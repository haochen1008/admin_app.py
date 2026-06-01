import streamlit as st
import gspread
from google.oauth2 import service_account
import pandas as pd
import urllib.parse
import requests

# --- 1. 页面配置与 CSS ---
st.set_page_config(page_title="Hao Harbour | London Luxury", layout="wide")

if 'page' not in st.session_state:
    st.session_state.page = 1

def reset_page():
    st.session_state.page = 1

st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] { gap: 20px; justify-content: center; }
    .stTabs [aria-selected="true"] { color: #bfa064 !important; border-bottom: 2px solid #bfa064 !important; }
    .prop-title { font-weight: bold; font-size: 18px; color: #1a1a1a; margin: 5px 0; }
    .prop-price { color: #bfa064; font-size: 22px; font-weight: bold; }
    .prop-date { font-size: 12px; color: #999; margin-bottom: 10px; }
    .wa-link { background-color: #25D366 !important; color: white !important; text-align: center; padding: 10px; border-radius: 8px; font-weight: bold; text-decoration: none; display: block; }
    #MainMenu, footer, .stAppDeployButton, [data-testid="stToolbar"] {visibility: hidden; display: none !important;}
    </style>
""", unsafe_allow_html=True)

# --- 2. 数据库连接（修复：安全读取 + 实时刷新）---
EXPECTED_HEADERS = ["date", "title", "region", "rooms", "price",
                    "poster-link", "description", "views", "is_featured",
                    "station", "walkingMinutes", "lat", "lng"]

def _get_worksheet():
    """建立 Google Sheets 连接（不缓存，每次调用都是新鲜连接）。"""
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        gc = gspread.authorize(creds)
        return gc.open("Hao_Harbour_DB").get_worksheet(0)
    except Exception as e:
        st.error(f"数据库连接失败: {e}")
        return None

@st.cache_data(ttl=30, show_spinner=False)   # 缓存数据30秒，新房源最多30秒后自动出现
def _fetch_records():
    """读取 Sheet 所有数据，结果缓存30秒。"""
    ws = _get_worksheet()
    if ws is None:
        return []
    try:
        return ws.get_all_records(expected_headers=EXPECTED_HEADERS)
    except Exception:
        pass
    try:
        all_values = ws.get_all_values()
        if not all_values:
            return []
        raw_headers = all_values[0]
        col_indices = []
        seen = set()
        for idx, h in enumerate(raw_headers):
            if h and h in EXPECTED_HEADERS and h not in seen:
                col_indices.append((idx, h))
                seen.add(h)
        records = []
        for row in all_values[1:]:
            record = {h: (row[idx] if idx < len(row) else "") for idx, h in col_indices}
            if any(v for v in record.values()):
                records.append(record)
        return records
    except Exception as e:
        st.error(f"读取房源数据失败: {e}")
        return []

def get_data():
    """返回 (DataFrame, worksheet)。worksheet 用于写浏览量。"""
    records = _fetch_records()
    ws = _get_worksheet()   # 用于写操作（update_cell）
    if not records:
        return pd.DataFrame(), ws
    return pd.DataFrame(records), ws

# --- 3. 详情弹窗 ---
@st.dialog("Property Details")
def show_details(item, ws, row_idx, df=None):
    img_url = item.get('poster-link', '')
    if img_url:
        st.image(img_url, use_container_width=True)
        try:
            resp = requests.get(img_url, timeout=10)
            st.download_button(label="📥 下载海报", data=resp.content,
                               file_name=f"Hao_{item['title']}.jpg",
                               mime="image/jpeg", use_container_width=True)
        except: pass

    st.markdown(f"## {item['title']}")
    st.markdown(f"📅 **发布日期**: {item.get('date', '近期')}")

    c1, c2, c3 = st.columns(3)
    try:
        rmb_price = int(float(item['price'])) * 9.2
        c1.metric("月租", f"£{item['price']}", f"约合 ¥{rmb_price:,.0f}/月", delta_color="off")
    except:
        c1.metric("月租", f"£{item['price']}")
    c2.metric("区域", item['region'])
    c3.metric("户型", item['rooms'])

    st.markdown("---")
    st.markdown("### 📜 房源亮点")
    raw_desc = str(item.get('description', ''))
    formatted_desc = raw_desc.replace('✓', '\n✓').strip()
    st.info("💡 点击下方框内右上角一键复制：")
    st.code(formatted_desc, language=None)

    st.markdown("---")
    st.markdown("### 🗺️ 位置周边概览")
    m_q = urllib.parse.quote(item['title'] + " London")
    map_html = f'<iframe width="100%" height="300" frameborder="0" style="border:0; border-radius: 8px; margin-bottom: 5px;" src="https://maps.google.com/maps?q={m_q}&t=&z=14&ie=UTF8&iwloc=&output=embed" allowfullscreen></iframe>'
    st.markdown(map_html, unsafe_allow_html=True)
    st.link_button("📍 跳转 Google Maps 导航", f"https://www.google.com/maps/search/{m_q}", use_container_width=True)

    st.markdown("### 📱 预约咨询")
    cl, cr = st.columns(2)
    with cl:
        st.markdown("**微信**")
        st.code("HaoHarbour", language=None)
    with cr:
        wa_url = f"https://wa.me/447450912493?text=Interested in {item['title']}"
        st.markdown(f'<a href="{wa_url}" class="wa-link">💬 WhatsApp</a>', unsafe_allow_html=True)

    try:
        new_v = int(item.get('views', 0)) + 1
        ws.update_cell(row_idx, 8, new_v)
    except: pass

    if df is not None:
        similar = df[(df['region'] == item['region']) & (df['title'] != item['title'])]
        if not similar.empty:
            st.markdown("---")
            st.markdown("### 💡 您可能还会喜欢 (Similar Properties)")
            s_cols = st.columns(3)
            for j, (_, s_row) in enumerate(similar.head(3).iterrows()):
                with s_cols[j % 3]:
                    s_url = s_row.get('poster-link', '')
                    if s_url: st.image(s_url, use_container_width=True)
                    t_short = s_row['title'][:25] + ".." if len(s_row['title']) > 25 else s_row['title']
                    st.markdown(f"**{t_short}**")
                    st.markdown(f"<span style='color:#bfa064;font-weight:bold;'>£{s_row['price']}</span>", unsafe_allow_html=True)

# --- 4. 主程序 ---
st.markdown("<h1 style='text-align:center; color:#1a1a1a; font-family:serif; font-size:42px;'>HAO HARBOUR</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#bfa064; letter-spacing:5px; font-size:12px;'>EXCLUSIVE LONDON LIVING</p>", unsafe_allow_html=True)

# 手动刷新按钮（强制清除缓存，立刻获取最新房源）
col_refresh, _ = st.columns([1, 5])
if col_refresh.button("🔄 刷新房源", help="点击立刻获取最新房源"):
    st.cache_data.clear()
    st.rerun()

df, worksheet = get_data()

if df.empty:
    st.warning("暂时无法加载房源数据，请稍后刷新页面重试。")
    st.stop()

# 确保 is_featured 是数字
df['is_featured'] = pd.to_numeric(df.get('is_featured', 0), errors='coerce').fillna(0).astype(int)

tabs = st.tabs(["🏠 房源精选", "🛠️ 我们的服务", "👤 关于我们", "📞 联系方式"])

# --- TAB 1: 房源精选 ---
with tabs[0]:
    featured_df = df[df['is_featured'] == 1].copy()
    if not featured_df.empty:
        st.markdown("### 🌟 精选独家房源 (Featured Lettings)")
        f_cols = st.columns(3)
        for i, (idx, row) in enumerate(featured_df.head(3).iterrows()):
            with f_cols[i % 3]:
                with st.container(border=True):
                    p_url = row.get('poster-link', '')
                    if p_url: st.image(p_url, use_container_width=True)
                    st.markdown(f'<div class="prop-title">{row["title"]}</div>', unsafe_allow_html=True)
                    try:
                        rmb = int(float(row["price"] or 0)) * 9.2
                        st.markdown(f'<div class="prop-price">£{row["price"]} /mo <span style="font-size:12px;color:#999;">(约¥{rmb:,.0f})</span></div>', unsafe_allow_html=True)
                    except:
                        st.markdown(f'<div class="prop-price">£{row["price"]} /mo</div>', unsafe_allow_html=True)
                    if st.button("详情", key=f"f_btn_{idx}_{i}", use_container_width=True):
                        show_details(row, worksheet, idx + 2, df)
        st.markdown("---")
        st.markdown("### 🏠 房源大厅")

    s1, s2 = st.columns(2)
    sort_by = s1.selectbox("排序维度", ["发布时间", "租金价格"], index=0, on_change=reset_page)
    sort_order = s2.selectbox("排序方式", ["从新到旧 (Newest) / 从高到低 (Highest)", "从旧到新 (Oldest) / 从低到高 (Lowest)"], index=0, on_change=reset_page)

    with st.expander("🔍 高级筛选与搜索", expanded=False):
        search_q = st.text_input("输入楼盘、地铁站关键词...", "", on_change=reset_page).lower()
        f1, f2, f3 = st.columns(3)
        sel_reg  = f1.multiselect("区域", options=sorted(df['region'].dropna().unique()), on_change=reset_page)
        sel_room = f2.multiselect("户型", options=sorted(df['rooms'].dropna().unique()),  on_change=reset_page)
        max_p    = f3.slider("预算上限 (£)", 1000, 15000, 15000, on_change=reset_page)

    f_df = df.copy()
    if search_q:
        f_df = f_df[
            f_df['title'].astype(str).str.lower().str.contains(search_q, na=False) |
            f_df['description'].astype(str).str.lower().str.contains(search_q, na=False)
        ]
    if sel_reg:  f_df = f_df[f_df['region'].isin(sel_reg)]
    if sel_room: f_df = f_df[f_df['rooms'].isin(sel_room)]

    f_df['p_num'] = pd.to_numeric(f_df['price'], errors='coerce').fillna(0)
    f_df = f_df[f_df['p_num'] <= max_p]
    f_df['date'] = pd.to_datetime(f_df['date'], errors='coerce')

    is_asc = ("从旧到新" in sort_order)
    if sort_by == "发布时间":
        f_df = f_df.sort_values(by=['is_featured', 'date'],  ascending=[False, is_asc])
    else:
        f_df = f_df.sort_values(by=['is_featured', 'p_num'], ascending=[False, is_asc])

    if len(f_df) == 0:
        st.info("🏡 **暂无完全匹配的公开房源。**\n\nHao Harbour 掌握大量伦敦独家 Off-Market 房源，请直接联系我们的私人顾问（微信：**HaoHarbour**）获取为您量身定制的专属推荐。")
    else:
        ITEMS_PER_PAGE = 8
        total_pages = max(1, (len(f_df) - 1) // ITEMS_PER_PAGE + 1)
        if st.session_state.page > total_pages:
            st.session_state.page = 1
        start_idx = (st.session_state.page - 1) * ITEMS_PER_PAGE
        page_df = f_df.iloc[start_idx:start_idx + ITEMS_PER_PAGE]

        st.markdown(f"共有 **{len(f_df)}** 套符合条件的房源，当前显示第 **{st.session_state.page} / {total_pages}** 页")
        cols = st.columns(3)
        for i, (idx, row) in enumerate(page_df.iterrows()):
            with cols[i % 3]:
                with st.container(border=True):
                    p_url = row.get('poster-link', '')
                    if p_url: st.image(p_url, use_container_width=True)
                    st.markdown(f'<div class="prop-title">{row["title"]}</div>', unsafe_allow_html=True)
                    try:
                        rmb = int(float(row["price"] or 0)) * 9.2
                        st.markdown(f'<div class="prop-price">£{row["price"]} /mo <span style="font-size:12px;color:#999;">(约¥{rmb:,.0f})</span></div>', unsafe_allow_html=True)
                    except:
                        st.markdown(f'<div class="prop-price">£{row["price"]} /mo</div>', unsafe_allow_html=True)
                    d_val = row['date'].strftime('%Y-%m-%d') if pd.notnull(row['date']) else "近期"
                    st.markdown(f'<div class="prop-date">📍 {row["region"]} | 🗓️ {d_val}</div>', unsafe_allow_html=True)
                    if st.button("详情", key=f"btn_{idx}_{i}", use_container_width=True):
                        show_details(row, worksheet, idx + 2, df)

        st.markdown("---")
        p_c1, p_c2, p_c3 = st.columns([1, 2, 1])
        with p_c1:
            if st.button("⬅️ 上一页", disabled=(st.session_state.page <= 1), use_container_width=True):
                st.session_state.page -= 1
                st.rerun()
        with p_c2:
            st.markdown(f"<div style='text-align:center;padding-top:10px;'>第 <b>{st.session_state.page}</b> 页 / 共 <b>{total_pages}</b> 页</div>", unsafe_allow_html=True)
        with p_c3:
            if st.button("下一页 ➡️", disabled=(st.session_state.page >= total_pages), use_container_width=True):
                st.session_state.page += 1
                st.rerun()

# --- TAB 2: 我们的服务 ---
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

# --- TAB 3: 关于我们 ---
with tabs[2]:
    st.markdown("### 👤 为什么选择 Hao Harbour？")
    st.info("""
    * **【名校精英视角】** 创始人拥有 **UCL（伦敦大学学院）本硕学历**，以校友身份深切理解留学生对学区安全及环境的严苛需求。
    * **【行业巨头背景】** 曾任职于全球房产咨询五大行之一，财富500强公司的 **JLL（仲量联行）**，引入世界级房地产专业标准与合规流程。
    * **【十载英伦深耕】** 扎根英国生活 **10余年**，提供比导航更精准的社区治安、配套及族裔分布解析。
    * **【官方战略合作】** 与众多本土管理公司建立长期稳固合作，掌握大量"独家房源"或优先配额。
    * **【金牌服务口碑】** 成功协助数百位国际留学生完成从"纸上申请"到"温馨入住"的完美过渡。
    """)

# --- TAB 4: 联系方式 ---
with tabs[3]:
    st.markdown("### 📞 预约您的私人顾问")
    con_c1, con_c2 = st.columns(2)
    with con_c1:
        st.markdown("**微信咨询 (WeChat)**")
        st.code("HaoHarbour", language=None)
    with con_c2:
        st.markdown("**WhatsApp**")
        st.markdown('<a href="https://wa.me/447450912493" class="wa-link">💬 点击联系咨询</a>', unsafe_allow_html=True)
