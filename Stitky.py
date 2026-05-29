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

# --- RESTRIKCE SLUŽEB DLE ZEMÍ ---
ALLOWED_COUNTRIES = {
    "CLASSIC": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"],
    "PRIVATE": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE"],
    "GUARANTEE": ["DE", "PL", "AT", "SK", "NL", "BE", "FR"], 
    "PICKUP": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"],
    "EXPRESS": list(COUNTRIES.values()), 
    "PNEU": ["CZ"], 
    "DPD12": ["CZ"], 
    "DPDDNES": ["CZ"], 
    "SHOP_TO_SHOP": ["CZ", "SK", "PL", "DE", "HR", "AT", "ES", "FR", "NL"],
    "SHOP_TO_HOME": ["CZ", "SK", "PL", "HR", "ES"],
    "RETURN": ["CZ", "SK", "DE", "PL", "AT", "HU", "FR", "ES", "SI", "NL", "BE"],
    "COLLECTION_IMPORT": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"],
    "THIRDPARTY_COLLECTION": ["CZ"]
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
        return text if text.strip() else "Prázdná odpověď od serveru."

def get_human_error_message(err_data):
    """Plnohodnotný překlad DPD chyb do lidské češtiny s přesným zněním."""
    err_str = json.dumps(err_data, ensure_ascii=False)
    
    if "Parcel range for the customer address" in err_str:
        return "Parcel range for the customer addres - chybějící číselná řada je třeba se obrátit na technickou podporu DPD aby Vám vytvořila novou."
    elif "dpostcode not matching with country pattern" in err_str:
        return "dpostcode not matching with country pattern NNNN - špatně zadaná adresa příjemce, konkrétně máte špatné PSČ."
    elif "Could not get routing data" in err_str:
        return "Could not get routing data - Je zvolená neplatná kombinace služeb, DPD tuto službu do dané země v API neposkytuje."
        
    return None

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
    return payload_obj, country_code

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
                    st.success(f"Úspěšně načteno! Nalezeno {len(parsed_addresses)} svozových adres.")
                else:
                    st.error(f"Chyba při volání /me (HTTP {response.status_code})")
            except Exception as e:
                st.error(f"Chyba: {str(e)}")

st.divider()

if st.session_state.addresses:
    
    # --- KROK 2 A 3: DVOU-SLOUPCOVÝ LAYOUT (ADRESY VLEVO, SLUŽBY VPRAVO) ---
    col_left, col_right = st.columns([1, 1], gap="large")
    
    with col_left:
        st.header("2. Adresy účastníků přepravy")
        
        # Odesílatel z profilu DSW
        st.markdown("### Vaše adresa (Registrovaný odesílatel z DPD profilu)")
        address_dict = {str(a["it4emId"]): a for a in st.session_state.addresses}
        selected_id_str = st.selectbox("Vyberte adresu z profilu:", options=list(address_dict.keys()), format_func=lambda x: address_dict[x]["label"])
        active_dsw = address_dict[selected_id_str]["dsw"]
        active_it4emId = address_dict[selected_id_str]["it4emId"]
        
        st.markdown("<hr>", unsafe_allow_html=True)
        
        # Zákazník (Příjemce)
        manual_address_data, dest_country_code = render_address_block("cust", "Adresa Zákazníka / Protistrany")
        
        # Prostor pro případnou třetí stranu (Svoz)
        extra_address_placeholder = st.empty()

    with col_right:
        st.header("3. Výběr Služby a Doplňků")
        
        all_service_options = {
            "CLASSIC": "DPD Classic", "PRIVATE": "DPD Private", "GUARANTEE": "DPD Guarantee",
            "EXPRESS": "DPD Express (Letecky)", "PNEU": "DPD Pneu", "DPD12": "DPD 12:00",
            "DPDDNES": "DPD Dnes (Same Day)", "PICKUP": "DPD Pickup (Boxy/Místa)",
            "SHOP_TO_SHOP": "DPD Shop2Shop", "SHOP_TO_HOME": "DPD Shop2Home",
            "RETURN": "Return (Zpětná vratka)", "COLLECTION_IMPORT": "Svoz k nám (Collection/Import)",
            "THIRDPARTY_COLLECTION": "Svoz třetí straně"
        }
        
        # Filtrování služeb podle zvoleného státu u zákazníka
        filtered_keys = [k for k, v in all_service_options.items() if dest_country_code in ALLOWED_COUNTRIES.get(k, [])]
        available_services = {k: all_service_options[k] for k in filtered_keys}
        
        if not available_services:
            st.error("Pro zvolenou zemi aktuálně DPD API nenabízí žádné aktivní služby z tohoto Dashboardu.")
            st.stop()
            
        service_type = st.radio("Dostupné produkty pro vybraný stát:", options=list(available_services.keys()), format_func=lambda x: available_services[x], horizontal=True)
        
        # Určení toku dat
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
        
        # Bezštítkový Return (PIN)
        return_mode = "LABEL"
        if service_type == "RETURN":
            return_mode = st.radio("Režim vratky:", options=["LABEL", "DROP_OFF_CODE"], format_func=lambda x: "🖨️ Papírový štítek (PDF)" if x == "LABEL" else "📱 Bezštítkové podání (PIN + Aztec)", horizontal=True)

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown("### Doplňkové parametry")
        
        col_srv1, col_srv2, col_srv3 = st.columns(3)
        with col_srv1: 
            cod_enabled = st.checkbox("💸 Dobírka (COD)")
            
        with col_srv2: 
            # SWAP Omezení: Classic, Private, Guarantee, DPD12, DPDDnes pouze v ČR
            if service_type in ["CLASSIC", "PRIVATE", "GUARANTEE", "DPD12", "DPDDNES"] and dest_country_code == "CZ":
                swap_enabled = st.checkbox("🔄 Výměnný balík")
            else:
                swap_enabled = False
                
        with col_srv3: 
            ins_enabled = st.checkbox("🛡️ Připojištění")
            
        # ID Check Omezení: Classic, Private, DPD12 pouze v ČR
        if service_type in ["CLASSIC", "PRIVATE", "DPD12"] and dest_country_code == "CZ":
            id_check = st.checkbox("👤 Ověření dokladu (ID Check)")
        else:
            id_check = False
        
        # Výchozí hodnoty pro doplňky
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
            ins_amount = st.number_input("Deklarovaná hodnota (Pojištění):", min_value=0.0, step=100.0, value=50000.0)
            
        if id_check:
            c_id1, c_id2 = st.columns(2)
            with c_id1: 
                id_name = st.text_input("Ověřované jméno:")
            with c_id2: 
                id_number = st.text_input("Posledních 5 znaků OP:", max_chars=5)

        st.markdown("<br>", unsafe_allow_html=True)
        
        # Uzamknutí MPS (Vícekusu)
        disable_mps = False
        if service_type in ["PICKUP", "SHOP_TO_SHOP", "SHOP_TO_HOME", "RETURN", "COLLECTION_IMPORT", "THIRDPARTY_COLLECTION"] or swap_enabled:
            disable_mps = True
            
        if disable_mps:
            st.info("ℹ️ Pro tuto službu je vícekusová zásilka (MPS) zakázána.")
            parcel_count = 1
        else:
            parcel_count = st.number_input("Počet balíků (MPS):", min_value=1, max_value=50, value=1)
            
        col_w, col_r = st.columns(2)
        with col_w:
            # Maximální váha dle služby
            if service_type in ["PICKUP", "SHOP_TO_SHOP", "SHOP_TO_HOME"]:
                max_w = 20.0
            else:
                max_w = 31.5
                
            st.info(f"Váhový limit služby: max. {max_w} kg")
            parcel_weight_kg = st.number_input("Váha jednoho balíku (kg):", min_value=0.1, max_value=max_w, value=1.5, step=0.5)
            
        with col_r:
            ref1 = st.text_input("Reference zásilky (objednávka):", "OBJ-2026-999")

    # --- KROK 4: SPODNÍ BLOK PŘES CELOU ŠÍŘKU (MAPA, TLAČÍTKO, VÝSLEDKY) ---
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
        
        # Reset proměnných v session state před novým voláním
        st.session_state.pdf_bytes = None
        st.session_state.parcel_number = ""
        st.session_state.dropoff_pin = ""
        st.session_state.needs_pickup_order = False
        st.session_state.last_request_shipment = None
        st.session_state.last_response_shipment = None
        st.session_state.last_label_response = None
        st.session_state.last_pickup_response = None
        
        if service_type in ["PICKUP", "SHOP_TO_SHOP"] and not pickup_id.strip():
            st.error("Musíte vyplnit ID výdejního místa z mapy!")
            st.stop()
            
        # Přiřazení měny k dobírce a pojištění na základě destinace
        currency = "EUR"
        if dest_country_code == "CZ": 
            currency = "CZK"
        elif dest_country_code == "HU": 
            currency = "HUF"
        elif dest_country_code == "RO": 
            currency = "RON"

        # Překlad služby do DPD shipmentType
        current_shipment_type = "Standard"
        if service_type == "RETURN": 
            current_shipment_type = "Return"
        elif service_type == "THIRDPARTY_COLLECTION": 
            current_shipment_type = "ThirdPartyCollection"
        elif service_type == "COLLECTION_IMPORT": 
            if manual_address_data["address"]["country"]["isoAlpha2"] == "CZ":
                current_shipment_type = "Collection"
            else:
                current_shipment_type = "Import"

        # Mapování Odesílatele a Příjemce na základě toku
        registered_address_payload = {"it4emId": int(active_it4emId)}
        
        if is_normal_flow:
            sender_payload = registered_address_payload
            receiver_payload = manual_address_data
        elif is_reverse_flow:
            sender_payload = manual_address_data
            receiver_payload = registered_address_payload
        elif is_third_party_flow:
            sender_payload = manual_address_data
            receiver_payload = manual_receiver_tp

        # Sestavení balíků
        weight_grams = int(parcel_weight_kg * 1000)
        parcels_list = [{"references": {"ref1": ref1}, "weightGrams": weight_grams} for _ in range(int(parcel_count))]

        # Sestavení hlavního Payloadu
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
        
        # Konfigurace DPD Služeb do JSONu
        serv_obj = {}
        if service_type == "PRIVATE": 
            serv_obj["notification"] = True
        elif service_type == "GUARANTEE": 
            serv_obj["dpdGuarantee"] = True
        elif service_type == "EXPRESS": 
            serv_obj["airExpress"] = True
        elif service_type == "PNEU": 
            serv_obj["dpdPneu"] = True
        elif service_type == "DPD12": 
            serv_obj["dpdTimeGuarantee"] = "DPD12"
        elif service_type == "DPDDNES": 
            serv_obj["dpdTimeGuarantee"] = "SAMEDAY"
        elif service_type in ["PICKUP", "SHOP_TO_SHOP"]:
            clean_id_match = re.search(r'([a-zA-Z]{2}\d+)', pickup_id.strip())
            if clean_id_match:
                serv_obj["pickupPoint"] = clean_id_match.group(1).upper()
            else:
                serv_obj["pickupPoint"] = pickup_id.strip().upper()
                
            if service_type == "SHOP_TO_SHOP": 
                serv_obj["shopToShop"] = True
            else: 
                serv_obj["notification"] = True
        elif service_type == "SHOP_TO_HOME": 
            serv_obj["shopToHome"] = True
        elif service_type == "RETURN": 
            serv_obj["dpdReturn"] = True

        # Doplňkové služby v JSONu
        if swap_enabled: 
            serv_obj["swap"] = True
            
        if cod_enabled:
            serv_obj["cashOnDelivery"] = {
                "amountCents": int(float(cod_amount) * 100), 
                "currency": currency, 
                "payment": "CASH_OR_CARD"
            }
            if cod_vs.strip(): 
                serv_obj["cashOnDelivery"]["variableSymbol"] = cod_vs.strip()
                
        if ins_enabled:
            serv_obj["declaredValue"] = {
                "amountCents": int(float(ins_amount) * 100), 
                "currency": currency
            }
            
        if id_check:
            serv_obj["personalIdentification"] = {
                "name": id_name, 
                "personalId": id_number
            }

        payload[0]["services"] = serv_obj
        st.session_state.last_request_shipment = payload
        headers = {"x-api-key": st.session_state.api_key, "Content-Type": "application/json"}
        
        # --- VOLÁNÍ SHIPMENTS API ---
        with st.spinner("Odesílám požadavek do DPD API..."):
            try:
                ship_res = requests.post(f"{API_BASE}/v1/shipments", headers=headers, json=payload)
                ship_data = safe_response_parse(ship_res)
                st.session_state.last_response_shipment = ship_data
                
                if ship_res.status_code not in [200, 201] or not isinstance(ship_data, (dict, list)):
                    human_msg = get_human_error_message(ship_data)
                    if human_msg: 
                        st.error(f"❌ **ZAMÍTNUTO DPD:** {human_msg}")
                    else: 
                        st.error(f"❌ DPD API zamítlo požadavek (HTTP {ship_res.status_code})")
                    
                    if isinstance(ship_data, (dict, list)): 
                        st.json(ship_data)
                    else: 
                        st.code(str(ship_data))
                    st.stop()
                
                # Vyhledání čísla balíku v JSON odpovědi
                def get_p_num(d):
                    if isinstance(d, dict):
                        if "parcelNumbers" in d and "main" in d["parcelNumbers"]: 
                            return d["parcelNumbers"]["main"]
                        if "parcelNumber" in d: 
                            return d["parcelNumber"]
                        for v in d.values():
                            res = get_p_num(v)
                            if res: return res
                    elif isinstance(d, list):
                        for v in d:
                            res = get_p_num(v)
                            if res: return res
                    return None
                
                p_number = get_p_num(ship_data)
                if not p_number:
                    st.error("Zásilka byla založena, ale v odpovědi chybí číslo balíku.")
                    st.stop()
                    
                st.session_state.parcel_number = p_number
                
                # --- NÁSLEDNÉ AKCE (SVOZ / ŠTÍTKY / PIN) ---
                if service_type in ["COLLECTION_IMPORT", "THIRDPARTY_COLLECTION"]:
                    st.session_state.needs_pickup_order = True
                    
                elif service_type == "RETURN" and return_mode == "DROP_OFF_CODE":
                    dropoff_payload = {"aztec": {"format": "PDF"}}
                    dropoff_res = requests.post(f"{API_BASE}/v1/parcels/{p_number}/drop-off-codes", headers=headers, json=dropoff_payload)
                    dropoff_data = safe_response_parse(dropoff_res)
                    st.session_state.last_label_response = dropoff_data
                    
                    if dropoff_res.status_code in [200, 201] and isinstance(dropoff_data, dict):
                        st.session_state.dropoff_pin = dropoff_data.get("pin", {}).get("value", "")
                        aztec_b64 = dropoff_data.get("aztec", {}).get("value", "")
                        if aztec_b64: 
                            st.session_state.pdf_bytes = base64.b64decode(aztec_b64)
                            
                else:
                    label_payload = {
                        "printType": "PDF", 
                        "printProperties": {
                            "pageSize": "A6",
                            "labelsPerPage": 1
                        }, 
                        "parcels": [{"parcelNumber": str(p_number)}]
                    }
                    label_res = requests.post(f"{API_BASE}/v1/parcels/labels", headers=headers, json=label_payload)
                    
                    if 'application/pdf' in label_res.headers.get('Content-Type', '').lower() or label_res.content.startswith(b'%PDF'):
                        st.session_state.pdf_bytes = label_res.content
                    else:
                        ld = safe_response_parse(label_res)
                        st.session_state.last_label_response = ld
                        if isinstance(ld, dict) and ld.get("labels"):
                            st.session_state.pdf_bytes = base64.b64decode(ld["labels"][0].get("content", ""))
            except Exception as e: 
                st.error(f"Systémová chyba: {str(e)}")

    # --- SEKCE INTERAKTIVNÍCH VÝSLEDKŮ ---
    if st.session_state.parcel_number:
        st.success(f"✅ Zásilka {st.session_state.parcel_number} byla úspěšně vytvořena!")
        
        if swap_enabled: 
            st.info("🔄 Výměnný balík (Swap): Vygenerované PDF obsahuje odchozí i vratný štítek pro kurýra.")
        
        if st.session_state.dropoff_pin:
            st.markdown(f"**PIN kód pro zákazníka (Bezštítkové podání na pobočce):** `{st.session_state.dropoff_pin}`")
            
        if st.session_state.pdf_bytes:
            lbl = "📄 Stáhnout Aztec kód (PDF)" if service_type == "RETURN" and return_mode == "DROP_OFF_CODE" else "📄 Stáhnout PDF Štítek"
            st.download_button(lbl, data=st.session_state.pdf_bytes, file_name=f"DPD_{st.session_state.parcel_number}.pdf", mime="application/pdf", use_container_width=True)
        
        if st.session_state.needs_pickup_order:
            st.markdown("<hr>", unsafe_allow_html=True)
            st.header("🚚 Objednávka fyzického svozu kurýrem")
            date = st.date_input("Zvolte požadované datum svozu:", min_value=datetime.today(), value=datetime.today() + timedelta(days=1))
            note = st.text_input("Interní poznámka pro kurýra (např. 'Zvonit na sklad'):", max_chars=200)
            
            if st.button("Potvrdit a zarezervovat svoz", type="primary", use_container_width=True):
                with st.spinner("Rezervuji kurýra..."):
                    p_load = [{
                        "parcel": {"parcelNumber": str(st.session_state.parcel_number)}, 
                        "date": date.strftime("%Y-%m-%d")
                    }]
                    if note.strip():
                        p_load[0]["note"] = note.strip()
                        
                    pick_res = requests.post(f"{API_BASE}/v1/pickup-orders", headers={"x-api-key": st.session_state.api_key, "Content-Type": "application/json"}, json=p_load)
                    p_data = safe_response_parse(pick_res)
                    st.session_state.last_pickup_response = p_data
                    
                    if pick_res.status_code in [200, 201]:
                        st.success(f"✅ Kurýr pro svoz byl úspěšně objednán na datum: {date.strftime('%d. %m. %Y')}!")
                    else:
                        st.error("Nepodařilo se zarezervovat svoz u DPD.")

# --- TECHNICKÝ LOG ---
if st.session_state.last_request_shipment:
    st.divider()
    with st.expander("🛠️ Technický detail komunikace (Pro vývojáře)"):
        st.write("**Request Payload (do DPD API):**")
        st.json(st.session_state.last_request_shipment)
        st.write("**Response (Tvorba Zásilky):**")
        st.json(st.session_state.last_response_shipment)
        
        if st.session_state.last_label_response:
            st.write("**Response (Štítky / PIN):**")
            st.json(st.session_state.last_label_response)
            
        if st.session_state.last_pickup_response:
            st.write("**Response (Svozy):**")
            st.json(st.session_state.last_pickup_response)
