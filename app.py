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
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', str(metin))]

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

# --- OTURUM YÖNETİMİ ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

if "secili_makine_id" not in st.session_state:
    st.session_state.secili_makine_id = None

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
        
    if st.session_state.secili_makine_id:
        if st.button("⬅️ Ana Sayfaya Dön", key="side_home_btn", use_container_width=True):
            st.session_state.secili_makine_id = None
            st.rerun()

    if st.button("Çıkış Yap", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.secili_makine_id = None
        st.rerun()
    st.divider()

# --- MAKİNE LİSTESİNİ ÇEKME (VERİTABANI VE EXCEL BİRLEŞİK) ---
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
    
    # Excel varsa bilgileri zenginleştir
    if os.path.exists("iplik6MakineListesi.xlsx"):
        df_excel = pd.read_excel("iplik6MakineListesi.xlsx").fillna("")
        df_excel['excel_code'] = df_excel['MAKİNE ADI'].astype(str).str.strip() + " - " + df_excel['İŞLETME NO'].astype(str).str.strip()
        df_excel['excel_no'] = df_excel['İŞLETME NO'].astype(str).str.strip()
        
        # Kod veya isim bazlı eşleme
        merged = pd.merge(df_db, df_excel, left_on='code', right_on='excel_code', how='left')
        df_db['no'] = merged['excel_no'].fillna("")
        # Eksik markaları doldur
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
search_term = st.sidebar.text_input("Makine Adı veya No", placeholder="Örn: CER, RING, 5...").strip().lower()

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

# --- VERİTABANI İŞLEMLERİ (ÇİFT YÖNLÜ AKILLI ARAMA) ---
def load_records(machine_id, machine_code, machine_name):
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Hem gerçek machine_id'ye hem de yazı içindeki kod/isim eşleşmesine bakar
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

def load_recent_20():
    try:
        conn = get_connection()
        cur = conn.cursor()
        # Tüm kayıtları makine bilgisiyle birlikte çeker
        cur.execute("""
            SELECT 
                r.record_date AS "Tarih / Saat", 
                r.record_type AS "İşlem Türü", 
                COALESCE(m.code, '') AS "Makine",
                r.description AS "Açıklama / Müdahale", 
                r.parts_replaced AS "Değişen Parça / Kod", 
                r.technician AS "Teknisyen"
            FROM maintenance_records r
            LEFT JOIN machines m ON r.machine_id = m.id
            ORDER BY r.record_date DESC LIMIT 20;
        """)
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
        cur.close()
        conn.close()
        df = pd.DataFrame(rows, columns=colnames)
        
        # Eğer makine sütunu boşsa açıklamadan otomatik çıkarır
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

# Arama Sonuçları (Sadece kutuya yazıldığında görünür)
if search_term:
    filtreli_df = user_machines[
        user_machines['name'].str.lower().str.contains(search_term) |
        user_machines['code'].str.lower().str.contains(search_term) |
        user_machines['no'].str.lower().str.contains(search_term)
    ].copy()

    st.markdown(f"### 🔍 **'{search_term.upper()}'** Arama Sonuçları ({len(filtreli_df)} Makine Bulundu)")
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

    st.divider()

# Henüz makine seçilmemişse Ana Ekran
if not st.session_state.secili_makine_id:
    if not search_term:
        st.info("👈 İşlem yapmak için sol menüden arama yapabilir veya makine seçebilirsiniz.")
    else:
        st.info("👆 Lütfen yukarıdaki arama sonuçlarından işlem yapacağınız **makine butonuna basınız**.")
        
    st.subheader("🔔 En Son Girilen 20 Bakım & Arıza Kaydı")
    son_kayitlar = load_recent_20()
    if not son_kayitlar.empty:
        st.dataframe(son_kayitlar, use_container_width=True, hide_index=True)
    else:
        st.info("Henüz kayıt bulunmuyor.")
    st.stop()

# --- SEÇİLİ MAKİNE EKRANI ---
secili_makine_kaydi = user_machines[user_machines['id'] == st.session_state.secili_makine_id]
if secili_makine_kaydi.empty:
    st.warning("Seçilen makine bulunamadı.")
    if st.button("⬅️ Ana Sayfaya Dön", key="err_home_btn"):
        st.session_state.secili_makine_id = None
        st.rerun()
    st.stop()

m_detay = secili_makine_kaydi.iloc[0]

# Üst Başlık ve Geri Dön Butonu
col_baslik, col_buton = st.columns([3, 1])
with col_baslik:
    st.markdown(f"## 📍 Aktif Makine: **{m_detay['name']} — `{m_detay['code']}`**")
with col_buton:
    if st.button("⬅️ Ana Sayfaya Dön", key="top_home_btn", use_container_width=True):
        st.session_state.secili_makine_id = None
        st.rerun()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Marka", str(m_detay['brand']) or "-")
c2.metric("Tip / Model", f"{m_detay['machine_type']} ({m_detay['model_year']})")
c3.metric("Yerleşim", str(m_detay['location']) or "-")
c4.metric("Seri No", str(m_detay['serial_no']) or "-")

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["➕ Yeni Bakım/Arıza Girişi", "📋 Geçmiş Kayıtlar", "📥 Excel Raporu"])

# TAB 1: YENİ KAYIT
with tab1:
    st.subheader(f"{m_detay['code']} İçin Yeni Kayıt Girişi")
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
                
                # Hem machine_id hem de metin bazlı çifte kayıt
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
    st.subheader(f"{m_detay['code']} Geçmiş Bakım Kayıtları")
    kayitlar = load_records(int(m_detay['id']), m_detay['code'], m_detay['name'])
    if kayitlar.empty:
        st.info(f"{m_detay['code']} için henüz bir arıza kaydı bulunmuyor.")
    else:
        # Metindeki [KOD] başlığını temizleyip sade gösterir
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
    st.subheader("Kayıtları İndir")
    kayitlar = load_records(int(m_detay['id']), m_detay['code'], m_detay['name'])
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

# Sayfa Altı Geri Dön Butonu
st.divider()
if st.button("⬅️ Ana Sayfaya Dön (Son 20 Kayıt)", key="bottom_home_btn", use_container_width=True):
    st.session_state.secili_makine_id = None
    st.rerun()
