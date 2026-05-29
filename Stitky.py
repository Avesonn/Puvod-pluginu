import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import base64
import re
from datetime import datetime, timedelta

API_BASE = "https://geoapi-test.dpd.cz"

st.set_page_config(page_title="DPD GeoAPI 2.0 Dashboard", layout="wide")

# --- VLASTNÍ DPD CSS STYLY PRO DLAŽDICE ---
st.markdown("""
<style>
div[role="radiogroup"] { gap: 10px; }
div[role="radiogroup"] > label {
    border: 1.5px solid #dc0032 !important; 
    border-radius: 25px !important;
    padding: 10px 20px !important;
    background-color: white !important;
    cursor: pointer;
    transition: all 0.2s;
}
div[role="radiogroup"] > label:hover { background-color: #fff0f2 !important; }
div[role="radiogroup"] > label[data-checked="true"] { background-color: #dc0032 !important; }
div[role="radiogroup"] > label[data-checked="true"] p { color: white !important; }
div[role="radiogroup"] > label p {
    color: #dc0032 !important;
    font-weight: 500 !important;
    font-size: 15px !important;
    margin: 0 !important;
}
div[role="radiogroup"] > label div[data-baseweb="radio"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

COUNTRIES = {
    "Česká republika": "CZ", "Slovensko": "SK", "Německo": "DE", 
    "Polsko": "PL", "Rakousko": "AT", "Maďarsko": "HU", 
    "Rumunsko": "RO", "Francie": "FR", "Itálie": "IT", 
    "Španělsko": "ES", "Slovinsko": "SI", "Chorvatsko": "HR",
    "Nizozemsko": "NL", "Belgie": "BE", "Bulharsko": "BG"
}

# --- RESTRIKCE MAPOVÁNÍ SLUŽEB PODLE ZEMÍ ---
ALLOWED_COUNTRIES = {
    "CLASSIC": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"],
    "PRIVATE": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE"],
    "GUARANTEE": ["DE", "PL", "AT", "SK", "NL", "BE", "FR"], 
    "PICKUP": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"],
    "EXPRESS": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"],
    "PNEU": ["CZ"], 
    "DPD12": ["CZ"], 
    "DPDDNES": ["CZ"], 
    "SHOP_TO_SHOP": ["CZ", "SK", "PL", "DE", "HR", "AT", "ES", "FR", "NL"],
    "SHOP_TO_HOME": ["CZ", "SK", "PL", "HR", "ES"],
    "RETURN": ["CZ", "SK", "DE", "PL", "AT", "HU", "FR", "ES", "SI", "NL", "BE"],
    "COLLECTION_IMPORT": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"],
    "THIRDPARTY_COLLECTION": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"]
}

# --- INICIALIZACE SESSION STATE ---
if 'api_key' not in st.session_state: st.session_state.api_key = ''
if 'addresses' not in st.session_state: st.session_state.addresses = []
if 'parcel_number' not in st.session_state: st.session_state.parcel_number = ''
if 'pdf_bytes' not in st.session_state: st.session_state.pdf_bytes = None
if 'dropoff_pin' not in st.session_state: st.session_state.dropoff_pin = ''
if 'needs_pickup_order' not in st.session_state: st.session_state.needs_pickup_order = False
if 'last_request_shipment' not in st.session_state: st.session_state.last_request_shipment = None
if 'last_response_shipment' not in st.session_state: st.session_state.last_response_shipment = None
if 'last_pickup_response' not in st.session_state: st.session_state.last_pickup_response = None
if 'last_label_response' not in st.session_state: st.session_state.last_label_response = None

# --- POMOCNÉ FUNKCE ---
def safe_response_parse(response):
    if response is None:
        return "Prázdná odpověď od serveru."
        
    if isinstance(response, str):
        text = response
    else:
        text = response.text
        
    if text.strip().startswith("<!DOCTYPE") or text.strip().startswith("<html"):
        status = response.status_code if not isinstance(response, str) else 'N/A'
        return f"HTML_ERROR: Server vrátil HTML stránku místo JSONu. (HTTP {status})"
        
    try:
        return response.json()
    except Exception:
        if text.strip():
            return text
        else:
            return "Prázdná odpověď od serveru."

def get_human_error_message(err_data):
    """Přeloží surový DPD JSON error do detailního českého popisu."""
    err_str = json.dumps(err_data, ensure_ascii=False)
    
    if "Parcel range for the customer address" in err_str:
        return "Parcel range for the customer address - chybějící číselná řada. Je třeba se obrátit na technickou podporu DPD, aby Vám vytvořila novou."
    elif "dpostcode not matching with country pattern" in err_str:
        return "dpostcode not matching with country pattern NNNN - špatně zadaná adresa příjemce, konkrétně máte špatné PSČ."
    elif "Could not get routing data" in err_str:
        return "Could not get routing data - Je zvolená neplatná kombinace služeb, DPD tuto službu do dané země v API neposkytuje."
        
    return None

def render_address_block(prefix_key, title_text, override_country=None):
    st.header(title_text)
    name = st.text_input("Jméno a příjmení / Firma:", "Jan Novák", key=f"{prefix_key}_name")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        phone = st.text_input("Telefonní číslo:", "+420777666444", key=f"{prefix_key}_phone")
        street = st.text_input("Ulice:", "Nad Petruskou", key=f"{prefix_key}_street")
        zip_c = st.text_input("PSČ:", "12000", key=f"{prefix_key}_zip")
    with col_c2:
        email = st.text_input("E-mailová adresa:", "dpd@test.cz", key=f"{prefix_key}_email")
        house = st.text_input("Číslo popisné/orientační:", "63/1", key=f"{prefix_key}_house")
        city = st.text_input("Město:", "Praha", key=f"{prefix_key}_city")
        
    if override_country:
        country_code = override_country
    else:
        c_name = st.selectbox("Stát:", options=list(COUNTRIES.keys()), key=f"{prefix_key}_country")
        country_code = COUNTRIES[c_name]
        
    payload_obj = {
        "info": {
            "name1": name, 
            "name2": "", 
            "contact": {"person": name, "phone": phone, "email": email}
        },
        "address": {
            "street": street, 
            "postalCode": zip_c, 
            "city": city, 
            "houseNumber": house, 
            "country": {"isoAlpha2": country_code}
        }
    }
    return payload_obj

# --- KROK 1: PŘIHLÁŠENÍ ---
st.header("1. Přihlášení")
col_auth1, col_auth2 = st.columns([1, 2])
with col_auth1:
    api_key_input = st.text_input("Zadejte API Klíč (x-api-key):", type="password", value=st.session_state.api_key)
    btn_login = st.button("Načíst údaje z profilu", type="primary")

if btn_login:
    if not api_key_input:
        st.warning("Prosím, vložte platný API klíč.")
    else:
        with st.spinner("Stahuji data o účtu..."):
            headers = {"x-api-key": api_key_input}
            try:
                response = requests.get(f"{API_BASE}/v1/me", headers=headers)
                parsed_res = safe_response_parse(response)
                
                if response.status_code == 200 and isinstance(parsed_res, dict):
                    st.session_state.api_key = api_key_input
                    parsed_addresses = []
                    
                    for cust_block in parsed_res.get("customers", []):
                        current_dsw = cust_block.get("customer", {}).get("DSW", "")
                        for addr in cust_block.get("addresses", []):
                            city = addr.get('address', {}).get('city', '')
                            street = addr.get('address', {}).get('street', '')
                            name = addr.get('info', {}).get('name1', '')
                            it4_id = addr.get('it4emId')
                            
                            parsed_addresses.append({
                                "dsw": current_dsw, 
                                "it4emId": it4_id, 
                                "label": f"{city}, {street} | {name} (DSW: {current_dsw}, ID: {it4_id})"
                            })
                            
                    st.session_state.addresses = parsed_addresses
                    st.success(f"Úspěšně načteno! Nalezeno {len(parsed_addresses)} svozových adres.")
                else:
                    st.error(f"Chyba při volání /me (HTTP {response.status_code})")
                    if isinstance(parsed_res, (dict, list)):
                        st.json(parsed_res)
                    else:
                        st.code(str(parsed_res))
            except Exception as e:
                st.error(f"Chyba: {str(e)}")

st.divider()

if st.session_state.addresses:
    col_left, col_right = st.columns([4, 5], gap="large")
    
    with col_left:
        # --- KROK 2: ADRESA A DESTINACE ---
        st.header("2. Adresa a cílová destinace")
        
        address_dict = {str(a["it4emId"]): a for a in st.session_state.addresses}
        selected_id_str = st.selectbox("Registrovaný odesílatel (z DPD profilu):", options=list(address_dict.keys()), format_func=lambda x: address_dict[x]["label"])
        active_dsw = address_dict[selected_id_str]["dsw"]
        active_it4emId = address_dict[selected_id_str]["it4emId"]
        
        dest_country_name = st.selectbox("Zvolte zemi doručení / svozu:", options=list(COUNTRIES.keys()))
        dest_country_code = COUNTRIES[dest_country_name]
        
        st.markdown("<br>", unsafe_allow_html=True)
        r_name = st.text_input("Jméno a příjmení / Firma:", "Jan Novák")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            r_phone = st.text_input("Telefonní číslo:", "+420777666444")
            r_street = st.text_input("Ulice:", "Nad Petruskou")
            r_zip = st.text_input("PSČ:", "12000")
        with col_c2:
            r_email = st.text_input("E-mailová adresa:", "dpd@test.cz")
            r_house = st.text_input("Číslo popisné/orientační:", "63/1")
            r_city = st.text_input("Město:", "Praha")

        # --- KROK 3: VÝBĚR PRODUKTU / SLUŽBY ---
        st.markdown("<hr>", unsafe_allow_html=True)
        st.header("3. Výběr služby DPD")
        
        all_service_options = {
            "CLASSIC": "DPD Classic", 
            "PRIVATE": "DPD Private", 
            "GUARANTEE": "DPD Guarantee",
            "EXPRESS": "DPD Express (Letecky)", 
            "PNEU": "DPD Pneu", 
            "DPD12": "DPD 12:00",
            "DPDDNES": "DPD Dnes (Same Day)", 
            "PICKUP": "DPD Pickup (Boxy/Místa)",
            "SHOP_TO_SHOP": "DPD Shop2Shop", 
            "SHOP_TO_HOME": "DPD Shop2Home",
            "RETURN": "Return (Zpětná vratka)", 
            "COLLECTION_IMPORT": "Svoz k nám (Collection/Import)",
            "THIRDPARTY_COLLECTION": "Svoz třetí straně"
        }
        
        # Filtrujeme dostupné služby na základě zvolené země
        filtered_keys = [k for k, v in all_service_options.items() if dest_country_code in ALLOWED_COUNTRIES.get(k, [])]
        available_services = {k: all_service_options[k] for k in filtered_keys}
        
        if not available_services:
            st.error("Pro tuto zemi aktuálně nejsou v Dashboardu povoleny žádné služby.")
            st.stop()
            
        service_type = st.radio("Dostupné produkty pro vybraný stát:", options=list(available_services.keys()), format_func=lambda x: available_services[x], horizontal=True)
        
        is_reverse_flow = service_type in ["RETURN", "COLLECTION_IMPORT"]
        is_third_party_flow = service_type == "THIRDPARTY_COLLECTION"
        is_normal_flow = not is_reverse_flow and not is_third_party_flow
        
        if is_reverse_flow:
            st.warning("🔄 **Obrácený tok:** Zadaná adresa výše bude v API nastavena jako adresa **VYZVEDNUTÍ** (Sender).")
        
        return_mode = "LABEL"
        if service_type == "RETURN":
            return_mode = st.radio(
                "Režim vratky:", 
                options=["LABEL", "DROP_OFF_CODE"], 
                format_func=lambda x: "🖨️ Papírový štítek (PDF)" if x == "LABEL" else "📱 Bezštítkové podání (PIN + Aztec)", 
                horizontal=True
            )

        # --- KROK 4: ADRESNÍ BLOKY PRO OBRÁCENÉ TOKY ---
        st.markdown("<hr>", unsafe_allow_html=True)
        
        if is_normal_flow:
            manual_receiver = {
                "info": {"name1": r_name, "name2": "", "contact": {"person": r_name, "phone": r_phone, "email": r_email}},
                "address": {"street": r_street, "postalCode": r_zip, "city": r_city, "houseNumber": r_house, "country": {"isoAlpha2": dest_country_code}}
            }
            manual_sender = None
            s_cc = "CZ"
        elif is_reverse_flow:
            st.info("🔄 **Obrácený tok:** Kurýr jede pro balík na adresu níže. Zásilka pak poputuje k vám.")
            manual_sender = render_address_block("sen", "4. Adresa pro VYZVEDNUTÍ", override_country=dest_country_code)
            manual_receiver = None
            s_cc = dest_country_code
        elif is_third_party_flow:
            st.info("🔄 **Tok třetí stranou:** Platíte přes DSW, adresa Odesílatele a Příjemce je libovolná.")
            manual_sender = render_address_block("sen", "4A. Adresa pro VYZVEDNUTÍ")
            st.markdown("<br>", unsafe_allow_html=True)
            manual_receiver = render_address_block("rec", "4B. Adresa pro DORUČENÍ", override_country=dest_country_code)
            s_cc = manual_sender["address"]["country"]["isoAlpha2"]

        # --- KROK 5: DOPLŇKOVÉ SLUŽBY ---
        st.markdown("<hr>", unsafe_allow_html=True)
        st.header("5. Doplňkové parametry")
        
        col_srv1, col_srv2, col_srv3 = st.columns(3)
        with col_srv1:
            cod_enabled = st.checkbox("💸 Dobírka (COD)")
        with col_srv2:
            if service_type in ["CLASSIC", "PRIVATE", "GUARANTEE", "DPD12", "DPDDNES"] and dest_country_code == "CZ":
                swap_enabled = st.checkbox("🔄 Výměnný balík")
            else:
                swap_enabled = False
        with col_srv3:
            ins_enabled = st.checkbox("🛡️ Připojištění hodnoty")
            
        if service_type in ["CLASSIC", "PRIVATE", "DPD12"] and dest_country_code == "CZ":
            id_check = st.checkbox("👤 Ověření dokladu (ID Check)")
        else:
            id_check = False
        
        cod_amount = 0.0
        cod_vs = ""
        ins_amount = 0.0
        id_name = ""
        id_number = ""
        
        if cod_enabled:
            c_cod1, c_cod2 = st.columns(2)
            with c_cod1:
                cod_amount = st.number_input("Částka dobírky:", min_value=0.0, step=10.0, value=1000.0)
            with c_cod2:
                cod_vs = st.text_input("Variabilní symbol (COD):")
                
        if ins_enabled:
            ins_amount = st.number_input("Deklarovaná hodnota:", min_value=0.0, step=100.0, value=50000.0)
            
        if id_check:
            c_id1, c_id2 = st.columns(2)
            with c_id1:
                id_name = st.text_input("Ověřované jméno:")
            with c_id2:
                id_number = st.text_input("Posledních 5 znaků OP:", max_chars=5)

        st.markdown("<br>", unsafe_allow_html=True)
        disable_mps = False
        if service_type in ["PICKUP", "SHOP_TO_SHOP", "SHOP_TO_HOME", "RETURN", "COLLECTION_IMPORT", "THIRDPARTY_COLLECTION"] or swap_enabled:
            disable_mps = True
            
        if disable_mps:
            st.info("ℹ️ Pro tuto konfiguraci je vícekusová zásilka zakázána.")
            parcel_count = 1
        else:
            parcel_count = st.number_input("Počet balíků (MPS):", min_value=1, max_value=50, value=1)
            
        col_w, col_r = st.columns(2)
        with col_w:
             if service_type in ["PICKUP", "SHOP_TO_SHOP", "SHOP_TO_HOME"]:
                 max_w = 20.0
             else:
                 max_w = 31.5
             st.info(f"Váhový limit služby: max. {max_w} kg")
             parcel_weight_kg = st.number_input("Váha balíku (kg):", min_value=0.1, max_value=max_w, value=1.5, step=0.5)
        with col_r:
             ref1 = st.text_input("Reference zásilky (č. objednávky):", "OBJ-2026-999")

    with col_right:
        pickup_id = ""
        if service_type in ["PICKUP", "SHOP_TO_SHOP"]:
            st.header("📍 Výdejní místo / Box")
            pickup_id = st.text_input("ID vybraného místa:")
            with st.expander("🌍 Zobrazit DPD Mapu", expanded=True):
                components.iframe("https://api.dpd.cz/widget/latest/demo.html", height=700, scrolling=True)
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        # --- HLAVNÍ AKCE ---
        if st.button("🚀 Vytvořit zásilku v DPD", type="primary", use_container_width=True):
            st.session_state.pdf_bytes = None
            st.session_state.parcel_number = ""
            st.session_state.dropoff_pin = ""
            st.session_state.needs_pickup_order = False
            
            if service_type in ["PICKUP", "SHOP_TO_SHOP"] and not pickup_id.strip():
                st.error("Musíte vyplnit ID výdejního místa!")
                st.stop()
                
            currency = "EUR"
            if dest_country_code == "CZ":
                currency = "CZK"
            elif dest_country_code == "HU":
                currency = "HUF"
            elif dest_country_code == "RO":
                currency = "RON"

            current_shipment_type = "Standard"
            if service_type == "RETURN":
                current_ship
