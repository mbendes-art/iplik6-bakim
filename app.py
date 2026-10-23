import streamlit as st
import psycopg2
import pandas as pd
import datetime
import io
import os
import re
import warnings

warnings.filterwarnings('ignore', category=UserWarning)

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(
    page_title="İplik-6 Bakım Yönetimi",
    page_icon="🧵",
    layout="wide"
)

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- VERİTABANI BAĞLANTISI ---
DB_URI = "postgresql://postgres.ahvsruxighjrbwbepqej:iplik6-bakim@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

def get_connection():
    return psycopg2.connect(DB_URI, connect_timeout=10)

def dogal_sirala(metin):
    """Metin içerisindeki sayıları sayısal olarak ayırarak doğal sıralama sağlar (PENYE-2, PENYE-10'dan önce gelir)."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', str(metin))]

def ana_sayfaya_don():
    st.session_state.secili_makine_id = None
    st.session_state.search_term = ""
    st.rerun()

# --- KULLANICI LİSTELERİ VE YETKİLER ---
TAM_YETKILI_YONETICILER = [
    "mbendes", "r_şahin", "r_sahin", "n_ertürk", "n_erturk", "g_albayrak"
]

IHZARAT_KULLANICILARI = [
    "a_gültekin", "a_gultekin",
    "g_gümüş", "g_gumus",
    "g_göktaş", "g_goktas",
    "a_öztürk", "a_ozturk"
]

RING_BOBIN_KULLANICILARI = [
    "a_aslan",
    "m_karahan",
    "m_bay",
    "e_candan",
    "l_yaşar", "l_yasar"
]

YETKILI_KULLANICILAR = TAM_YETKILI_YONETICILER + IHZARAT_KULLANICILARI + RING_BOBIN_KULLANICILARI + ["f_duran"]

IHZARAT_KELIMELERI = [
    "UNIFLOC", "UNICLEAN", "UNIMİX", "UNISTORE", "KONDENSER",
    "VSI", "TELEF", "TARAK", "CER", "OMEGALLAP", "SERVOLAB",
    "PENYE", "RSB-CER", "FİTİL"
]

RING_BOBIN_KELIMELERI = ["RING", "BOBİN", "BOBIN", "PAKETLEME"]

# --- KALICI OTURUM YÖNETİMİ ---
if "user" in st.query_params and st.query_params["user"] in YETKILI_KULLANICILAR:
    st.session_state.logged_in = True
    st.session_state.username = st.query_params["user"]
else:
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""

if "secili_makine_id" not in st.session_state:
    st.session_state.secili_makine_id = None

if "search_term" not in st.session_state:
    st.session_state.search_term = ""

def normalize_text(text):
    if not text:
        return ""
    text = text.strip()
    text = text.replace("İ", "i").replace("I", "ı").replace("ı", "i")
    return text.lower()

def login():
    if os.path.exists("logo.png"):
        st.image("logo.png", width=160)
    elif os.path.exists("logo.jpg"):
        st.image("logo.jpg", width=160)
        
    st.markdown("## 🔐 İplik-6 İşletmesi Yetkili Girişi")
    with st.form("login_form"):
        username = st.text_input("Kullanıcı Adı").strip().lower()
        password = st.text_input("Şifre", type="password").strip()
        submit = st.form_submit_button("Giriş Yap", use_container_width=True)

        if submit:
            norm_pass = normalize_text(password)
            if username in YETKILI_KULLANICILAR and (norm_pass == "iplik6" or norm_pass == "iplik123"):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.secili_makine_id = None
                st.session_state.search_term = ""
                st.query_params["user"] = username
                st.success("Giriş başarılı!")
                st.rerun()
            else:
                st.error("Hatalı kullanıcı adı veya şifre!")

if not st.session_state.logged_in:
    login()
    st.stop()

# --- SOL MENÜ (SIDEBAR) ---
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=140)
    elif os.path.exists("logo.jpg"):
        st.image("logo.jpg", width=140)
        
    st.write(f"👤 Aktif: **{st.session_state.username}**")
    
    if st.session_state.username in TAM_YETKILI_YONETICILER:
        st.success("🏭 Yetki: **Tüm Fabrika**")
    elif st.session_state.username in IHZARAT_KULLANICILARI:
        st.info("🏭 Yetki Alanı: **İhzarat**")
    elif st.session_state.username in RING_BOBIN_KULLANICILARI:
        st.info("🏭 Yetki Alanı: **Ring & Bobin**")
        
    # Her an ana sayfaya dönülebilmesi için sol menünün en üstündeki buton
    if st.session_state.secili_makine_id is not None or st.session_state.search_term:
        if st.button("⬅️ Ana Sayfaya Dön (Son 20)", key="side_home_btn", use_container_width=True, type="primary"):
            ana_sayfaya_don()

    if st.button("Çıkış Yap", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.secili_makine_id = None
        st.session_state.search_term = ""
        if "user" in st.query_params:
            del st.query_params["user"]
        st.rerun()
    st.divider()

# --- MAKİNE LİSTESİNİ ÇEKME ---
@st.cache_data(ttl=60)
def load_all_machines():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, code, name, location, machine_type, serial_no, brand, model_year FROM machines ORDER BY name, code")
    rows = cur.fetchall()
    colnames = [desc[0] for desc in cur.description]
    cur.close()
    conn.close()
    df_db = pd.DataFrame(rows, columns=colnames)
    
    if os.path.exists("iplik6MakineListesi.xlsx"):
        df_excel = pd.read_excel("iplik6MakineListesi.xlsx").fillna("")
        df_excel['excel_code'] = df_excel['MAKİNE ADI'].astype(str).str.strip() + " - " + df_excel['İŞLETME NO'].astype(str).str.strip()
        df_excel['excel_no'] = df_excel['İŞLETME NO'].astype(str).str.strip()
        
        merged = pd.merge(df_db, df_excel, left_on='code', right_on='excel_code', how='left')
        df_db['no'] = merged['excel_no'].fillna("")
        df_db['brand'] = df_db['brand'].combine_first(merged['MARKA'])
        df_db['machine_type'] = df_db['machine_type'].combine_first(merged['TYPE'])
        df_db['model_year'] = df_db['model_year'].combine_first(merged['MODEL'].astype(str).str.replace(".0", "", regex=False))
        df_db['serial_no'] = df_db['serial_no'].combine_first(merged['MAKİNE NO'].astype(str))
    else:
        df_db['no'] = ""

    return df_db

all_machines = load_all_machines()

user = st.session_state.username
if user in IHZARAT_KULLANICILARI:
    regex_pattern = "|".join(IHZARAT_KELIMELERI)
    user_machines = all_machines[all_machines['name'].str.upper().str.contains(regex_pattern, na=False)].copy()
elif user in RING_BOBIN_KULLANICILARI:
    regex_pattern = "|".join(RING_BOBIN_KELIMELERI)
    user_machines = all_machines[all_machines['name'].str.upper().str.contains(regex_pattern, na=False)].copy()
else:
    user_machines = all_machines.copy()

# Sol Arama Alanı
st.sidebar.header("🔍 Hızlı Makine Arama")
search_term = st.sidebar.text_input("Makine Adı veya No", key="search_term", placeholder="Örn: PENYE, RING, 5...").strip().lower()

if search_term:
    if st.sidebar.button("❌ Aramayı Temizle (Ana Sayfa)", key="clear_search_side", use_container_width=True):
        ana_sayfaya_don()

user_machines['secim_adi'] = user_machines['name'] + " (" + user_machines['code'] + ")"
sirali_makineler = sorted(user_machines['secim_adi'].unique(), key=dogal_sirala)
secenekler = dict(zip(user_machines['secim_adi'], user_machines['id']))

secilen_kutu = st.sidebar.selectbox(
    "Veya Listeden Seçiniz", 
    sirali_makineler, 
    index=None, 
    placeholder="Açılır listeden seç..."
)

if secilen_kutu:
    st.session_state.secili_makine_id = secenekler[secilen_kutu]

# --- VERİTABANI FONKSİYONLARI ---
def load_records(machine_id, machine_code):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, record_date, record_type, description, parts_replaced, technician 
            FROM maintenance_records 
            WHERE machine_id = %s 
               OR parts_replaced ILIKE %s 
               OR description ILIKE %s
            ORDER BY record_date DESC LIMIT 50
        """, (machine_id, f"%{machine_code}%", f"%{machine_code}%"))
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
        cur.close()
        conn.close()
        return pd.DataFrame(rows, columns=colnames)
    except:
        return pd.DataFrame()

def load_filtered_recent_20(filter_query=""):
    try:
        conn = get_connection()
        cur = conn.cursor()
        sql = """
            SELECT 
                r.record_date AS "Tarih / Saat", 
                r.record_type AS "İşlem Türü", 
                COALESCE(m.code, '') AS "Makine",
                r.description AS "Açıklama / Müdahale", 
                r.parts_replaced AS "Değişen Parça / Kod", 
                r.technician AS "Teknisyen"
            FROM maintenance_records r
            LEFT JOIN machines m ON r.machine_id = m.id
            WHERE 1=1
        """
        params = []
        if filter_query:
            sql += " AND (m.code ILIKE %s OR m.name ILIKE %s OR r.description ILIKE %s OR r.parts_replaced ILIKE %s)"
            q = f"%{filter_query}%"
            params.extend([q, q, q, q])
            
        sql += " ORDER BY r.record_date DESC LIMIT 20;"
        cur.execute(sql, params)
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
        cur.close()
        conn.close()
        df = pd.DataFrame(rows, columns=colnames)
        
        for idx, row in df.iterrows():
            if not row['Makine'] and '[' in str(row['Açıklama / Müdahale']):
                match = re.search(r'\[(.*?)\]', str(row['Açıklama / Müdahale']))
                if match:
                    df.at[idx, 'Makine'] = match.group(1)
        return df
    except:
        return pd.DataFrame()

# --- ANA EKRAN BAŞLIĞI ---
st.title("🧵 İplik-6 | Arıza & Bakım Takip Portalı")

# HIZLI ARAMA YAPILDIĞINDA
if search_term:
    filtreli_df = user_machines[
        user_machines['name'].str.lower().str.contains(search_term) |
        user_machines['code'].str.lower().str.contains(search_term) |
        user_machines['no'].str.lower().str.contains(search_term)
    ].copy()

    # DOĞAL SAYISAL SIRALAMA (1, 2, 3 ... 10, 15)
    filtreli_df['sira_anahtari'] = filtreli_df['code'].apply(dogal_sirala)
    filtreli_df = filtreli_df.sort_values(by='sira_anahtari').drop(columns=['sira_anahtari'])

    col_arama_baslik, col_arama_don = st.columns([3, 1])
    with col_arama_baslik:
        st.markdown(f"### 🔍 **'{search_term.upper()}'** Makineleri ({len(filtreli_df)} Makine Bulundu)")
    with col_arama_don:
        if st.button("⬅️ Ana Sayfaya Dön (Aramayı Kapat)", key="search_close_top", use_container_width=True, type="primary"):
            ana_sayfaya_don()

    if filtreli_df.empty:
        st.warning(f"Yetki alanınızda '{search_term}' ile eşleşen makine bulunamadı.")
    else:
        cols = st.columns(3)
        for idx, (_, row) in enumerate(filtreli_df.iterrows()):
            col = cols[idx % 3]
            is_selected = (st.session_state.secili_makine_id == row['id'])
            btn_type = "primary" if is_selected else "secondary"
            btn_label = f"⚙️ {row['code']}"
            
            if col.button(btn_label, key=f"btn_{row['id']}", type=btn_type, use_container_width=True):
                st.session_state.secili_makine_id = row['id']
                st.rerun()

    st.markdown("---")

# Henüz hiçbir makine seçilmemişse Ana Ekran
if not st.session_state.secili_makine_id:
    if search_term:
        st.subheader(f"🔔 '{search_term.upper()}' İçin Son Girilen Bakım & Arıza Kayıtları")
        son_kayitlar = load_filtered_recent_20(search_term)
    else:
        st.info("👈 İşlem yapmak için sol menüden makine adı/no aratın veya açılır listeden seçim yapın.")
        st.subheader("🔔 En Son Girilen 20 Bakım & Arıza Kaydı (Genel)")
        son_kayitlar = load_filtered_recent_20("")

    if not son_kayitlar.empty:
        st.dataframe(son_kayitlar, use_container_width=True, hide_index=True)
    else:
        st.info("Bu filtreye ait henüz kayıt bulunmuyor.")

    # Arama sayfasındayken de listenin en altında geri dönüş butonu
    if search_term:
        st.divider()
        if st.button("⬅️ Ana Sayfaya Dön (Aramayı Kapat)", key="search_close_bottom", use_container_width=True):
            ana_sayfaya_don()
    st.stop()

# --- MAKİNE SEÇİLDİĞİNDE GÖRÜNEN İŞLEM ALANI ---
secili_makine_kaydi = user_machines[user_machines['id'] == st.session_state.secili_makine_id]
if secili_makine_kaydi.empty:
    st.warning("Seçilen makine bulunamadı.")
    if st.button("⬅️ Ana Sayfaya Dön", key="err_home_btn", use_container_width=True):
        ana_sayfaya_don()
    st.stop()

m_detay = secili_makine_kaydi.iloc[0]

# EN ÜSTTE BÜYÜK DÖNÜŞ BUTONU
if st.button("⬅️ ANA SAYFAYA DÖN (SON 20 & TÜM LİSTE)", key="top_big_home_btn", use_container_width=True, type="secondary"):
    ana_sayfaya_don()

st.markdown(f"## 📍 Aktif Makine: **{m_detay['name']} — `{m_detay['code']}`**")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Marka", str(m_detay['brand']) or "-")
c2.metric("Tip / Model", f"{m_detay['machine_type']} ({m_detay['model_year']})")
c3.metric("Yerleşim", str(m_detay['location']) or "-")
c4.metric("Seri No", str(m_detay['serial_no']) or "-")

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["➕ Yeni Bakım/Arıza Girişi", "📋 Geçmiş Kayıtlar", "📥 Excel Raporu"])

# TAB 1: YENİ KAYIT
with tab1:
    c_form_title, c_form_btn = st.columns([3, 1])
    with c_form_title:
        st.subheader(f"{m_detay['code']} İçin Yeni Kayıt")
    with c_form_btn:
        if st.button("⬅️ Ana Sayfaya Dön", key="tab1_top_home", use_container_width=True):
            ana_sayfaya_don()

    with st.form("yeni_kayit_formu", clear_on_submit=True):
        col_tarih, col_saat = st.columns(2)
        girilen_tarih = col_tarih.date_input("İşlem Tarihi", value=datetime.date.today())
        girilen_saat = col_saat.time_input("İşlem Saati", value=datetime.datetime.now().time())

        islem_turu = st.selectbox(
            "İşlem Türü", 
            ["Arıza Onarımı", "Periyodik Bakım", "Parça Değişimi", "Garnitür / Planga Ayarı", "Temizlik / Yağlama", "Sensör / Elektronik"]
        )
        aciklama = st.text_area("Yapılan Müdahale / Arıza Nedeni", placeholder="Örn: Motor kayışı koptu, değiştirildi ve gergi ayarı yapıldı...")
        parcalar = st.text_input("Değişen Yedek Parça", placeholder="Örn: Kayış (SPZ 1250), Rulman 6204...")
        teknisyen = st.text_input("İşlemi Yapan Usta", value=st.session_state.username)

        kaydet = st.form_submit_button("💾 Kaydı Sisteme Kaydet", use_container_width=True, type="primary")
        if kaydet:
            if not aciklama.strip():
                st.error("Lütfen yapılan işlemi veya arızayı açıklayınız!")
            else:
                tarih_saat_str = f"{girilen_tarih.strftime('%Y-%m-%d')} {girilen_saat.strftime('%H:%M')}"
                detay_metin = f"[{m_detay['code']}] {aciklama.strip()}"
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO maintenance_records (machine_id, record_type, description, parts_replaced, technician, record_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (int(m_detay['id']), islem_turu, detay_metin, f"{m_detay['code']} | {parcalar.strip()}", teknisyen.strip(), tarih_saat_str))
                conn.commit()
                conn.close()
                st.success(f"✅ {m_detay['code']} için kayıt başarıyla işlendi!")
                st.rerun()

# TAB 2: GEÇMİŞ KAYITLAR
with tab2:
    c_tab2_title, c_tab2_btn = st.columns([3, 1])
    with c_tab2_title:
        st.subheader(f"{m_detay['code']} Geçmiş Bakım Kayıtları")
    with c_tab2_btn:
        if st.button("⬅️ Ana Sayfaya Dön", key="tab2_top_home", use_container_width=True):
            ana_sayfaya_don()

    kayitlar = load_records(int(m_detay['id']), m_detay['code'])
    if kayitlar.empty:
        st.info(f"{m_detay['code']} için henüz bir arıza kaydı bulunmuyor.")
    else:
        kayitlar_goster = kayitlar.copy()
        kayitlar_goster['description'] = kayitlar_goster['description'].str.replace(f"[{m_detay['code']}]", "", regex=False).str.strip()
        st.dataframe(
            kayitlar_goster.drop(columns=['id']).rename(columns={
                'record_date': 'Tarih / Saat',
                'record_type': 'İşlem Türü',
                'description': 'Müdahale Açıklaması',
                'parts_replaced': 'Değişen Parça',
                'technician': 'Usta / Teknisyen'
            }), 
            use_container_width=True
        )

# TAB 3: EXCEL RAPORU
with tab3:
    c_tab3_title, c_tab3_btn = st.columns([3, 1])
    with c_tab3_title:
        st.subheader("Kayıtları İndir")
    with c_tab3_btn:
        if st.button("⬅️ Ana Sayfaya Dön", key="tab3_top_home", use_container_width=True):
            ana_sayfaya_don()

    kayitlar = load_records(int(m_detay['id']), m_detay['code'])
    if kayitlar.empty:
        st.info("İndirilecek kayıt bulunmuyor.")
    else:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            kayitlar.to_excel(writer, index=False, sheet_name="Gecmis")
        st.download_button(
            "📊 Excel İndir (.xlsx)", 
            data=buffer.getvalue(), 
            file_name=f"{m_detay['code']}_Rapor.xlsx", 
            use_container_width=True
        )

# SAYFA EN ALTI DÖNÜŞ BUTONU
st.divider()
if st.button("⬅️ ANA SAYFAYA DÖN (SON 20 & TÜM LİSTE)", key="bottom_fixed_home_btn", use_container_width=True):
    ana_sayfaya_don()
