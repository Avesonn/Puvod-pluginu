import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import base64
import re
from datetime import datetime, timedelta

API_BASE = "https://geoapi-test.dpd.cz"
TRACKING_BASE = "https://tracking.dpd.cz/v1/parcels"

st.set_page_config(page_title="DPD GeoAPI 2.0 Dashboard", layout="wide")

# --- VLASTNÍ DPD CSS STYLY ---
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
.history-card {
    background-color: white;
    padding: 15px;
    border-radius: 8px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    margin-bottom: 15px;
    border-left: 5px solid #dc0032;
}
.status-badge {
    background-color: #f0f2f6;
    padding: 5px 10px;
    border-radius: 15px;
    font-weight: bold;
    font-size: 14px;
    color: #31333F;
}
.status-dodei {
    background-color: #d4edda !important;
    color: #155724 !important;
}
</style>
""", unsafe_allow_html=True)

# --- MASIVNÍ SEZNAM VŠECH ZEMÍ ---
COUNTRIES = {
    "Afghánistán": "AF", "Albánie": "AL", "Alžírsko": "DZ", "Andorra": "AD", "Angola": "AO", 
    "Argentina": "AR", "Arménie": "AM", "Austrálie": "AU", "Ázerbájdžán": "AZ", "Bahamy": "BS",
    "Bahrajn": "AE", "Bangladéš": "BD", "Belgie": "BE", "Bělorusko": "BY", "Bosna a Hercegovina": "BA", 
    "Brazílie": "BR", "Bulharsko": "BG", "Černá Hora": "ME", "Česká republika": "CZ", "Čína": "CN", 
    "Dánsko": "DK", "Egypt": "EG", "Ekvádor": "EC", "Estonsko": "EE", "Filipíny": "PH", "Finsko": "FI", 
    "Francie": "FR", "Gruzie": "GE", "Chorvatsko": "HR", "Indie": "IN", "Indonésie": "ID", 
    "Irsko": "IE", "Island": "IS", "Itálie": "IT", "Izrael": "IL", "Japonsko": "JP", 
    "Jižní Afrika": "ZA", "Jižní Korea": "KR", "Kanada": "CA", "Katar": "QA", "Kazachstán": "KZ", 
    "Kolumbie": "CO", "Korsika": "FR", "Kostarika": "CR", "Kuvajt": "KW", "Kypr": "CY", 
    "Lichtenštejnsko": "LI", "Litva": "LT", "Lotyšsko": "LV", "Lucembursko": "LU", "Maďarsko": "HU", 
    "Malajsie": "MY", "Malta": "MT", "Maroko": "MA", "Mexiko": "MX", "Moldavsko": "MD", 
    "Monako": "MC", "Německo": "DE", "Nigérie": "NG", "Nizozemsko": "NL", "Norsko": "NO", 
    "Nový Zéland": "NZ", "Omán": "OM", "Pákistán": "PK", "Peru": "PE", "Polsko": "PL", 
    "Portugalsko": "PT", "Rakousko": "AT", "Rumunsko": "RO", "Rusko": "RU", "Řecko": "GR", 
    "Saúdská Arábie": "SA", "Severní Irsko": "GB", "Singapur": "SG", "Slovensko": "SK", 
    "Slovinsko": "SI", "Spojené arabské emiráty": "AE", "Spojené království (UK)": "GB", 
    "Spojené státy americké (USA)": "US", "Srbsko": "RS", "Španělsko": "ES", "Švédsko": "SE", 
    "Švýcarsko": "CH", "Thajsko": "TH", "Tchaj-wan": "TW", "Tunisko": "TN", "Turecko": "TR", 
    "Ukrajina": "UA", "Uruguay": "UY", "Vatikán": "VA", "Vietnam": "VN"
}

# --- RESTRIKCE SLUŽEB DLE ZEMÍ (Odebráno DPD Dnes) ---
ALLOWED_COUNTRIES = {
    "CLASSIC": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"],
    "PRIVATE": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE"],
    "GUARANTEE": ["DE", "PL", "AT", "SK", "NL", "BE", "FR"], 
    "PICKUP": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"],
    "EXPRESS": list(COUNTRIES.values()), 
    "PNEU": ["CZ"], 
    "DPD12": ["CZ"], 
    "SHOP_TO_SHOP": ["CZ", "SK", "PL", "DE", "HR", "AT", "ES", "FR", "NL"],
    "SHOP_TO_HOME": ["CZ", "SK", "PL", "HR", "ES"],
    "RETURN": ["CZ", "SK", "DE", "PL", "AT", "HU", "FR", "ES", "SI", "NL", "BE"],
    "COLLECTION_IMPORT": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"],
    "THIRDPARTY_COLLECTION": ["CZ"]
}

# --- INICIALIZACE SESSION STATE ---
if 'api_key' not in st.session_state: st.session_state.api_key = ''
if 'tracking_api_key' not in st.session_state: st.session_state.tracking_api_key = ''
if 'addresses' not in st.session_state: st.session_state.addresses = []
if 'shipment_history' not in st.session_state: st.session_state.shipment_history = [] # Paměť vytvořených zásilek
if 'parcel_number' not in st.session_state: st.session_state.parcel_number = ''
if 'pdf_bytes' not in st.session_state: st.session_state.pdf_bytes = None
if 'dropoff_pin' not in st.session_state: st.session_state.dropoff_pin = ''
if 'needs_pickup_order' not in st.session_state: st.session_state.needs_pickup_order = False

if 'last_request_shipment' not in st.session_state: st.session_state.last_request_shipment = None
if 'last_response_shipment' not in st.session_state: st.session_state.last_response_shipment = None
if 'last_label_response' not in st.session_state: st.session_state.last_label_response = None
if 'last_pickup_response' not in st.session_state: st.session_state.last_pickup_response = None
if 'last_tracking_response' not in st.session_state: st.session_state.last_tracking_response = None

# --- POMOCNÉ FUNKCE ---
def safe_response_parse(response):
    if response is None: return "Prázdná odpověď od serveru."
    if isinstance(response, str): text = response
    else: text = response.text
    if text.strip().startswith("<!DOCTYPE") or text.strip().startswith("<html"):
        status = response.status_code if not isinstance(response, str) else 'N/A'
        return f"HTML_ERROR: Server vrátil HTML stránku místo JSONu. (HTTP {status})"
    try: return response.json()
    except Exception: return text if text.strip() else "Prázdná odpověď od serveru."

def get_human_error_message(err_data):
    err_str = json.dumps(err_data, ensure_ascii=False)
    if "Parcel range for the customer address" in err_str:
        return "Parcel range for the customer addres - chybějící číselná řada. Je třeba se obrátit na technickou podporu DPD aby Vám vytvořila novou."
    elif "dpostcode not matching with country pattern" in err_str:
        return "dpostcode not matching with country pattern NNNN - špatně zadaná adresa příjemce, konkrétně máte špatné PSČ."
    elif "Could not get routing data" in err_str:
        return "Could not get routing data - Je zvolená neplatná kombinace služeb, DPD tuto službu do dané země v API neposkytuje."
    elif "InvalidServiceCombination" in err_str and "DpdPneu" in err_str:
        return "Chybí povinná kombinace služeb. Služba DPD Pneu musí být pro úspěšné vytvoření odeslána společně s Notifikací příjemci."
    return None

def get_p_num(d):
    if isinstance(d, dict):
        if "parcelNumbers" in d and "main" in d["parcelNumbers"]: return d["parcelNumbers"]["main"]
        if "parcelNumber" in d: return d["parcelNumber"]
        for v in d.values():
            res = get_p_num(v)
            if res: return res
    elif isinstance(d, list):
        for v in d:
            res = get_p_num(v)
            if res: return res
    return None

def parse_tracking_events(data):
    """Extrahuje code a description z odpovědi tracking API."""
    try:
        events = data.get("trackingEvents", [])
        if events:
            # Zpravidla první element je ten nejnovější (aktuální stav)
            status_obj = events[0].get("status", {})
            code = status_obj.get("code", "NO_CODE")
            desc = status_obj.get("description", {}).get("cz", "Bez popisu")
            return code, desc
    except Exception:
        pass
    return "UNKNOWN", "Stav se nepodařilo načíst z událostí."

def render_address_block(prefix_key, title_text):
    st.markdown(f"### {title_text}")
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
        
    c_name = st.selectbox("Stát (Destinace):", options=list(COUNTRIES.keys()), key=f"{prefix_key}_country")
    country_code = COUNTRIES[c_name]
        
    payload_obj = {
        "info": {"name1": name, "name2": "", "contact": {"person": name, "phone": phone, "email": email}},
        "address": {"street": street, "postalCode": zip_c, "city": city, "houseNumber": house, "country": {"isoAlpha2": country_code}}
    }
    return payload_obj, country_code

# --- HLAVNÍ NAVIGACE (SIDEBAR) ---
st.sidebar.title("Navigace")
menu_selection = st.sidebar.radio("Přejít na:", ["📦 Vytvoření zásilky", "🔍 Historie a Tracking"])

# --- STRÁNKA 1: PŘIHLÁŠENÍ (VŽDY VIDITELNÉ POKUD NENÍ NAČTENO) ---
if not st.session_state.addresses:
    st.header("1. Přihlášení do API")
    st.markdown("Zadejte vaše přístupové údaje. Pro kompletní využití dashboardu doplňte i klíč pro Tracking.")
    
    col_auth1, col_auth2 = st.columns([1, 1])
    with col_auth1:
        api_key_input = st.text_input("GeoAPI Klíč (Tvorba Zásilek):", type="password", value=st.session_state.api_key)
    with col_auth2:
        tracking_key_input = st.text_input("Tracking API Klíč (Sledování stavů):", type="password", value=st.session_state.tracking_api_key)
        
    btn_login = st.button("Přihlásit a načíst profil", type="primary")

    if btn_login:
        if not api_key_input:
            st.warning("Prosím, vložte alespoň základní GeoAPI klíč pro tvorbu zásilek.")
        else:
            with st.spinner("Stahuji data o účtu..."):
                headers = {"x-api-key": api_key_input}
                try:
                    response = requests.get(f"{API_BASE}/v1/me", headers=headers)
                    parsed_res = safe_response_parse(response)
                    
                    if response.status_code == 200 and isinstance(parsed_res, dict):
                        st.session_state.api_key = api_key_input
                        st.session_state.tracking_api_key = tracking_key_input
                        parsed_addresses = []
                        
                        for cust_block in parsed_res.get("customers", []):
                            current_dsw = cust_block.get("customer", {}).get("DSW", "")
                            for addr in cust_block.get("addresses", []):
                                it4_id = addr.get("it4emId")
                                city = addr.get("address", {}).get("city", "")
                                street = addr.get("address", {}).get("street", "")
                                name = addr.get("info", {}).get("name1", "")
                                parsed_addresses.append({
                                    "dsw": current_dsw, 
                                    "it4emId": it4_id, 
                                    "label": f"{city}, {street} | {name} (DSW: {current_dsw}, ID: {it4_id})"
                                })
                                
                        st.session_state.addresses = parsed_addresses
                        st.rerun() # Refresh pro načtení UI
                    else:
                        st.error(f"Chyba při volání /me (HTTP {response.status_code})")
                        st.json(parsed_res)
                except Exception as e:
                    st.error(f"Chyba: {str(e)}")
    st.stop() # Pokud není profil, dál nepokračujeme

# --- STRÁNKA: VYTVOŘENÍ ZÁSILKY ---
if menu_selection == "📦 Vytvoření zásilky":
    
    col_left, col_right = st.columns([1, 1], gap="large")
    
    with col_left:
        st.header("2. Adresy účastníků přepravy")
        st.markdown("### Vaše adresa (Odesílatel)")
        address_dict = {str(a["it4emId"]): a for a in st.session_state.addresses}
        selected_id_str = st.selectbox("Vyberte adresu z profilu:", options=list(address_dict.keys()), format_func=lambda x: address_dict[x]["label"])
        active_dsw = address_dict[selected_id_str]["dsw"]
        active_it4emId = address_dict[selected_id_str]["it4emId"]
        
        st.markdown("<hr>", unsafe_allow_html=True)
        manual_address_data, dest_country_code = render_address_block("cust", "Adresa Zákazníka / Protistrany")
        extra_address_placeholder = st.empty()

    with col_right:
        st.header("3. Výběr Služby a Doplňků")
        
        all_service_options = {
            "CLASSIC": "DPD Classic", "PRIVATE": "DPD Private", "GUARANTEE": "DPD Guarantee",
            "EXPRESS": "DPD Express (Letecky)", "PNEU": "DPD Pneu", "DPD12": "DPD 12:00",
            "PICKUP": "DPD Pickup (Boxy/Místa)", "SHOP_TO_SHOP": "DPD Shop2Shop", 
            "SHOP_TO_HOME": "DPD Shop2Home", "RETURN": "Return (Zpětná vratka)", 
            "COLLECTION_IMPORT": "Svoz k nám (Collection/Import)",
            "THIRDPARTY_COLLECTION": "Svoz třetí straně"
        }
        
        filtered_keys = [k for k, v in all_service_options.items() if dest_country_code in ALLOWED_COUNTRIES.get(k, [])]
        available_services = {k: all_service_options[k] for k in filtered_keys}
        
        if not available_services:
            st.error("Pro zvolenou zemi aktuálně DPD API nenabízí žádné aktivní služby z tohoto Dashboardu.")
            st.stop()
            
        service_type = st.radio("Dostupné produkty pro vybraný stát:", options=list(available_services.keys()), format_func=lambda x: available_services[x], horizontal=True)
        
        is_reverse_flow = service_type in ["RETURN", "COLLECTION_IMPORT"]
        is_third_party_flow = service_type == "THIRDPARTY_COLLECTION"
        is_normal_flow = not is_reverse_flow and not is_third_party_flow
        
        if is_reverse_flow:
            st.info("🔄 **Obrácený tok:** Adresa zákazníka vlevo bude použita jako místo **Vyzvednutí**. Balík pojede k vám.")
            
        manual_receiver_tp = None
        if is_third_party_flow:
            st.info("🔄 **Tok třetí stranou:** Zákazník vlevo je Odesílatel. Nyní vyplňte, komu se má balík doručit:")
            with extra_address_placeholder.container():
                st.markdown("<hr>", unsafe_allow_html=True)
                manual_receiver_tp, tp_country_code = render_address_block("rec_tp", "Adresa Příjemce (Třetí strana)")
                dest_country_code = tp_country_code
        
        return_mode = "LABEL"
        if service_type == "RETURN":
            return_mode = st.radio("Režim vratky:", options=["LABEL", "DROP_OFF_CODE"], format_func=lambda x: "🖨️ Papírový štítek (PDF)" if x == "LABEL" else "📱 Bezštítkové podání (PIN + Aztec)", horizontal=True)

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("### Doplňkové parametry")
        
        col_srv1, col_srv2, col_srv3 = st.columns(3)
        with col_srv1: 
            cod_enabled = st.checkbox("💸 Dobírka (COD)")
        with col_srv2: 
            if service_type in ["CLASSIC", "PRIVATE", "GUARANTEE", "DPD12"] and dest_country_code == "CZ":
                swap_enabled = st.checkbox("🔄 Výměnný balík")
            else:
                swap_enabled = False
        with col_srv3: 
            ins_enabled = st.checkbox("🛡️ Připojištění")
            
        if service_type in ["CLASSIC", "PRIVATE", "DPD12"] and dest_country_code == "CZ":
            id_check = st.checkbox("👤 Ověření dokladu (ID Check)")
        else:
            id_check = False
        
        cod_amount, cod_vs, ins_amount, id_name, id_number = 0.0, "", 0.0, "", ""
        if cod_enabled:
            c_cod1, c_cod2 = st.columns(2)
            with c_cod1: cod_amount = st.number_input("Částka dobírky:", min_value=0.0, step=10.0, value=1000.0)
            with c_cod2: cod_vs = st.text_input("Variabilní symbol (COD):")
                
        if ins_enabled:
            ins_amount = st.number_input("Deklarovaná hodnota (Pojištění):", min_value=0.0, step=100.0, value=50000.0)
            
        if id_check:
            c_id1, c_id2 = st.columns(2)
            with c_id1: id_name = st.text_input("Ověřované jméno:")
            with c_id2: id_number = st.text_input("Posledních 5 znaků OP:", max_chars=5)

        st.markdown("<br>", unsafe_allow_html=True)
        disable_mps = service_type in ["PICKUP", "SHOP_TO_SHOP", "SHOP_TO_HOME", "RETURN", "COLLECTION_IMPORT", "THIRDPARTY_COLLECTION"] or swap_enabled
        if disable_mps:
            st.info("ℹ️ Pro tuto službu je vícekusová zásilka (MPS) zakázána.")
            parcel_count = 1
        else:
            parcel_count = st.number_input("Počet balíků (MPS):", min_value=1, max_value=50, value=1)
            
        col_w, col_r = st.columns(2)
        with col_w:
            max_w = 20.0 if service_type in ["PICKUP", "SHOP_TO_SHOP", "SHOP_TO_HOME"] else 31.5
            st.info(f"Váhový limit služby: max. {max_w} kg")
            parcel_weight_kg = st.number_input("Váha jednoho balíku (kg):", min_value=0.1, max_value=max_w, value=1.5, step=0.5)
            
        with col_r:
            ref1 = st.text_input("Reference zásilky (objednávka):", "OBJ-2026-999")

    # --- KROK 4: SPODNÍ BLOK ---
    st.markdown("<hr style='border: 2px solid #dc0032;'>", unsafe_allow_html=True)
    
    pickup_id = ""
    if service_type in ["PICKUP", "SHOP_TO_SHOP"]:
        st.header("📍 Výdejní místo / Box (Pro tuto službu povinné)")
        pickup_id = st.text_input("ID vybraného místa:")
        with st.expander("🌍 Zobrazit interaktivní mapu DPD Widget", expanded=True):
            components.iframe("https://api.dpd.cz/widget/latest/demo.html", height=600, scrolling=True)
        st.markdown("<br>", unsafe_allow_html=True)

    # --- ODESLÁNÍ DO API ---
    if st.button("🚀 Odeslat a vytvořit zásilku v DPD", type="primary", use_container_width=True):
        
        st.session_state.pdf_bytes = None
        st.session_state.parcel_number = ""
        st.session_state.dropoff_pin = ""
        st.session_state.needs_pickup_order = False
        
        if service_type in ["PICKUP", "SHOP_TO_SHOP"] and not pickup_id.strip():
            st.error("Musíte vyplnit ID výdejního místa z mapy!")
            st.stop()
            
        currency = "EUR"
        if dest_country_code == "CZ": currency = "CZK"
        elif dest_country_code == "HU": currency = "HUF"
        elif dest_country_code == "RO": currency = "RON"

        current_shipment_type = "Standard"
        if service_type == "RETURN": current_shipment_type = "Return"
        elif service_type == "THIRDPARTY_COLLECTION": current_shipment_type = "ThirdPartyCollection"
        elif service_type == "COLLECTION_IMPORT": 
            current_shipment_type = "Collection" if manual_address_data["address"]["country"]["isoAlpha2"] == "CZ" else "Import"

        registered_address_payload = {"it4emId": int(active_it4emId)}
        
        if is_normal_flow:
            sender_payload, receiver_payload = registered_address_payload, manual_address_data
        elif is_reverse_flow:
            sender_payload, receiver_payload = manual_address_data, registered_address_payload
        elif is_third_party_flow:
            sender_payload, receiver_payload = manual_address_data, manual_receiver_tp

        weight_grams = int(parcel_weight_kg * 1000)
        parcels_list = [{"references": {"ref1": ref1}, "weightGrams": weight_grams} for _ in range(int(parcel_count))]

        payload = [{
            "customer": {"dsw": str(active_dsw)}, 
            "deliveryOptions": {"completeness": "CompleteOnly"},
            "shipmentType": current_shipment_type, 
            "sender": sender_payload, 
            "receiver": receiver_payload,
            "references": {"ref1": ref1}, 
            "parcels": parcels_list, 
            "services": {}
        }]
        
        serv_obj = {}
        if service_type == "PRIVATE": serv_obj["notification"] = True
        elif service_type == "GUARANTEE": serv_obj["dpdGuarantee"] = True
        elif service_type == "EXPRESS": serv_obj["airExpress"] = True
        elif service_type == "PNEU": 
            serv_obj["dpdPneu"] = True
            serv_obj["notification"] = True 
        elif service_type == "DPD12": serv_obj["dpdTimeGuarantee"] = "DPD12"
        elif service_type in ["PICKUP", "SHOP_TO_SHOP"]:
            clean_id_match = re.search(r'([a-zA-Z]{2}\d+)', pickup_id.strip())
            serv_obj["pickupPoint"] = clean_id_match.group(1).upper() if clean_id_match else pickup_id.strip().upper()
            if service_type == "SHOP_TO_SHOP": serv_obj["shopToShop"] = True
            else: serv_obj["notification"] = True
        elif service_type == "SHOP_TO_HOME": serv_obj["shopToHome"] = True
        elif service_type == "RETURN": serv_obj["dpdReturn"] = True

        if swap_enabled: serv_obj["swap"] = True
        if cod_enabled:
            serv_obj["cashOnDelivery"] = {"amountCents": int(float(cod_amount) * 100), "currency": currency, "payment": "CASH_OR_CARD"}
            if cod_vs.strip(): serv_obj["cashOnDelivery"]["variableSymbol"] = cod_vs.strip()
        if ins_enabled:
            serv_obj["declaredValue"] = {"amountCents": int(float(ins_amount) * 100), "currency": currency}
        if id_check:
            serv_obj["personalIdentification"] = {"name": id_name, "personalId": id_number}

        payload[0]["services"] = serv_obj
        st.session_state.last_request_shipment = payload
        headers = {"x-api-key": st.session_state.api_key, "Content-Type": "application/json"}
        
        with st.spinner("Odesílám požadavek do DPD API..."):
            try:
                ship_res = requests.post(f"{API_BASE}/v1/shipments", headers=headers, json=payload)
                ship_data = safe_response_parse(ship_res)
                st.session_state.last_response_shipment = ship_data
                
                if ship_res.status_code not in [200, 201] or not isinstance(ship_data, (dict, list)):
                    human_msg = get_human_error_message(ship_data)
                    if human_msg: st.error(f"❌ **ZAMÍTNUTO DPD:** {human_msg}")
                    else: st.error(f"❌ DPD API zamítlo požadavek (HTTP {ship_res.status_code})")
                    if isinstance(ship_data, (dict, list)): st.json(ship_data)
                    else: st.code(str(ship_data))
                    st.stop()
                
                p_number = get_p_num(ship_data)
                if not p_number:
                    st.error("Zásilka byla založena, ale v odpovědi chybí číslo balíku.")
                    st.stop()
                    
                st.session_state.parcel_number = p_number
                
                # --- NÁSLEDNÉ AKCE (SVOZ / ŠTÍTKY) ---
                if service_type in ["COLLECTION_IMPORT", "THIRDPARTY_COLLECTION"]:
                    st.session_state.needs_pickup_order = True
                elif service_type == "RETURN" and return_mode == "DROP_OFF_CODE":
                    dropoff_res = requests.post(f"{API_BASE}/v1/parcels/{p_number}/drop-off-codes", headers=headers, json={"aztec": {"format": "PDF"}})
                    dropoff_data = safe_response_parse(dropoff_res)
                    st.session_state.last_label_response = dropoff_data
                    if dropoff_res.status_code in [200, 201] and isinstance(dropoff_data, dict):
                        st.session_state.dropoff_pin = dropoff_data.get("pin", {}).get("value", "")
                        b64 = dropoff_data.get("aztec", {}).get("value", "")
                        if b64: st.session_state.pdf_bytes = base64.b64decode(b64)
                else:
                    label_res = requests.post(f"{API_BASE}/v1/parcels/labels", headers=headers, json={"printType": "PDF", "printProperties": {"pageSize": "A6", "labelsPerPage": 1}, "parcels": [{"parcelNumber": str(p_number)}]})
                    if 'application/pdf' in label_res.headers.get('Content-Type', '').lower() or label_res.content.startswith(b'%PDF'):
                        st.session_state.pdf_bytes = label_res.content
                    else:
                        ld = safe_response_parse(label_res)
                        st.session_state.last_label_response = ld
                        if isinstance(ld, dict) and ld.get("labels"):
                            st.session_state.pdf_bytes = base64.b64decode(ld["labels"][0].get("content", ""))
                            
                # ULOŽENÍ DO HISTORIE
                customer_name = manual_address_data["info"]["name1"]
                st.session_state.shipment_history.insert(0, {
                    "parcel_number": p_number,
                    "date": datetime.now().strftime("%d. %m. %Y %H:%M"),
                    "service": all_service_options[service_type],
                    "receiver": customer_name,
                    "status_code": "NEW",
                    "status_desc": "Zásilka vytvořena (čeká na data z trackingu)"
                })
                            
            except Exception as e: 
                st.error(f"Systémová chyba: {str(e)}")

    # --- SEKCE INTERAKTIVNÍCH VÝSLEDKŮ ---
    if st.session_state.parcel_number:
        st.success(f"✅ Zásilka {st.session_state.parcel_number} byla úspěšně vytvořena a uložena do Historie!")
        
        if swap_enabled: st.info("🔄 Výměnný balík (Swap): Vygenerované PDF obsahuje odchozí i vratný štítek.")
        if st.session_state.dropoff_pin:
            st.markdown(f"**PIN kód pro zákazníka (Bezštítkové podání na pobočce):** `{st.session_state.dropoff_pin}`")
            
        if st.session_state.pdf_bytes:
            lbl = "📄 Stáhnout Aztec kód (PDF)" if service_type == "RETURN" and return_mode == "DROP_OFF_CODE" else "📄 Stáhnout PDF Štítek"
            st.download_button(lbl, data=st.session_state.pdf_bytes, file_name=f"DPD_{st.session_state.parcel_number}.pdf", mime="application/pdf", use_container_width=True)
        
        if st.session_state.needs_pickup_order:
            st.markdown("<hr>", unsafe_allow_html=True)
            st.header("🚚 Objednávka fyzického svozu kurýrem")
            date = st.date_input("Zvolte požadované datum svozu:", min_value=datetime.today(), value=datetime.today() + timedelta(days=1))
            note = st.text_input("Interní poznámka pro kurýra:", max_chars=200)
            
            if st.button("Potvrdit a zarezervovat svoz", type="primary", use_container_width=True):
                with st.spinner("Rezervuji kurýra..."):
                    p_load = [{"parcel": {"parcelNumber": str(st.session_state.parcel_number)}, "date": date.strftime("%Y-%m-%d")}]
                    if note.strip(): p_load[0]["note"] = note.strip()
                    pick_res = requests.post(f"{API_BASE}/v1/pickup-orders", headers={"x-api-key": st.session_state.api_key, "Content-Type": "application/json"}, json=p_load)
                    p_data = safe_response_parse(pick_res)
                    st.session_state.last_pickup_response = p_data
                    if pick_res.status_code in [200, 201]: st.success(f"✅ Kurýr pro svoz byl úspěšně objednán!")
                    else: st.error("Nepodařilo se zarezervovat svoz u DPD.")

# --- STRÁNKA 2: HISTORIE A TRACKING ---
elif menu_selection == "🔍 Historie a Tracking":
    st.title("🗂️ Historie vytvořených zásilek a Sledování stavů")
    
    if not st.session_state.tracking_api_key:
        st.warning("⚠️ Pro využití funkce Tracking (Sledování stavů) doplňte prosím na úvodní stránce váš Tracking API klíč.")
        
    if not st.session_state.shipment_history:
        st.info("Zatím nebyly v této relaci vytvořeny žádné zásilky.")
    else:
        # Tlačítko pro BATCH Tracking (Hromadná kontrola)
        if st.button("🔄 Zjistit data u všech zásilek (Hromadný Tracking)", type="primary"):
            if not st.session_state.tracking_api_key:
                st.error("Chybí Tracking API Klíč.")
            else:
                parcels_to_track = [p["parcel_number"] for p in st.session_state.shipment_history if p["status_code"] != "DODEI"][:90]
                if not parcels_to_track:
                    st.info("Nebyly nalezeny žádné zásilky k hromadné aktualizaci (všechny jsou buď doručené, nebo chybí historie).")
                else:
                    with st.spinner(f"Aktualizuji stavy pro {len(parcels_to_track)} zásilek..."):
                        t_headers = {"x-api-key": st.session_state.tracking_api_key, "Content-Type": "application/json"}
                        t_payload = [{"parcelNumber": p} for p in parcels_to_track]
                        
                        try:
                            t_res = requests.post(TRACKING_BASE, headers=t_headers, json=t_payload)
                            st.session_state.last_tracking_response = safe_response_parse(t_res)
                            
                            if t_res.status_code in [200, 201]:
                                t_data_list = st.session_state.last_tracking_response
                                if isinstance(t_data_list, list):
                                    for t_data in t_data_list:
                                        p_num = get_p_num(t_data)
                                        code, desc = parse_tracking_events(t_data)
                                        # Aktualizace historie
                                        for item in st.session_state.shipment_history:
                                            if item["parcel_number"] == p_num:
                                                item["status_code"] = code
                                                item["status_desc"] = desc
                                    st.success("Stavy zásilek byly úspěšně hromadně aktualizovány!")
                                else:
                                    st.warning("Odpověď API nemá očekávaný formát seznamu (List).")
                            else:
                                st.error(f"Chyba při hromadném sledování (HTTP {t_res.status_code})")
                        except Exception as e:
                            st.error(f"Systémová chyba: {str(e)}")

        st.markdown("<hr>", unsafe_allow_html=True)
        
        # Vykreslení historie zásilek
        for item in st.session_state.shipment_history:
            badge_class = "status-dodei" if item['status_code'] == "DODEI" else ""
            
            st.markdown(f"""
            <div class="history-card">
                <div style="display:flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h4 style="margin:0; color:#dc0032;">{item['parcel_number']}</h4>
                        <span style="font-size:14px; color:#555;">{item['date']} | {item['service']} | 👤 {item['receiver']}</span>
                    </div>
                    <div style="text-align: right;">
                        <div class="status-badge {badge_class}">
                            [{item['status_code']}] {item['status_desc']}
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Tlačítko pro individuální Tracking
            if st.button(f"🔍 Sledovat zásilku {item['parcel_number']}", key=f"trk_{item['parcel_number']}"):
                if not st.session_state.tracking_api_key:
                    st.error("Chybí Tracking API Klíč.")
                else:
                    with st.spinner("Zjišťuji stav zásilky..."):
                        t_headers = {"x-api-key": st.session_state.tracking_api_key}
                        try:
                            t_res = requests.get(f"{TRACKING_BASE}/{item['parcel_number']}", headers=t_headers)
                            st.session_state.last_tracking_response = safe_response_parse(t_res)
                            
                            if t_res.status_code == 200:
                                t_data = st.session_state.last_tracking_response
                                code, desc = parse_tracking_events(t_data)
                                
                                # Aktualizujeme přímo tento objekt v historii
                                item["status_code"] = code
                                item["status_desc"] = desc
                                st.rerun() # Překreslí UI s novým stavem
                            else:
                                st.error(f"Chyba sledování zásilky (HTTP {t_res.status_code})")
                        except Exception as e:
                            st.error(f"Systémová chyba: {str(e)}")


# --- TECHNICKÝ LOG A EXPORT ---
st.markdown("<br><br>", unsafe_allow_html=True)
if st.session_state.last_request_shipment or st.session_state.last_tracking_response:
    with st.expander("🛠️ Technický detail komunikace (Pro vývojáře)"):
        export_data = {
            "request_shipment": st.session_state.last_request_shipment,
            "response_shipment": st.session_state.last_response_shipment,
            "response_label": st.session_state.last_label_response,
            "response_pickup": st.session_state.last_pickup_response,
            "response_tracking": st.session_state.last_tracking_response
        }
        st.download_button("💾 Exportovat kompletní logy do JSON", data=json.dumps(export_data, indent=4, ensure_ascii=False), file_name=f"DPD_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", mime="application/json", use_container_width=True)
        
        if st.session_state.last_request_shipment:
            st.write("**Request (Tvorba Zásilky):**")
            st.json(st.session_state.last_request_shipment)
        if st.session_state.last_response_shipment:
            st.write("**Response (Tvorba Zásilky):**")
            st.json(st.session_state.last_response_shipment)
        if st.session_state.last_tracking_response:
            st.write("**Response (Tracking API):**")
            st.json(st.session_state.last_tracking_response)
