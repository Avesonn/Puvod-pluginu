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
st.markdown("Kompletní testovací rozhraní pro GeoAPI 2.0")

# --- POMOCNÁ FUNKCE PRO BEZPEČNÉ PARSOVÁNÍ ODPOVĚDI ---
def safe_response_parse(response):
    """Bezpečně zkusí parsovat JSON. Pokud jde o HTML chybu (<!DOCTYPE), vrátí text."""
    if not response:
        return "Prázdná odpověď od serveru."
    if isinstance(response, str):
        text = response
    else:
        text = response.text
        
    if text.strip().startswith("<!DOCTYPE") or text.strip().startswith("<html"):
        return f"HTML_ERROR: Server vrátil HTML stránku místo JSONu. Pravděpodobně interní chyba serveru (HTTP {response.status_code if not isinstance(response, str) else 'N/A'})."
    try:
        return response.json()
    except Exception:
        return text

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
                                "dsw": current_dsw, "it4emId": it4_id,
                                "label": f"{city}, {street} | {name} (DSW: {current_dsw}, ID: {it4_id})"
                            })
                    st.session_state.addresses = parsed_addresses
                    st.success(f"Úspěšně načteno! Nalezeno {len(parsed_addresses)} svozových adres.")
                else:
                    st.error(f"Chyba při volání /me (HTTP {response.status_code})")
                    if isinstance(parsed_res, str) and parsed_res.startswith("HTML_ERROR"):
                        st.code(parsed_res)
                    else:
                        st.json(parsed_res)
            except Exception as e:
                st.error(f"Chyba: {str(e)}")

st.divider()

# --- POMOCNÁ FUNKCE PRO VYKRESLENÍ ADRESY ---
def render_address_block(prefix_key, title_text):
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
        
    country_name = st.selectbox("Stát:", options=list(COUNTRIES.keys()), key=f"{prefix_key}_country")
    
    payload_obj = {
        "info": {
            "name1": name, "name2": "",
            "contact": {"person": name, "phone": phone, "email": email}
        },
        "address": {
            "street": street, "postalCode": zip_c, "city": city,
            "houseNumber": house, "country": {"isoAlpha2": COUNTRIES[country_name]}
        }
    }
    return payload_obj, COUNTRIES[country_name]

# --- KROK 2 & 3: FORMULÁŘ ---
if st.session_state.addresses:
    
    col_left, col_right = st.columns([4, 5], gap="large")
    
    with col_left:
        st.header("2. Nastavení zásilky")
        
        # Svozová adresa DSW
        address_dict = {str(a["it4emId"]): a for a in st.session_state.addresses}
        selected_id_str = st.selectbox("Vaše adresa (z DPD profilu):", options=list(address_dict.keys()), format_func=lambda x: address_dict[x]["label"])
        active_dsw = address_dict[selected_id_str]["dsw"]
        active_it4emId = address_dict[selected_id_str]["it4emId"]
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        service_options = {
            "CLASSIC": "Classic (B2B)",
            "PRIVATE": "Private (B2C)",
            "PICKUP": "Pickup (Pudo)",
            "SHOP_TO_SHOP": "Shop to Shop",
            "SHOP_TO_HOME": "Shop to Home",
            "RETURN": "Return (Vratka)",
            "COLLECTION_IMPORT": "Svoz k nám (Collection / Import)",
            "THIRDPARTY_COLLECTION": "Svoz třetí straně (ThirdParty Collection)"
        }
        
        service_type = st.radio("Zvolte produkt / službu:", options=list(service_options.keys()), format_func=lambda x: service_options[x], horizontal=True)
        
        # --- DEFINICE TOKU ---
        is_reverse_flow = service_type in ["RETURN", "COLLECTION_IMPORT"]
        is_third_party_flow = service_type == "THIRDPARTY_COLLECTION"
        is_normal_flow = not is_reverse_flow and not is_third_party_flow
        
        # --- VÝBĚR TYPU VRÁCENÍ PRO RETURN ---
        return_mode = "LABEL"
        if service_type == "RETURN":
            st.markdown("<br>", unsafe_allow_html=True)
            return_mode = st.radio(
                "Způsob zpětného podání (Return Mode):",
                options=["LABEL", "DROP_OFF_CODE"],
                format_func=lambda x: "🖨️ Tisk papírového štítku (Klasické PDF)" if x == "LABEL" else "📱 Bezštítkové podání (Zákazník obdrží PIN + Aztec QR)",
                horizontal=True
            )
        
        # --- VÍCEKUSOVÁ ZÁSILKA A UZAMYKÁNÍ ---
        # Sběrné služby, výdejní místa a bezštítkový return nepovolují vícekusové zásilky (MPS)
        disable_mps = service_type in ["PICKUP", "SHOP_TO_SHOP", "RETURN", "COLLECTION_IMPORT", "THIRDPARTY_COLLECTION"]
        
        st.markdown("<br>", unsafe_allow_html=True)
        if disable_mps:
            st.info("ℹ️ Pro vybranou službu není vícekusová zásilka povolena. Omezeno na 1 balík.")
            parcel_count = 1
        else:
            parcel_count = st.number_input("Počet balíků (Vícekusová zásilka):", min_value=1, max_value=50, value=1)

        # --- DOBÍRKA ---
        st.markdown("<br>", unsafe_allow_html=True)
        cod_enabled = st.checkbox("💸 Odeslat na dobírku (COD)")
        cod_amount = 0.0
        cod_vs = ""
        if cod_enabled:
            col_cod1, col_cod2 = st.columns(2)
            with col_cod1:
                cod_amount = st.number_input("Částka dobírky:", min_value=0.0, step=10.0, value=1000.0)
            with col_cod2:
                cod_vs = st.text_input("Variabilní symbol:")

        st.markdown("<br>", unsafe_allow_html=True)
        ref1 = st.text_input("Reference 1 (číslo objednávky - propíše se i na balíky):", "OBJ-2026-999")

        # --- VYKRESLENÍ ADRES PODLE TOKU ---
        st.markdown("<br>", unsafe_allow_html=True)
        
        if is_normal_flow:
            manual_receiver, r_cc = render_address_block("rec", "3. Adresa pro DORUČENÍ (Příjemce)")
            manual_sender = None
            s_cc = "CZ"
            dest_country = r_cc
            
        elif is_reverse_flow:
            st.info("陣 **Obrácený tok:** Kurýr jede pro balík na adresu níže. Zásilka pak poputuje k vám (na vaši zvolenou DPD adresu).")
            manual_sender, s_cc = render_address_block("sen", "3. Adresa pro VYZVEDNUTÍ (Kde je balík nyní)")
            manual_receiver = None
            dest_country = "CZ"
            
        elif is_third_party_flow:
            st.info("陣 **Tok třetí stranou:** Zásilka se fyzicky nedotkne vaší adresy. Pouze ji platíte přes vaše DSW.")
            manual_sender, s_cc = render_address_block("sen", "3A. Adresa pro VYZVEDNUTÍ (Odesílatel)")
            st.markdown("<br>", unsafe_allow_html=True)
            manual_receiver, r_cc = render_address_block("rec", "3B. Adresa pro DORUČENÍ (Příjemce)")
            dest_country = r_cc

    with col_right:
        pickup_id = ""
        if service_type in ["PICKUP", "SHOP_TO_SHOP"]:
            st.header("📍 Výdejní místo")
            st.markdown("Najděte pobočku na mapě, zkopírujte její ID a vložte ho do bílého pole.")
            pickup_id = st.text_input("ID výdejního místa:")
            
            with st.expander("🌍 Zobrazit DPD Mapu", expanded=True):
                components.iframe("https://api.dpd.cz/widget/latest/demo.html", height=700, scrolling=True)
        else:
            st.info("Zvolená služba nevyžaduje výběr výdejního místa z mapy.")
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        # --- HLAVNÍ AKCE ---
        if st.button("🚀 Vytvořit zásilku v DPD", type="primary", use_container_width=True):
            st.session_state.pdf_bytes = None
            st.session_state.parcel_number = ""
            st.session_state.dropoff_pin = ""
            st.session_state.needs_pickup_order = False
            st.session_state.last_pickup_response = None
            st.session_state.last_label_response = None

            if service_type in ["PICKUP", "SHOP_TO_SHOP"] and not pickup_id.strip():
                st.error("Pro tuto službu musíte zadat ID výdejního místa!")
                st.stop()
                
            currency = "EUR"
            if dest_country == "CZ": currency = "CZK"
            elif dest_country == "HU": currency = "HUF"
            elif dest_country == "RO": currency = "RON"

            # Dynamické mapování typu zásilky (Collection vs Import vs Return)
            current_shipment_type = "Standard"
            if service_type == "RETURN": current_shipment_type = "Return"
            elif service_type == "THIRDPARTY_COLLECTION": current_shipment_type = "ThirdPartyCollection"
            elif service_type == "COLLECTION_IMPORT":
                current_shipment_type = "Collection" if s_cc == "CZ" else "Import"

            # Odesílatel a Příjemce payload
            registered_address_payload = {"it4emId": int(active_it4emId)}
            
            if is_normal_flow:
                sender_payload = registered_address_payload
                receiver_payload = manual_receiver
            elif is_reverse_flow:
                sender_payload = manual_sender
                receiver_payload = registered_address_payload
            elif is_third_party_flow:
                sender_payload = manual_sender
                receiver_payload = manual_receiver

            # Sestavení balíků (Parcels list)
            final_parcel_count = 1 if disable_mps else int(parcel_count)
            parcels_list = [{"references": {"ref1": ref1}, "weightGrams": 1500} for _ in range(final_parcel_count)]

            # Sestavení hlavního Payloadu
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
            
            # Služby (Services)
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

            # Dobírka s fixním CASH_OR_CARD a filtrem na haléře
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
            
            with st.spinner("Zpracovávám požadavek na zásilku..."):
                try:
                    ship_res = requests.post(f"{API_BASE}/v1/shipments", headers=headers, json=payload)
                    ship_data = safe_response_parse(ship_res)
                    st.session_state.last_response_shipment = ship_data
                    
                    if ship_res.status_code not in [200, 201] or not isinstance(ship_data, dict):
                        st.error(f"❌ DPD API zamítlo požadavek (Kód {ship_res.status_code})")
                        if isinstance(ship_data, str) and ship_data.startswith("HTML_ERROR"):
                            st.code(ship_data)
                        else:
                            st.json(ship_data)
                        st.stop()
                    
                    # Vyhledání čísla balíku
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
                        st.error("Zásilka byla založena, ale číslo balíku nebylo v odpovědi nalezeno.")
                        st.stop()
                        
                    st.session_state.parcel_number = p_number
                    
                    # --- SCÉNÁŘE ZPRACOVÁNÍ PO VYTVOŘENÍ BALÍKU ---
                    if service_type in ["COLLECTION_IMPORT", "THIRDPARTY_COLLECTION"]:
                        # Sběrné služby nepotřebují štítek, rovnou flag na objednání svozu
                        st.session_state.needs_pickup_order = True
                        
                    elif service_type == "RETURN" and return_mode == "DROP_OFF_CODE":
                        # Bezštítkové podání (PIN + Aztec)
                        with st.spinner("Generuji bezštítkové kódy (PIN / Aztec)..."):
                            dropoff_payload = {"aztec": {"format": "PDF"}}
                            dropoff_res = requests.post(f"{API_BASE}/v1/parcels/{p_number}/drop-off-codes", headers=headers, json=dropoff_payload)
                            dropoff_data = safe_response_parse(dropoff_res)
                            st.session_state.last_label_response = dropoff_data
                            
                            if dropoff_res.status_code in [200, 201] and isinstance(dropoff_data, dict):
                                st.session_state.dropoff_pin = dropoff_data.get("pin", {}).get("value", "Nenalezen")
                                aztec_b64 = dropoff_data.get("aztec", {}).get("value", "")
                                if aztec_b64:
                                    st.session_state.pdf_bytes = base64.b64decode(aztec_b64)
                            else:
                                st.error(f"Nepodařilo se vygenerovat bezštítkové kódy (HTTP {dropoff_res.status_code})")
                                if isinstance(dropoff_data, str) and dropoff_data.startswith("HTML_ERROR"):
                                    st.code(dropoff_data)
                                else:
                                    st.json(dropoff_data)
                                    
                    else:
                        # Standardní tisk štítku (Classic, Private, Pickup, ShopToShop, ShopToHome, Return-Label)
                        with st.spinner("Stahuji tiskový PDF štítek..."):
                            label_payload = {"printType": "PDF", "printProperties": {"pageSize": "A6", "labelsPerPage": 1}, "parcels": [{"parcelNumber": str(p_number)}]}
                            label_res = requests.post(f"{API_BASE}/v1/parcels/labels", headers=headers, json=label_payload)
                            
                            if label_res.status_code not in [200, 201]:
                                label_data = safe_response_parse(label_res)
                                st.session_state.last_label_response = label_data
                                st.error("Štítek se nepodařilo stáhnout, ale zásilka byla vytvořena.")
                                if isinstance(label_data, str) and label_data.startswith("HTML_ERROR"):
                                    st.code(label_data)
                                else:
                                    st.json(label_data)
                                st.stop()
                                
                            content_type = label_res.headers.get('Content-Type', '')
                            if 'application/pdf' in content_type.lower() or label_res.content.startswith(b'%PDF'):
                                st.session_state.pdf_bytes = label_res.content
                                st.session_state.last_label_response = "[Surová binární PDF data štítku v pořádku stažena]"
                            else:
                                label_data = safe_response_parse(label_res)
                                st.session_state.last_label_response = label_data
                                if isinstance(label_data, dict):
                                    content = label_data.get("labels", [{}])[0].get("content", label_data.get("content", ""))
                                    if content:
                                        st.session_state.pdf_bytes = base64.b64decode(content)
                                        
                except Exception as e:
                    st.error(f"Chyba systému: {str(e)}")

        # --- ZOBRAZENÍ VÝSLEDKŮ (Přímo v pravém sloupci pod akcí) ---
        if st.session_state.parcel_number:
            st.divider()
            st.success(f"✅ Zásilka **{st.session_state.parcel_number}** byla úspěšně založena!")
            
            # 1. Zobrazení PINu pro bezštítkové podání
            if st.session_state.dropoff_pin:
                st.markdown(f"""
                <div style="background-color:#e1f5fe; padding:20px; border-radius:10px; border-left:6px solid #0288d1; margin-bottom:15px;">
                    <span style="font-size:16px; color:#555;">Kód pro bezštítkové vrácení balíku (PIN):</span><br>
                    <strong style="font-size:32px; color:#01579b; letter-spacing:2px;">{st.session_state.dropoff_pin}</strong>
                </div>
                """, unsafe_allow_html=True)
                
            # 2. Stažení PDF (Štítek nebo Aztec QR v PDF)
            if st.session_state.pdf_bytes:
                lbl = "📄 Stáhnout Aztec kód (PDF)" if service_type == "RETURN" and return_mode == "DROP_OFF_CODE" else "📄 Stáhnout PDF Štítek"
                st.download_button(lbl, data=st.session_state.pdf_bytes, file_name=f"DPD_{st.session_state.parcel_number}.pdf", mime="application/pdf", use_container_width=True)

            # 3. Modul pro objednání fyzického svozu (Collection/Import/ThirdParty)
            if st.session_state.needs_pickup_order:
                st.info("🚛 **Tento typ sběrné služby vyžaduje objednání fyzického svozu kurýrem.**")
                
                if st.button("Objednat svoz u DPD pro tuto zásilku", type="primary", use_container_width=True):
                    with st.spinner("Objednávám svoz na serveru..."):
                        headers = {"x-api-key": st.session_state.api_key, "Content-Type": "application/json"}
                        pickup_payload = {"parcels": [{"parcelNumber": str(st.session_state.parcel_number)}]}
                        
                        try:
                            pick_res = requests.post(f"{API_BASE}/v1/pickups", headers=headers, json=pickup_payload)
                            pickup_data = safe_response_parse(pick_res)
                            st.session_state.last_pickup_response = pickup_data
                                
                            if pick_res.status_code in [200, 201] and not (isinstance(pickup_data, str) and pickup_data.startswith("HTML_ERROR")):
                                st.success("✅ Fyzický svoz kurýrem byl úspěšně objednán!")
                            else:
                                st.error(f"❌ Chyba při objednání svozu (Kód {pick_res.status_code})")
                                if isinstance(pickup_data, str) and pickup_data.startswith("HTML_ERROR"):
                                    st.code(pickup_data)
                                else:
                                    st.json(pickup_data)
                        except Exception as e:
                            st.error(f"Systémová chyba při svozu: {str(e)}")

# --- DEBUGGING (Technický detail s ošetřením HTML) ---
if st.session_state.last_request_shipment:
    st.divider()
    with st.expander("🛠️ Technický detail komunikace (Request / Response)"):
        st.write("**1. Zásilka (Shipment) - Odeslaný Payload:**")
        st.json(st.session_state.last_request_shipment)
        
        st.write("**1. Zásilka (Shipment) - Odpověď API:**")
        if isinstance(st.session_state.last_response_shipment, str):
            st.code(st.session_state.last_response_shipment)
        else:
            st.json(st.session_state.last_response_shipment)
            
        if st.session_state.last_label_response:
            st.write("**2. Generování Štítku / Drop-off kódů - Odpověď API:**")
            if isinstance(st.session_state.last_label_response, str):
                st.code(st.session_state.last_label_response)
            else:
                st.json(st.session_state.last_label_response)
        
        if st.session_state.last_pickup_response:
            st.write("**3. Svoz (Pickup Order) - Odpověď API:**")
            if isinstance(st.session_state.last_pickup_response, str):
                st.code(st.session_state.last_pickup_response)
            else:
                st.json(st.session_state.last_pickup_response)
