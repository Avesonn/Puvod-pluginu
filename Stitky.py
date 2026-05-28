import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import base64
import re

API_BASE = "https://geoapi-test.dpd.cz"

# Roztažení na celou šířku
st.set_page_config(page_title="DPD GeoAPI 2.0 Dashboard", layout="wide")

# Seznam států pro našeptávač (Zobrazuje se česky, do API jde ISO Alpha-2)
COUNTRIES = {
    "Česká republika": "CZ", "Slovensko": "SK", "Německo": "DE", 
    "Polsko": "PL", "Rakousko": "AT", "Maďarsko": "HU", 
    "Rumunsko": "RO", "Francie": "FR", "Itálie": "IT", 
    "Španělsko": "ES", "Slovinsko": "SI", "Chorvatsko": "HR",
    "Nizozemsko": "NL", "Belgie": "BE", "Bulharsko": "BG"
}

# Inicializace session state
if 'api_key' not in st.session_state: st.session_state.api_key = ''
if 'addresses' not in st.session_state: st.session_state.addresses = []
if 'parcel_number' not in st.session_state: st.session_state.parcel_number = ''
if 'pdf_bytes' not in st.session_state: st.session_state.pdf_bytes = None
if 'last_request_shipment' not in st.session_state: st.session_state.last_request_shipment = None
if 'last_response_shipment' not in st.session_state: st.session_state.last_response_shipment = None

st.title("📦 DPD Shipping Dashboard")
st.markdown("Kompletní testovací rozhraní pro GeoAPI 2.0")

# --- KROK 1: Přihlášení ---
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
                if response.status_code == 200:
                    data = response.json()
                    st.session_state.api_key = api_key_input
                    
                    parsed_addresses = []
                    for cust_block in data.get("customers", []):
                        current_dsw = cust_block.get("customer", {}).get("DSW", "")
                        for addr in cust_block.get("addresses", []):
                            it4_id = addr.get("it4emId")
                            city = addr.get("address", {}).get("city", "")
                            street = addr.get("address", {}).get("street", "")
                            name = addr.get("info", {}).get("name1", "")
                            parsed_addresses.append({
                                "dsw": current_dsw, "it4emId": it4_id,
                                "label": f"{city}, {street} | {name} (DSW: {current_dsw}, ID: {it4_id})"
                            })
                    st.session_state.addresses = parsed_addresses
                    st.success(f"Úspěšně načteno! Nalezeno {len(parsed_addresses)} svozových adres.")
                else:
                    st.error(f"Chyba při volání /me (HTTP {response.status_code})")
                    st.json(response.json())
            except Exception as e:
                st.error(f"Chyba: {str(e)}")

st.divider()

# --- KROK 2 & 3: Formulář ---
if st.session_state.addresses:
    
    # Rozdělení obrazovky na dva velké sloupce
    col_left, col_right = st.columns([1, 1], gap="large")
    
    with col_left:
        st.header("2. Nastavení zásilky")
        
        # Svozová adresa
        address_dict = {str(a["it4emId"]): a for a in st.session_state.addresses}
        selected_id_str = st.selectbox("Odesílatel (Svoz):", options=list(address_dict.keys()), format_func=lambda x: address_dict[x]["label"])
        active_dsw = address_dict[selected_id_str]["dsw"]
        active_it4emId = address_dict[selected_id_str]["it4emId"]
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Dlaždice pro služby
        service_type = st.radio(
            "Zvolte produkt / službu:", 
            options=["CLASSIC", "PRIVATE", "PICKUP", "SHOP_TO_SHOP"], 
            format_func=lambda x: {
                "CLASSIC": "Classic (B2B)",
                "PRIVATE": "Private (B2C)",
                "PICKUP": "Pickup (Pudo)",
                "SHOP_TO_SHOP": "Shop to Shop"
            }[x],
            horizontal=True
        )
        
        # Dobírka
        st.markdown("<br>", unsafe_allow_html=True)
        cod_enabled = st.checkbox("💸 Odeslat na dobírku (COD)")
        cod_amount = 0.0
        if cod_enabled:
            st.info("Měna se nastaví automaticky podle vybraného státu příjemce (CZK/HUF/RON/EUR).")
            cod_amount = st.number_input("Částka dobírky:", min_value=0.0, step=10.0, value=1000.0)

        st.markdown("<br>", unsafe_allow_html=True)
        st.header("3. Příjemce")
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
            
        country_name = st.selectbox("Stát:", options=list(COUNTRIES.keys()))
        country_code = COUNTRIES[country_name]
        
        ref1 = st.text_input("Reference 1 (např. číslo objednávky):", "OBJ-2026-999")

    with col_right:
        pickup_id = ""
        # Zobrazíme widget pouze pro Pickup nebo Shop to Shop
        if service_type in ["PICKUP", "SHOP_TO_SHOP"]:
            st.header("📍 Výdejní místo")
            st.info("Najděte pobočku na mapě, zkopírujte její ID a vložte ho do pole níže.")
            pickup_id = st.text_input("ID výdejního místa (našeptávač text sám ořeže):")
            
            with st.expander("🌍 Zobrazit DPD Mapu", expanded=True):
                components.iframe("https://api.dpd.cz/widget/latest/demo.html", height=500, scrolling=True)
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        # ODESLÁNÍ
        if st.button("🚀 Odeslat zásilku a vygenerovat štítek", type="primary", use_container_width=True):
            if service_type in ["PICKUP", "SHOP_TO_SHOP"] and not pickup_id.strip():
                st.error("Pro tuto službu musíte zadat ID výdejního místa!")
                st.stop()
                
            # Logika měny dobírky
            currency = "EUR"
            if country_code == "CZ": currency = "CZK"
            elif country_code == "HU": currency = "HUF"
            elif country_code == "RO": currency = "RON"

            payload = [{
                "customer": {"dsw": str(active_dsw)},
                "deliveryOptions": {"completeness": "CompleteOnly"},
                "shipmentType": "Standard",
                "sender": {"it4emId": int(active_it4emId)},
                "receiver": {
                    "info": {
                        "name1": r_name,
                        "name2": "",
                        "contact": {"person": r_name, "phone": r_phone, "email": r_email}
                    },
                    "address": {
                        "street": r_street,
                        "postalCode": r_zip,
                        "city": r_city,
                        "houseNumber": r_house,
                        "country": {"isoAlpha2": country_code}
                    }
                },
                "references": {"ref1": ref1, "ref2": "", "ref3": "", "ref4": ""},
                "parcels": [{"references": {"ref1": ref1}, "weightGrams": 1500}],
                "services": {}
            }]
            
            # Naplnění uzlu "services" podle služby
            serv_obj = {}
            if service_type == "PRIVATE":
                serv_obj["notification"] = True
            elif service_type in ["PICKUP", "SHOP_TO_SHOP"]:
                clean_id = pickup_id.strip()
                match = re.search(r'([a-zA-Z]{2}\d+)', clean_id)
                if match: clean_id = match.group(1).upper()
                
                serv_obj["notification"] = True
                serv_obj["pickupPoint"] = clean_id
                if service_type == "SHOP_TO_SHOP":
                    serv_obj["shopToShop"] = True

            # Přidání dobírky do uzlu services
            if cod_enabled:
                serv_obj["cod"] = {
                    "amount": float(cod_amount),
                    "currency": currency,
                    "paymentMethod": "CashOrCard"
                }

            payload[0]["services"] = serv_obj
            
            st.session_state.last_request_shipment = payload
            headers = {"x-api-key": st.session_state.api_key, "Content-Type": "application/json"}
            
            with st.spinner("Zpracovávám požadavek..."):
                try:
                    ship_res = requests.post(f"{API_BASE}/v1/shipments", headers=headers, json=payload)
                    try:
                        ship_data = ship_res.json()
                    except:
                        ship_data = ship_res.text
                    
                    st.session_state.last_response_shipment = ship_data
                    
                    if ship_res.status_code not in [200, 201]:
                        st.error(f"❌ DPD API zamítlo požadavek (Kód {ship_res.status_code})")
                        st.json(ship_data)
                        st.stop()
                    
                    def find_parcel_number(d):
                        if isinstance(d, dict):
                            if "parcelNumbers" in d and isinstance(d["parcelNumbers"], dict) and "main" in d["parcelNumbers"]:
                                return d["parcelNumbers"]["main"]
                            if "parcelNumber" in d and isinstance(d["parcelNumber"], str):
                                return d["parcelNumber"]
                            for v in d.values():
                                res = find_parcel_number(v)
                                if res: return res
                        elif isinstance(d, list):
                            for v in d:
                                res = find_parcel_number(v)
                                if res: return res
                        return None
                    
                    p_number = find_parcel_number(ship_data)
                    if not p_number:
                        st.error("Zásilka byla založena, ale číslo zásilky nebylo nalezeno.")
                        st.stop()
                        
                    st.session_state.parcel_number = p_number
                    
                    # Generování štítku
                    label_payload = {"printType": "PDF", "printProperties": {"pageSize": "A6", "labelsPerPage": 1}, "parcels": [{"parcelNumber": str(p_number)}]}
                    label_res = requests.post(f"{API_BASE}/v1/parcels/labels", headers=headers, json=label_payload)
                    
                    if label_res.status_code not in [200, 201]:
                        st.error("Štítek se nepodařilo stáhnout.")
                        st.stop()
                        
                    if 'application/pdf' in label_res.headers.get('Content-Type', '').lower() or label_res.content.startswith(b'%PDF'):
                        st.session_state.pdf_bytes = label_res.content
                    else:
                        label_data = label_res.json()
                        content = label_data.get("labels", [{}])[0].get("content", label_data.get("content", ""))
                        st.session_state.pdf_bytes = base64.b64decode(content) if content else None
                        
                except Exception as e:
                    st.error(f"Chyba systému: {str(e)}")

# --- KROK 4: Výsledek ---
if st.session_state.pdf_bytes:
    st.divider()
    st.success(f"✅ Zásilka **{st.session_state.parcel_number}** byla úspěšně vygenerována!")
    st.download_button("📄 Stáhnout PDF Štítek", data=st.session_state.pdf_bytes, file_name=f"DPD_{st.session_state.parcel_number}.pdf", mime="application/pdf")

# --- DEBUGGING ---
if st.session_state.last_request_shipment:
    st.divider()
    with st.expander("🛠️ Technický detail (Request / Response)"):
        st.write("**Odeslaný Payload:**")
        st.json(st.session_state.last_request_shipment)
        st.write("**Odpověď API:**")
        st.json(st.session_state.last_response_shipment)
