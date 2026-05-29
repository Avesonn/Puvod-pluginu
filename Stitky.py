import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import base64
import re
from datetime import datetime, timedelta

API_BASE = "https://geoapi-test.dpd.cz"

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
</style>
""", unsafe_allow_html=True)

COUNTRIES = {
    "Česká republika": "CZ", "Slovensko": "SK", "Německo": "DE", 
    "Polsko": "PL", "Rakousko": "AT", "Maďarsko": "HU", 
    "Rumunsko": "RO", "Francie": "FR", "Itálie": "IT", 
    "Španělsko": "ES", "Slovinsko": "SI", "Chorvatsko": "HR",
    "Nizozemsko": "NL", "Belgie": "BE", "Bulharsko": "BG"
}

# --- PRAVIDLA DOSTUPNOSTI SLUŽEB PODLE ZEMÍ (Z HTML) ---
ALLOWED_COUNTRIES = {
    "CLASSIC": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"],
    "PRIVATE": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE"], # Bez BG
    "GUARANTEE": ["DE", "PL", "AT", "SK", "NL", "BE", "FR"], 
    "PICKUP": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"],
    "EXPRESS": ["CZ", "SK", "DE", "PL", "AT", "HU", "RO", "FR", "IT", "ES", "SI", "HR", "NL", "BE", "BG"], # Letecky (celý svět)
    "PNEU": ["CZ"], # Pouze ČR
    "DPD12": ["CZ"], # Pouze ČR
    "DPDDNES": ["CZ"], # Pouze ČR (Praha)
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

st.title("📦 DPD Shipping Dashboard")
st.markdown("Kompletní testovací rozhraní pro GeoAPI 2.0 s restrikcemi dle zemí")

# --- POMOCNÉ FUNKCE ---
def safe_response_parse(response):
    if response is None: return "Prázdná odpověď od serveru."
    if isinstance(response, str): text = response
    else: text = response.text
    if text.strip().startswith("<!DOCTYPE") or text.strip().startswith("<html"):
        return f"HTML_ERROR: Server vrátil HTML stránku místo JSONu. (HTTP {response.status_code if not isinstance(response, str) else 'N/A'})"
    try: return response.json()
    except Exception: return text if text.strip() else "Prázdná odpověď od serveru."

def get_human_error_message(err_data):
    err_str = json.dumps(err_data)
    if "Parcel range for the customer address" in err_str: return "Chybějící číselná řada. Obraťte se na technickou podporu DPD."
    elif "GeoroutingInputError" in err_str and "pattern" in err_str: return "Špatně zadaná adresa příjemce (pravděpodobně neplatný formát PSČ)."
    elif "GeoroutingCombinationNotFound" in err_str: return "Je zvolená neplatná kombinace služeb pro danou zemi/PSČ."
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
        "info": {"name1": name, "name2": "", "contact": {"person": name, "phone": phone, "email": email}},
        "address": {"street": street, "postalCode": zip_c, "city": city, "houseNumber": house, "country": {"isoAlpha2": country_code}}
    }
    return payload_obj

# --- KROK 1: PŘIHLÁŠENÍ ---
st.header("1. Přihlášení")
col_auth1, col_auth2 = st.columns([1, 2])
with col_auth1:
    api_key_input = st.text_input("Zadejte API Klíč (x-api-key):", type="password", value=st.session_state.api_key)
    btn_login = st.button("Načíst údaje z profilu", type="primary")

if btn_login:
    if not api_key_input: st.warning("Prosím, vložte platný API klíč.")
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
                            parsed_addresses.append({"dsw": current_dsw, "it4emId": it4_id, "label": f"{city}, {street} | {name} (DSW: {current_dsw}, ID: {it4_id})"})
                    st.session_state.addresses = parsed_addresses
                    st.success(f"Úspěšně načteno! Nalezeno {len(parsed_addresses)} svozových adres.")
                else:
                    st.error(f"Chyba při volání /me (HTTP {response.status_code})")
                    if isinstance(parsed_res, (dict, list)): st.json(parsed_res)
                    else: st.code(str(parsed_res))
            except Exception as e: st.error(f"Chyba: {str(e)}")

st.divider()

# --- KROK 2 & 3: FORMULÁŘ S FILTROVÁNÍM ---
if st.session_state.addresses:
    col_left, col_right = st.columns([4, 5], gap="large")
    
    with col_left:
        st.header("2. Základní nastavení a Destinace")
        address_dict = {str(a["it4emId"]): a for a in st.session_state.addresses}
        selected_id_str = st.selectbox("Vaše adresa (Odesílatel / DPD profil):", options=list(address_dict.keys()), format_func=lambda x: address_dict[x]["label"])
        active_dsw = address_dict[selected_id_str]["dsw"]
        active_it4emId = address_dict[selected_id_str]["it4emId"]
        
        # Výběr země je nyní ZDE nahoře, aby filtroval služby
        dest_country_name = st.selectbox("Země doručení / Zahraničního svozu:", options=list(COUNTRIES.keys()))
        dest_country_code = COUNTRIES[dest_country_name]
        
        st.markdown("<hr>", unsafe_allow_html=True)
        st.header("3. Výběr Služby")
        
        # Master seznam všech služeb
        all_service_options = {
            "CLASSIC": "DPD Classic",
            "PRIVATE": "DPD Private",
            "GUARANTEE": "DPD Guarantee",
            "EXPRESS": "DPD Express (Letecky)",
            "PNEU": "DPD Pneu",
            "DPD12": "DPD 12:00",
            "DPDDNES": "DPD Dnes (Same Day)",
            "PICKUP": "DPD Pickup (Boxy/Výdejní místa)",
            "SHOP_TO_SHOP": "DPD Shop2Shop",
            "SHOP_TO_HOME": "DPD Shop2Home",
            "RETURN": "Return (Zpětná vratka)",
            "COLLECTION_IMPORT": "Svoz k nám (Collection/Import)",
            "THIRDPARTY_COLLECTION": "Svoz třetí straně"
        }
        
        # Filtrujeme služby podle zvolené země
        available_services = {k: v for k, v in all_service_options.items() if dest_country_code in ALLOWED_COUNTRIES.get(k, [])}
        
        if not available_services:
            st.error("Pro tuto zemi aktuálně nejsou v Dashboardu povoleny žádné služby.")
            st.stop()
            
        service_type = st.radio("Dostupné služby pro vybranou zemi:", options=list(available_services.keys()), format_func=lambda x: available_services[x], horizontal=True)
        
        # Toky
        is_reverse_flow = service_type in ["RETURN", "COLLECTION_IMPORT"]
        is_third_party_flow = service_type == "THIRDPARTY_COLLECTION"
        is_normal_flow = not is_reverse_flow and not is_third_party_flow
        
        return_mode = "LABEL"
        if service_type == "RETURN":
            st.markdown("<br>", unsafe_allow_html=True)
            return_mode = st.radio("Způsob zpětného podání (Return Mode):", options=["LABEL", "DROP_OFF_CODE"], format_func=lambda x: "🖨️ Tisk papírového štítku (Klasické PDF)" if x == "LABEL" else "📱 Bezštítkové podání (PIN + Aztec QR)", horizontal=True)

        # Adresy
        st.markdown("<hr>", unsafe_allow_html=True)
        if is_normal_flow:
            manual_receiver = render_address_block("rec", "4. Adresa Příjemce", override_country=dest_country_code)
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

        # Doplňkové služby
        st.markdown("<hr>", unsafe_allow_html=True)
        st.header("5. Doplňkové služby")
        
        col_srv1, col_srv2, col_srv3 = st.columns(3)
        with col_srv1: cod_enabled = st.checkbox("💸 Dobírka (COD)")
        with col_srv2: swap_enabled = st.checkbox("🔄 Výměnný balík") if service_type in ["CLASSIC", "PRIVATE", "GUARANTEE", "DPD12", "DPDDNES"] and dest_country_code == "CZ" else False
        with col_srv3: ins_enabled = st.checkbox("🛡️ Rozšířené krytí (Pojištění)")
        
        id_check = st.checkbox("👤 Ověřené předání (ID Check)") if service_type in ["CLASSIC", "PRIVATE", "DPD12"] and dest_country_code == "CZ" else False
        
        # Logika polí pro doplňky
        cod_amount = 0.0
        cod_vs = ""
        ins_amount = 0.0
        id_name = ""
        id_number = ""
        
        if cod_enabled:
            c_cod1, c_cod2 = st.columns(2)
            with c_cod1: cod_amount = st.number_input("Částka dobírky:", min_value=0.0, step=10.0, value=1000.0)
            with c_cod2: cod_vs = st.text_input("Variabilní symbol (COD):")
            
        if ins_enabled:
            ins_amount = st.number_input("Hodnota zásilky (Pojištění):", min_value=0.0, step=100.0, value=50000.0)
            
        if id_check:
            c_id1, c_id2 = st.columns(2)
            with c_id1: id_name = st.text_input("Jméno pro ověření:")
            with c_id2: id_number = st.text_input("Číslo OP (Posledních 5 znaků):", max_chars=5)

        st.markdown("<br>", unsafe_allow_html=True)
        disable_mps = service_type in ["PICKUP", "SHOP_TO_SHOP", "SHOP_TO_HOME", "RETURN", "COLLECTION_IMPORT", "THIRDPARTY_COLLECTION"] or swap_enabled
        if disable_mps:
            st.info("ℹ️ Pro vybranou službu není vícekusová zásilka povolena.")
            parcel_count = 1
        else:
            parcel_count = st.number_input("Počet balíků (Vícekusová zásilka):", min_value=1, max_value=50, value=1)
            
        col_w, col_r = st.columns(2)
        with col_w:
             max_w = 20.0 if service_type in ["PICKUP", "SHOP_TO_SHOP", "SHOP_TO_HOME"] else 31.5
             st.info(f"Limit váhy: max. {max_w} kg")
             parcel_weight_kg = st.number_input("Váha jednoho balíku (kg):", min_value=0.1, max_value=max_w, value=1.5, step=0.5)
        with col_r:
             ref1 = st.text_input("Reference 1:", "OBJ-2026-999")

    with col_right:
        pickup_id = ""
        if service_type in ["PICKUP", "SHOP_TO_SHOP"]:
            st.header("📍 Výdejní místo")
            pickup_id = st.text_input("ID výdejního místa (z mapy níže):")
            with st.expander("🌍 Zobrazit DPD Mapu", expanded=True):
                components.iframe("https://api.dpd.cz/widget/latest/demo.html", height=700, scrolling=True)
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        if st.button("🚀 Vytvořit zásilku v DPD", type="primary", use_container_width=True):
            st.session_state.pdf_bytes = None
            st.session_state.parcel_number = ""
            st.session_state.dropoff_pin = ""
            st.session_state.needs_pickup_order = False
            
            if service_type in ["PICKUP", "SHOP_TO_SHOP"] and not pickup_id.strip():
                st.error("Zadejte ID výdejního místa!")
                st.stop()
                
            currency = "EUR"
            if dest_country_code == "CZ": currency = "CZK"
            elif dest_country_code == "HU": currency = "HUF"
            elif dest_country_code == "RO": currency = "RON"

            current_shipment_type = "Standard"
            if service_type == "RETURN": current_shipment_type = "Return"
            elif service_type == "THIRDPARTY_COLLECTION": current_shipment_type = "ThirdPartyCollection"
            elif service_type == "COLLECTION_IMPORT": current_shipment_type = "Collection" if s_cc == "CZ" else "Import"

            registered_address_payload = {"it4emId": int(active_it4emId)}
            if is_normal_flow:
                sender_payload = registered_address_payload
                receiver_payload = manual_receiver
            elif is_reverse_flow:
                sender_payload = manual_sender
                receiver_payload = registered_address_payload
            else:
                sender_payload = manual_sender
                receiver_payload = manual_receiver

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
            elif service_type == "PNEU": serv_obj["dpdPneu"] = True
            elif service_type == "DPD12": serv_obj["dpdTimeGuarantee"] = "DPD12"
            elif service_type == "DPDDNES": serv_obj["dpdTimeGuarantee"] = "SAMEDAY"
            elif service_type in ["PICKUP", "SHOP_TO_SHOP"]:
                clean_id = re.search(r'([a-zA-Z]{2}\d+)', pickup_id.strip())
                serv_obj["pickupPoint"] = clean_id.group(1).upper() if clean_id else pickup_id.strip().upper()
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
            
            with st.spinner("Odesílám do DPD..."):
                try:
                    ship_res = requests.post(f"{API_BASE}/v1/shipments", headers=headers, json=payload)
                    ship_data = safe_response_parse(ship_res)
                    st.session_state.last_response_shipment = ship_data
                    
                    if ship_res.status_code not in [200, 201] or not isinstance(ship_data, (dict, list)):
                        human_msg = get_human_error_message(ship_data)
                        if human_msg: st.error(f"❌ **ZAMÍTNUTO DPD:** {human_msg}")
                        else: st.error(f"❌ Chyba API (Kód {ship_res.status_code})")
                        if isinstance(ship_data, (dict, list)): st.json(ship_data)
                        else: st.code(str(ship_data))
                        st.stop()
                    
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
                    
                    p_number = get_p_num(ship_data)
                    if not p_number:
                        st.error("Zásilka založena, ale chybí číslo.")
                        st.stop()
                        
                    st.session_state.parcel_number = p_number
                    
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
                        label_res = requests.post(f"{API_BASE}/v1/parcels/labels", headers=headers, json={"printType": "PDF", "printProperties": {"pageSize": "A6"}, "parcels": [{"parcelNumber": str(p_number)}]})
                        if 'application/pdf' in label_res.headers.get('Content-Type', '').lower() or label_res.content.startswith(b'%PDF'):
                            st.session_state.pdf_bytes = label_res.content
                        else:
                            ld = safe_response_parse(label_res)
                            st.session_state.last_label_response = ld
                            if isinstance(ld, dict) and ld.get("labels"):
                                st.session_state.pdf_bytes = base64.b64decode(ld["labels"][0].get("content", ""))
                except Exception as e:
                    st.error(str(e))

        if st.session_state.parcel_number:
            st.success(f"✅ Zásilka {st.session_state.parcel_number} vytvořena!")
            if swap_enabled: st.info("🔄 Byl aktivován SWAP. Štítek bude vícestránkový.")
            if st.session_state.dropoff_pin: st.markdown(f"**PIN pro zákazníka:** {st.session_state.dropoff_pin}")
            if st.session_state.pdf_bytes: st.download_button("📄 Stáhnout PDF", data=st.session_state.pdf_bytes, file_name=f"DPD_{st.session_state.parcel_number}.pdf", mime="application/pdf")
            if st.session_state.needs_pickup_order:
                date = st.date_input("Svoz:", min_value=datetime.today())
                if st.button("Objednat svoz"):
                    requests.post(f"{API_BASE}/v1/pickup-orders", headers={"x-api-key": st.session_state.api_key, "Content-Type": "application/json"}, json=[{"parcel": {"parcelNumber": str(st.session_state.parcel_number)}, "date": date.strftime("%Y-%m-%d")}])
                    st.success("Svoz objednán!")

if st.session_state.last_request_shipment:
    with st.expander("🛠️ Technický detail"):
        st.json(st.session_state.last_request_shipment)
        st.json(st.session_state.last_response_shipment)
