import streamlit as st
import psycopg2
import pandas as pd
import datetime
import io
import os
import warnings

warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

# Sayfa Yapılandırması
st.set_page_config(
    page_title="İplik-6 Bakım Yönetimi",
    page_icon="🧵",
    layout="wide"
)

# Streamlit menü ve alt bilgi ögelerini gizleme
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .viewerBadge_container__1QSob {display: none;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- VERİTABANI BAĞLANTISI ---
DB_URI = "postgresql://postgres.ahvsruxighjrbwbepqej:iplik6-bakim@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

def get_connection():
    return psycopg2.connect(DB_URI)

# --- ORTAK ŞİFRE VE KULLANICI YETKİ GRUPLARI ---
ORTAK_SIFRE = "iplik6"

TAM_YETKILI_YONETICILER = [
    "mbendes",
    "ahmet",
    "r_şahin", "r_sahin",
    "n_ertürk", "n_erturk",
    "g_albayrak"
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

IHZARAT_MAKINELERI = [
    "UNIFLOC", "UNICLEAN", "UNIMİX", "UNISTORE", "KONDENSER",
    "VSI", "TELEF", "TARAK", "CER", "OMEGALLAP", "SERVOLAB",
    "PENYE", "RSB-CER", "FİTİL"
]

RING_BOBIN_MAKINELERI = [
    "RING", "BOBİN", "BOBIN", "PAKETLEME"
]

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

# --- GİRİŞ YAPILDIKTAN SONRAKİ PANEL ---
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=150)
    elif os.path.exists("logo.jpg"):
        st.image("logo.jpg", width=150)
        
    st.write(f"👤 Aktif Kullanıcı: **{st.session_state.username}**")
    
    if st.session_state.username in TAM_YETKILI_YONETICILER:
        st.success("🏭 Yetki: **Tüm Fabrika (Tam Yetki)**")
    elif st.session_state.username in IHZARAT_KULLANICILARI:
        st.info("🏭 Yetki Alanı: **İhzarat Bölümü**")
    elif st.session_state.username in RING_BOBIN_KULLANICILARI:
        st.info("🏭 Yetki Alanı: **Ring & Bobin**")
    else:
        st.info("🏭 Yetki Alanı: **Operasyon**")
        
    if st.button("Çıkış Yap"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()
    st.divider()

def load_machines(query=""):
    conn = get_connection()
    sql = "SELECT id, code, name, location, machine_type, serial_no, brand, model_year FROM machines WHERE 1=1"
    params = []
    
    if st.session_state.username in IHZARAT_KULLANICILARI:
        filtreler = " OR ".join(["name ILIKE %s OR code ILIKE %s" for _ in IHZARAT_MAKINELERI])
        sql += f" AND ({filtreler})"
        for m in IHZARAT_MAKINELERI:
            params.extend([f"%{m}%", f"%{m}%"])

    elif st.session_state.username in RING_BOBIN_KULLANICILARI:
        filtreler = " OR ".join(["name ILIKE %s OR code ILIKE %s" for _ in RING_BOBIN_MAKINELERI])
        sql += f" AND ({filtreler})"
        for m in RING_BOBIN_MAKINELERI:
            params.extend([f"%{m}%", f"%{m}%"])

    if query:
        sql += " AND (code ILIKE %s OR name ILIKE %s OR location ILIKE %s OR machine_type ILIKE %s)"
        q = f"%{query}%"
        params.extend([q, q, q, q])
        
    sql += " ORDER BY name, code"
    
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    colnames = [desc[0] for desc in cur.description]
    df = pd.DataFrame(rows, columns=colnames)
    cur.close()
    conn.close()
    return df

def load_records(machine_id):
    conn = get_connection()
    sql = """
        SELECT id, record_date, record_type, description, parts_replaced, technician 
        FROM maintenance_records 
        WHERE machine_id = %s 
        ORDER BY record_date DESC
    """
    cur = conn.cursor()
    cur.execute(sql, (machine_id,))
    rows = cur.fetchall()
    colnames = [desc[0] for desc in cur.description]
    df = pd.DataFrame(rows, columns=colnames)
    cur.close()
    conn.close()
    return df

def load_recent_20_records():
    conn = get_connection()
    sql = """
        SELECT 
            m.name AS "Makine Adı",
            m.code AS "Makine Kodu",
            r.record_date AS "Tarih / Saat",
            r.record_type AS "İşlem Türü",
            r.description AS "Müdahale Açıklaması",
            r.parts_replaced AS "Değişen Parça",
            r.technician AS "Teknisyen"
        FROM maintenance_records r
        JOIN machines m ON r.machine_id = m.id
        WHERE 1=1
    """
    params = []
    if st.session_state.username in IHZARAT_KULLANICILARI:
        filtreler = " OR ".join(["m.name ILIKE %s OR m.code ILIKE %s" for _ in IHZARAT_MAKINELERI])
        sql += f" AND ({filtreler})"
        for item in IHZARAT_MAKINELERI:
            params.extend([f"%{item}%", f"%{item}%"])
    elif st.session_state.username in RING_BOBIN_KULLANICILARI:
        filtreler = " OR ".join(["m.name ILIKE %s OR m.code ILIKE %s" for _ in RING_BOBIN_MAKINELERI])
        sql += f" AND ({filtreler})"
        for item in RING_BOBIN_MAKINELERI:
            params.extend([f"%{item}%", f"%{item}%"])

    sql += " ORDER BY r.record_date DESC LIMIT 20;"
    
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    colnames = [desc[0] for desc in cur.description]
    df = pd.DataFrame(rows, columns=colnames)
    cur.close()
    conn.close()
    return df

st.title("🧵 İplik-6 | Arıza & Bakım Takip Portalı")

# --- SON 20 ARIZA / BAKIM KAYDI KART ---
with st.expander("🔔 En Son Girilen 20 Bakım & Arıza Kaydı (Genel Bakış)", expanded=True):
    recent_df = load_recent_20_records()
    if recent_df.empty:
        st.info("Yetki alanınızda henüz kayıtlı bir arıza veya bakım bulunmuyor.")
    else:
        st.dataframe(recent_df, use_container_width=True, hide_index=True)

st.divider()

# Makine Arama ve Seçimi
st.sidebar.header("Makine Seçimi")
search_term = st.sidebar.text_input("🔍 Hızlı Arama", placeholder="Makine adı, kod, no...")

machines = load_machines(search_term)

if machines.empty:
    st.warning("Erişim yetkiniz dahilinde eşleşen makine bulunamadı.")
    st.stop()

machines['secim_adi'] = machines['name'] + " (" + machines['code'] + ")"
secenekler = dict(zip(machines['secim_adi'], machines['id']))

secilen_isim = st.sidebar.selectbox("Makine Listesi", list(secenekler.keys()))
secilen_id = secenekler[secilen_isim]
m_detay = machines[machines['id'] == secilen_id].iloc[0]

# Makine Bilgi Kartı
with st.container():
    st.markdown(f"### 📍 {m_detay['name']} — `{m_detay['code']}`")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Marka", m_detay['brand'] or "-")
    c2.metric("Tip / Model", f"{m_detay['machine_type'] or '-'} ({m_detay['model_year'] or '-'})")
    c3.metric("Yerleşim", m_detay['location'] or "-")
    c4.metric("Seri No", m_detay['serial_no'] or "-")

st.divider()

tab1, tab2, tab3 = st.tabs(["📋 Geçmiş Kayıtlar & Silme", "➕ Yeni Bakım/Arıza Girişi", "📥 Excel Raporu"])

# TAB 1: GEÇMİŞ VE SİLME
with tab1:
    kayitlar = load_records(secilen_id)
    if kayitlar.empty:
        st.info("Bu makineye ait henüz arıza/bakım kaydı girilmemiş.")
    else:
        st.dataframe(
            kayitlar.drop(columns=['id']).rename(columns={
                'record_date': 'Tarih / Saat',
                'record_type': 'İşlem Türü',
                'description': 'Müdahale Açıklaması',
                'parts_replaced': 'Değişen Parça',
                'technician': 'Teknisyen / Ekip'
            }), 
            use_container_width=True
        )

        with st.expander("🗑️ Hatalı Kaydı Sil"):
            silme_listesi = {
                f"{r['record_date']} | {r['record_type']} | {str(r['description'])[:35]}...": r['id']
                for _, r in kayitlar.iterrows()
            }
            secilen_silinecek = st.selectbox("Silinecek Kayıt:", list(silme_listesi.keys()))
            if st.button("Kaydı Veritabanından Sil", type="primary"):
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("DELETE FROM maintenance_records WHERE id = %s", (silme_listesi[secilen_silinecek],))
                conn.commit()
                conn.close()
                st.success("Kayıt başarıyla silindi.")
                st.rerun()

# TAB 2: YENİ KAYIT GİRİŞİ
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
        parcalar = st.text_input("Değişen Yedek Parçalar", placeholder="Parça kodu veya adı...")
        teknisyen = st.text_input("Müdahaleyi Yapan", value=st.session_state.username)

        kaydet = st.form_submit_button("💾 Kaydı Buluta İşle", use_container_width=True)
        if kaydet:
            if not aciklama.strip():
                st.error("Lütfen arıza veya işlem açıklamasını doldurun!")
            else:
                tarih_saat_str = f"{girilen_tarih.strftime('%Y-%m-%d')} {girilen_saat.strftime('%H:%M')}"
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO maintenance_records (machine_id, record_type, description, parts_replaced, technician, record_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (secilen_id, islem_turu, aciklama.strip(), parcalar.strip(), teknisyen.strip(), tarih_saat_str))
                conn.commit()
                conn.close()
                st.success("Kayıt bulut veritabanına başarıyla işlendi!")
                st.rerun()

# TAB 3: EXCEL RAPORU
with tab3:
    st.subheader("Makine Bakım Raporunu İndir")
    kayitlar = load_records(secilen_id)
    if kayitlar.empty:
        st.info("İndirilecek kayıt bulunmuyor.")
    else:
        rapor_df = kayitlar.drop(columns=['id']).rename(columns={
            'record_date': 'Tarih',
            'record_type': 'İşlem',
            'description': 'Müdahale',
            'parts_replaced': 'Değişen Parça',
            'technician': 'Teknisyen'
        })
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            rapor_df.to_excel(writer, index=False, sheet_name="Gecmis")
        
        st.download_button(
            label="📊 Excel İndir (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"{m_detay['code']}_Bakim_Raporu.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
