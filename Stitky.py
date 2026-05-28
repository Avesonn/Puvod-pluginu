import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import base64
import re

API_BASE = "https://geoapi-test.dpd.cz"

st.set_page_config(page_title="DPD GeoAPI 2.0 Dashboard", layout="wide")

COUNTRIES = {
    "Česká republika": "CZ", "Slovensko": "SK", "Německo": "DE", 
    "Polsko": "PL", "Rakousko": "AT", "Maďarsko": "HU", 
    "Rumunsko": "RO", "Francie": "FR", "Itálie": "IT", 
    "Španělsko": "ES", "Slovinsko": "SI", "Chorvatsko": "HR",
    "Nizozemsko": "NL", "Belgie": "BE", "Bulharsko": "BG"
}

if 'api_key' not in st.session_state: st.session_state.api_key = ''
if 'addresses' not in st.session_state: st.session_state.addresses = []
if 'parcel_number' not in st.session_state: st.session_state.parcel_number = ''
if 'pdf_bytes' not in st.session_state: st.session_state.pdf_bytes = None
if 'is_collection_flow' not in st.session_state: st.session_state.is_collection_flow = False
if 'last_request_shipment' not in st.session_state: st.session_state.last_request_shipment = None
if 'last_response_shipment' not in st.session_state: st.session_state.last_response_shipment = None

st.title("📦 DPD Shipping Dashboard")
st.markdown("Kompletní testovací rozhraní pro GeoAPI 2.0")

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
            except Exception as e:
                st.error(f"Chyba: {str(e)}")

st.divider()

# --- KROK 2 & 3: FORMULÁŘ ---
if st.session_state.addresses:
    
    col_left, col_right = st.columns([4, 5], gap="large")
    
    with col_left:
        
        service_options = {
            "CLASSIC": "Classic (B2B)",
            "PRIVATE": "Private (B2C)",
            "PICKUP": "Pickup (Pudo)",
            "SHOP_TO_SHOP": "Shop to Shop",
            "SHOP_TO_HOME": "Shop to Home",
            "RETURN": "Return (Vratka)",
            "COLLECTION": "Collection (Vnitrostátní svoz)",
            "IMPORT": "Import (Zahraniční svoz)"
        }
        
        st.header("2. Služby a typ zásilky")
        service_type = st.radio("Zvolte produkt / službu:", options=list(service_options.keys()), format_func=lambda x: service_options[x], horizontal=True)
        
        # --- DETEKCE OBRÁCENÉHO TOKU ---
        is_reverse_flow = service_type in ["RETURN", "COLLECTION", "IMPORT"]
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if is_reverse_flow:
            st.info("🔄 **Obrácený tok:** Vaše registrovaná adresa (níže) slouží jako **PŘÍJEMCE** zásilky.")
        else:
            st.info("📍 **Standardní tok:** Vaše registrovaná adresa (níže) slouží jako **ODESÍLATEL** zásilky.")

        address_dict = {str(a["it4emId"]): a for a in st.session_state.addresses}
        selected_id_str = st.selectbox("Vaše adresa (z DPD profilu):", options=list(address_dict.keys()), format_func=lambda x: address_dict[x]["label"])
        active_dsw = address_dict[selected_id_str]["dsw"]
        active_it4emId = address_dict[selected_id_str]["it4emId"]
        
        # Vícekusová zásilka (MPS)
        st.markdown("<br>", unsafe_allow_html=True)
        parcel_count = st.number_input("Počet balíků (Vícekusová zásilka):", min_value=1, max_value=50, value=1)

        # Dobírka
        st.markdown("<br>", unsafe_allow_html=True)
        cod_enabled = st.checkbox("💸 Odeslat na dobírku (COD)")
        cod_amount = 0.0
        cod_vs = ""
        if cod_enabled:
            col_cod1, col_cod2 = st.columns(2)
            with col_cod1:
                cod_amount = st.number_input("Částka dobírky:", min_value=0.0, step=10.0, value=1000.0)
            with col_cod2:
                cod_vs = st.text_input("Variabilní symbol (nepovinné):")

        st.markdown("<br>", unsafe_allow_html=True)
        
        # Dynamický nadpis podle toku
        if is_reverse_flow:
            st.header("3. Adresa pro VYZVEDNUTÍ (Kde je balík nyní)")
        else:
            st.header("3. Adresa pro DORUČENÍ (Kam balík míří)")
            
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
        
        ref1 = st.text_input("Reference 1 (číslo objednávky - propíše se i na balíky):", "OBJ-2026-999")

    with col_right:
        pickup_id = ""
        if service_type in ["PICKUP", "SHOP_TO_SHOP"]:
            st.header("📍 Výdejní místo")
            st.markdown("Najděte pobočku na mapě, zkopírujte její ID (z pole pod mapou) a vložte ho do bílého pole.")
            pickup_id = st.text_input("ID výdejního místa:")
            
            with st.expander("🌍 Zobrazit DPD Mapu", expanded=True):
                components.iframe("https://api.dpd.cz/widget/latest/demo.html", height=700, scrolling=True)
        else:
            st.info("Zvolená služba nevyžaduje výběr výdejního místa z mapy.")
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        # --- ODESLÁNÍ DO API ---
        if st.button("🚀 Odeslat / Objednat zásilku", type="primary", use_container_width=True):
            # Pročištění starých dat
            st.session_state.pdf_bytes = None
            st.session_state.parcel_number = ""
            st.session_state.is_collection_flow = False

            if service_type in ["PICKUP", "SHOP_TO_SHOP"] and not pickup_id.strip():
                st.error("Pro tuto službu musíte zadat ID výdejního místa!")
                st.stop()
                
            currency = "EUR"
            if country_code == "CZ": currency = "CZK"
            elif country_code == "HU": currency = "HUF"
            elif country_code == "RO": currency = "RON"

            # Dynamické mapování typu zásilky
            current_shipment_type = "Standard"
            if service_type == "RETURN": current_shipment_type = "Return"
            elif service_type == "COLLECTION": current_shipment_type = "Collection"
            elif service_type == "IMPORT": current_shipment_type = "Import"

            # MPS
            parcels_list = [{"references": {"ref1": ref1}, "weightGrams": 1500} for _ in range(int(parcel_count))]

            # --- OTOČENÍ ADRES ---
            manual_address_payload = {
                "info": {
                    "name1": r_name, "name2": "",
                    "contact": {"person": r_name, "phone": r_phone, "email": r_email}
                },
                "address": {
                    "street": r_street, "postalCode": r_zip, "city": r_city,
                    "houseNumber": r_house, "country": {"isoAlpha2": country_code}
                }
            }
            registered_address_payload = {"it4emId": int(active_it4emId)}

            if is_reverse_flow:
                sender_payload = manual_address_payload
                receiver_payload = registered_address_payload
            else:
                sender_payload = registered_address_payload
                receiver_payload = manual_address_payload

            # Sestavení Payloadu
            payload = [{
                "customer": {"dsw": str(active_dsw)},
                "deliveryOptions": {"completeness": "CompleteOnly"},
                "shipmentType": current_shipment_type,
                "sender": sender_payload,
                "receiver": receiver_payload,
                "references": {"ref1": ref1, "ref2": "", "ref3": "", "ref4": ""},
                "parcels": parcels_list,
                "services": {}
            }]
            
            # Služby
            serv_obj = {}
            if service_type == "PRIVATE":
                serv_obj["notification"] = True
            elif service_type == "PICKUP":
                clean_id = pickup_id.strip()
                match = re.search(r'([a-zA-Z]{2}\d+)', clean_id)
                if match: clean_id = match.group(1).upper()
                serv_obj["notification"] = True
                serv_obj["pickupPoint"] = clean_id
            elif service_type == "SHOP_TO_SHOP":
                clean_id = pickup_id.strip()
                match = re.search(r'([a-zA-Z]{2}\d+)', clean_id)
                if match: clean_id = match.group(1).upper()
                serv_obj["shopToShop"] = True
                serv_obj["pickupPoint"] = clean_id
            elif service_type == "SHOP_TO_HOME":
                serv_obj["shopToHome"] = True
            elif service_type == "RETURN":
                serv_obj["dpdReturn"] = True

            # Dobírka s fixním CASH_OR_CARD
            if cod_enabled:
                serv_obj["cashOnDelivery"] = {
                    "amountCents": int(float(cod_amount) * 100),
                    "currency": currency,
                    "payment": "CASH_OR_CARD"
                }
                if cod_vs.strip():
                    serv_obj["cashOnDelivery"]["variableSymbol"] = cod_vs.strip()

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
                        st.error("Zásilka byla založena, ale číslo nebylo nalezeno.")
                        st.stop()
                        
                    st.session_state.parcel_number = p_number
                    
                    # Logika pro přeskočení štítku u svozů
                    if service_type in ["COLLECTION", "IMPORT"]:
                        st.session_state.is_collection_flow = True
                    else:
                        st.session_state.is_collection_flow = False
                        label_payload = {"printType": "PDF", "printProperties": {"pageSize": "A6", "labelsPerPage": 1}, "parcels": [{"parcelNumber": str(p_number)}]}
                        label_res = requests.post(f"{API_BASE}/v1/parcels/labels", headers=headers, json=label_payload)
                        
                        if label_res.status_code not in [200, 201]:
                            st.error("Štítek se nepodařilo stáhnout, zásilka je ale v pořádku založena.")
                            st.stop()
                            
                        if 'application/pdf' in label_res.headers.get('Content-Type', '').lower() or label_res.content.startswith(b'%PDF'):
                            st.session_state.pdf_bytes = label_res.content
                        else:
                            label_data = label_res.json()
                            content = label_data.get("labels", [{}])[0].get("content", label_data.get("content", ""))
                            st.session_state.pdf_bytes = base64.b64decode(content) if content else None
                        
                except Exception as e:
                    st.error(f"Chyba systému: {str(e)}")

        # --- ZOBRAZENÍ VÝSLEDKŮ ---
        if st.session_state.parcel_number:
            st.divider()
            st.success(f"✅ Zásilka **{st.session_state.parcel_number}** byla v pořádku založena!")
            
            if st.session_state.is_collection_flow:
                st.info("🚛 **Svoz byl objednán.** U služeb Collection / Import generuje štítek samotný kurýr při vyzvednutí balíku, proto zde není PDF ke stažení.")
            elif st.session_state.pdf_bytes:
                st.download_button("📄 Stáhnout PDF Štítek", data=st.session_state.pdf_bytes, file_name=f"DPD_{st.session_state.parcel_number}.pdf", mime="application/pdf", use_container_width=True)

# --- DEBUGGING ---
if st.session_state.last_request_shipment:
    st.divider()
    with st.expander("🛠️ Technický detail (Request / Response)"):
        st.write("**Odeslaný Payload:**")
        st.json(st.session_state.last_request_shipment)
        st.write("**Odpověď API:**")
        st.json(st.session_state.last_response_shipment)
