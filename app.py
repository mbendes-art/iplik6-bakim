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

# Arayüzü kilitlemeyen sadeleştirilmiş stil
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

# --- DOĞAL SAYISAL SIRALAMA FONKSİYONU ---
def dogal_sirala(metin):
    """Metin içindeki sayıları sayısal olarak sıralar (RING-2, RING-10'dan önce gelir)."""
    return [int(parca) if parca.isdigit() else parca.lower() for parca in re.split(r'(\d+)', str(metin))]

# --- KULLANICI LİSTELERİ VE YETKİLER ---
ORTAK_SIFRE = "iplik6"

TAM_YETKILI_YONETICILER = [
    "mbendes", "ahmet", "r_şahin", "r_sahin", "n_ertürk", "n_erturk", "g_albayrak"
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

# Filtre Anahtar Kelimeleri
IHZARAT_KELIMELERI = [
    "UNIFLOC", "UNICLEAN", "UNIMİX", "UNISTORE", "KONDENSER",
    "VSI", "TELEF", "TARAK", "CER", "OMEGALLAP", "SERVOLAB",
    "PENYE", "RSB-CER", "FİTİL"
]

RING_BOBIN_KELIMELERI = ["RING", "BOBİN", "BOBIN", "PAKETLEME"]

# --- OTURUM (LOGIN) YÖNETİMİ ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

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
            if username in YETKILI_KULLANICILAR and (password == ORTAK_SIFRE or password == "iplik123"):
                st.session_state.logged_in = True
                st.session_state.username = username
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
    else:
        st.info("🏭 Yetki Alanı: **Operasyon**")
        
    if st.button("Çıkış Yap"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()
    st.divider()

# --- MAKİNE LİSTESİNİ OKUMA (EXCEL VEYA VERİTABANI) ---
@st.cache_data(ttl=60)
def load_all_machines():
    if os.path.exists("iplik6MakineListesi.xlsx"):
        df_excel = pd.read_excel("iplik6MakineListesi.xlsx")
        df_excel = df_excel.fillna("")
        df = pd.DataFrame()
        df['name'] = df_excel['MAKİNE ADI'].astype(str).str.strip()
        df['code'] = df_excel['MAKİNE ADI'].astype(str).str.strip() + " - " + df_excel['İŞLETME NO'].astype(str).str.strip()
        df['brand'] = df_excel['MARKA'].astype(str).str.strip()
        df['model_year'] = df_excel['MODEL'].astype(str).str.replace(".0", "", regex=False).str.strip()
        df['machine_type'] = df_excel['TYPE'].astype(str).str.strip()
        df['serial_no'] = df_excel['MAKİNE NO'].astype(str).str.strip()
        df['location'] = "İşletme No: " + df_excel['İŞLETME NO'].astype(str).str.strip()
        df['id'] = range(1, len(df) + 1)
        return df
    else:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, code, name, location, machine_type, serial_no, brand, model_year FROM machines ORDER BY name, code")
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
        cur.close()
        conn.close()
        return pd.DataFrame(rows, columns=colnames)

all_machines = load_all_machines()

# Kullanıcı Yetkisine Göre Filtreleme
user = st.session_state.username
if user in IHZARAT_KULLANICILARI:
    regex_pattern = "|".join(IHZARAT_KELIMELERI)
    user_machines = all_machines[all_machines['name'].str.upper().str.contains(regex_pattern, na=False)].copy()
elif user in RING_BOBIN_KULLANICILARI:
    regex_pattern = "|".join(RING_BOBIN_KELIMELERI)
    user_machines = all_machines[all_machines['name'].str.upper().str.contains(regex_pattern, na=False)].copy()
else:
    user_machines = all_machines.copy()

# Arama Filtresi
st.sidebar.header("Makine Seçimi")
search_term = st.sidebar.text_input("🔍 Hızlı Arama", placeholder="Makine adı, no...").strip().lower()

if search_term:
    user_machines = user_machines[
        user_machines['name'].str.lower().str.contains(search_term) |
        user_machines['code'].str.lower().str.contains(search_term)
    ]

if user_machines.empty:
    st.warning("Erişim yetkiniz dahilinde eşleşen makine bulunamadı.")
    st.stop()

# Doğal Sıralı Seçim Listesi Oluşturma
user_machines['secim_adi'] = user_machines['name'] + " (" + user_machines['code'] + ")"
sirali_makineler = sorted(user_machines['secim_adi'].unique(), key=dogal_sirala)

secenekler = dict(zip(user_machines['secim_adi'], user_machines['id']))

secilen_isim = st.sidebar.selectbox("Makine Listesi", sirali_makineler)
secilen_id = secenekler[secilen_isim]
m_detay = user_machines[user_machines['id'] == secilen_id].iloc[0]

# --- VERİTABANI İŞLEMLERİ (KAYITLAR) ---
def load_records(machine_code):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, record_date, record_type, description, parts_replaced, technician 
            FROM maintenance_records 
            WHERE parts_replaced ILIKE %s OR description ILIKE %s
            ORDER BY record_date DESC LIMIT 50
        """, (f"%{machine_code}%", f"%{machine_code}%"))
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
        cur.execute("""
            SELECT record_date AS "Tarih / Saat", record_type AS "İşlem Türü", 
                   description AS "Açıklama / Makine", parts_replaced AS "Değişen Parça / Kod", technician AS "Teknisyen"
            FROM maintenance_records 
            ORDER BY record_date DESC LIMIT 20;
        """)
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]
        cur.close()
        conn.close()
        return pd.DataFrame(rows, columns=colnames)
    except:
        return pd.DataFrame()

# --- ANA EKRAN ---
st.title("🧵 İplik-6 | Arıza & Bakım Takip Portalı")

# Son 20 Kayıt Özeti
with st.expander("🔔 En Son Girilen 20 Kayıt (Genel Bakış)", expanded=False):
    son_kayitlar = load_recent_20()
    if son_kayitlar.empty:
        st.info("Henüz arıza veya bakım kaydı bulunmuyor.")
    else:
        st.dataframe(son_kayitlar, use_container_width=True, hide_index=True)

st.divider()

# Seçili Makine Detayı
st.markdown(f"### 📍 {m_detay['name']} — `{m_detay['code']}`")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Marka", str(m_detay['brand']) or "-")
c2.metric("Tip / Model", f"{m_detay['machine_type']} ({m_detay['model_year']})")
c3.metric("Yerleşim", str(m_detay['location']) or "-")
c4.metric("Seri No", str(m_detay['serial_no']) or "-")

st.divider()

tab1, tab2, tab3 = st.tabs(["📋 Geçmiş Kayıtlar", "➕ Yeni Bakım/Arıza Girişi", "📥 Excel Raporu"])

with tab1:
    kayitlar = load_records(m_detay['code'])
    if kayitlar.empty:
        st.info(f"{m_detay['code']} için kayıt bulunamadı.")
    else:
        st.dataframe(kayitlar.drop(columns=['id', 'parts_replaced']), use_container_width=True)

with tab2:
    st.subheader("Yeni Kayıt Ekle")
    with st.form("yeni_kayit_formu", clear_on_submit=True):
        col_tarih, col_saat = st.columns(2)
        girilen_tarih = col_tarih.date_input("İşlem Tarihi", value=datetime.date.today())
        girilen_saat = col_saat.time_input("İşlem Saati", value=datetime.datetime.now().time())

        islem_turu = st.selectbox(
            "İşlem Türü", 
            ["Arıza Onarımı", "Periyodik Bakım", "Parça Değişimi", "Garnitür / Planga Ayarı", "Temizlik / Yağlama", "Sensör / Elektronik"]
        )
        aciklama = st.text_area("Yapılan İşlem / Arıza Sebebi", placeholder="Arıza detayını yazın...")
        parcalar = st.text_input("Değişen Parça Bilgisi", placeholder="Parça adı veya kodu...")
        teknisyen = st.text_input("Müdahaleyi Yapan", value=st.session_state.username)

        kaydet = st.form_submit_button("💾 Kaydı Buluta İşle", use_container_width=True)
        if kaydet:
            if not aciklama.strip():
                st.error("Lütfen açıklama girin!")
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
                st.success("Kayıt başarıyla işlendi!")
                st.rerun()

with tab3:
    st.subheader("Rapor İndir")
    kayitlar = load_records(m_detay['code'])
    if kayitlar.empty:
        st.info("Kayıt bulunmuyor.")
    else:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            kayitlar.to_excel(writer, index=False, sheet_name="Gecmis")
        st.download_button("📊 Excel İndir (.xlsx)", data=buffer.getvalue(), file_name=f"{m_detay['code']}_Rapor.xlsx", use_container_width=True)
