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
if 'needs_pickup_order' not in st.session_state: st.session_state.needs_pickup_order = False
if 'last_request_shipment' not in st.session_state: st.session_state.last_request_shipment = None
if 'last_response_shipment' not in st.session_state: st.session_state.last_response_shipment = None
if 'last_pickup_response' not in st.session_state: st.session_state.last_pickup_response = None

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

# --- POMOCNÁ FUNKCE PRO VYKRESLENÍ ADRESY ---
# Umožňuje nám na stránku vykreslit libovolný počet adresních bloků
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
            "RETURN": "Return (Vratka zákazníkem)",
            "COLLECTION_IMPORT": "Svoz k nám (Collection / Import)",
            "THIRDPARTY_COLLECTION": "Svoz třetí straně (ThirdParty Collection)"
        }
        
        service_type = st.radio("Zvolte produkt / službu:", options=list(service_options.keys()), format_func=lambda x: service_options[x], horizontal=True)
        
        # --- DEFINICE TOKU ---
        is_reverse_flow = service_type in ["RETURN", "COLLECTION_IMPORT"]
        is_third_party_flow = service_type == "THIRDPARTY_COLLECTION"
        is_normal_flow = not is_reverse_flow and not is_third_party_flow
        
        # --- VÍCEKUSOVÁ ZÁSILKA A UZAMYKÁNÍ ---
        disable_mps = service_type in ["PICKUP", "SHOP_TO_SHOP", "RETURN", "COLLECTION_IMPORT", "THIRDPARTY_COLLECTION"]
        
        st.markdown("<br>", unsafe_allow_html=True)
        if disable_mps:
            st.info("ℹ️ Pro vybranou službu **není vícekusová zásilka povolena**. Limitováno na 1 balík.")
        parcel_count = st.number_input("Počet balíků (Vícekusová zásilka):", min_value=1, max_value=50, value=1, disabled=disable_mps)

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
                cod_vs = st.text_input("Variabilní symbol (nepovinné):")

        st.markdown("<br>", unsafe_allow_html=True)
        ref1 = st.text_input("Reference 1 (číslo objednávky - propíše se i na balíky):", "OBJ-2026-999")

        # --- VYKRESLENÍ ADRES PODLE TOKU ---
        st.markdown("<br>", unsafe_allow_html=True)
        
        if is_normal_flow:
            manual_receiver, r_cc = render_address_block("rec", "3. Adresa pro DORUČENÍ (Příjemce)")
            manual_sender = None
            s_cc = "CZ" # Výchozí
            dest_country = r_cc
            
        elif is_reverse_flow:
            st.info("🔄 **Obrácený tok:** Kurýr jede pro balík na adresu níže. Zásilka pak poputuje k vám (na vaši zvolenou DPD adresu).")
            manual_sender, s_cc = render_address_block("sen", "3. Adresa pro VYZVEDNUTÍ (Kde je balík nyní)")
            manual_receiver = None
            dest_country = "CZ" # Jede k vám
            
        elif is_third_party_flow:
            st.info("🔄 **Tok třetí stranou:** Zásilka se fyzicky nedotkne vaší adresy. Pouze ji platíte přes vaše DSW.")
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
            # Pročištění starých dat
            st.session_state.pdf_bytes = None
            st.session_state.parcel_number = ""
            st.session_state.needs_pickup_order = False
            st.session_state.last_pickup_response = None

            if service_type in ["PICKUP", "SHOP_TO_SHOP"] and not pickup_id.strip():
                st.error("Pro tuto službu musíte zadat ID výdejního místa!")
                st.stop()
                
            # Měna Dobírky
            currency = "EUR"
            if dest_country == "CZ": currency = "CZK"
            elif dest_country == "HU": currency = "HUF"
            elif dest_country == "RO": currency = "RON"

            # Dynamické mapování typu zásilky (Collection vs Import)
            current_shipment_type = "Standard"
            if service_type == "RETURN": current_shipment_type = "Return"
            elif service_type == "THIRDPARTY_COLLECTION": current_shipment_type = "ThirdPartyCollection"
            elif service_type == "COLLECTION_IMPORT":
                current_shipment_type = "Collection" if s_cc == "CZ" else "Import"

            # Odesílatel a Příjemce
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

            # MPS Parcels
            final_parcel_count = 1 if disable_mps else int(parcel_count)
            parcels_list = [{"references": {"ref1": ref1}, "weightGrams": 1500} for _ in range(final_parcel_count)]

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
                    
                    # Štítek a flag pro objednání svozu
                    if service_type in ["COLLECTION_IMPORT", "THIRDPARTY_COLLECTION", "RETURN"]:
                        st.session_state.needs_pickup_order = True
                        
                        # Return jako jediný tiskne i štítek
                        if service_type == "RETURN":
                            label_payload = {"printType": "PDF", "printProperties": {"pageSize": "A6", "labelsPerPage": 1}, "parcels": [{"parcelNumber": str(p_number)}]}
                            label_res = requests.post(f"{API_BASE}/v1/parcels/labels", headers=headers, json=label_payload)
                            if 'application/pdf' in label_res.headers.get('Content-Type', '').lower() or label_res.content.startswith(b'%PDF'):
                                st.session_state.pdf_bytes = label_res.content
                            else:
                                l_data = label_res.json()
                                cont = l_data.get("labels", [{}])[0].get("content", l_data.get("content", ""))
                                st.session_state.pdf_bytes = base64.b64decode(cont) if cont else None
                    else:
                        st.session_state.needs_pickup_order = False
                        label_payload = {"printType": "PDF", "printProperties": {"pageSize": "A6", "labelsPerPage": 1}, "parcels": [{"parcelNumber": str(p_number)}]}
                        label_res = requests.post(f"{API_BASE}/v1/parcels/labels", headers=headers, json=label_payload)
                        if 'application/pdf' in label_res.headers.get('Content-Type', '').lower() or label_res.content.startswith(b'%PDF'):
                            st.session_state.pdf_bytes = label_res.content
                        else:
                            l_data = label_res.json()
                            cont = l_data.get("labels", [{}])[0].get("content", l_data.get("content", ""))
                            st.session_state.pdf_bytes = base64.b64decode(cont) if cont else None
                        
                except Exception as e:
                    st.error(f"Chyba systému: {str(e)}")

        # --- ZOBRAZENÍ VÝSLEDKŮ ---
        if st.session_state.parcel_number:
            st.divider()
            st.success(f"✅ Zásilka **{st.session_state.parcel_number}** byla úspěšně založena!")
            
            # Pokud máme štítek (Standardní + Return)
            if st.session_state.pdf_bytes:
                st.download_button("📄 Stáhnout PDF Štítek", data=st.session_state.pdf_bytes, file_name=f"DPD_{st.session_state.parcel_number}.pdf", mime="application/pdf", use_container_width=True)

            # Modul pro objednání svozu
            if st.session_state.needs_pickup_order:
                st.info("🚛 **Tento typ zásilky vyžaduje objednání fyzického svozu kurýrem.**")
                
                if st.button("Objednat svoz u DPD pro tuto zásilku", type="primary", use_container_width=True):
                    with st.spinner("Objednávám svoz na serveru..."):
                        headers = {"x-api-key": st.session_state.api_key, "Content-Type": "application/json"}
                        
                        # Zde odesíláme žádost na DPD endpoint pro Pickupy (zpravidla /v1/pickups nebo /v1/collection-requests)
                        # Pokud by API hlásilo chybu struktury, je potřeba tento JSON upravit dle konkrétní Postman dokumentace.
                        pickup_payload = {
                            "parcels": [{"parcelNumber": str(st.session_state.parcel_number)}]
                        }
                        
                        try:
                            # Standardní endpoint pro objednávky svozů (může se v DPD dokumentaci lišit)
                            pick_res = requests.post(f"{API_BASE}/v1/pickups", headers=headers, json=pickup_payload)
                            try:
                                st.session_state.last_pickup_response = pick_res.json()
                            except:
                                st.session_state.last_pickup_response = pick_res.text
                                
                            if pick_res.status_code in [200, 201]:
                                st.success("✅ Fyzický svoz kurýrem byl úspěšně objednán!")
                            else:
                                st.error(f"❌ Chyba při objednání svozu (Kód {pick_res.status_code})")
                                st.json(st.session_state.last_pickup_response)
                        except Exception as e:
                            st.error(f"Systémová chyba při svozu: {str(e)}")

# --- DEBUGGING ---
if st.session_state.last_request_shipment:
    st.divider()
    with st.expander("🛠️ Technický detail komunikace (Request / Response)"):
        st.write("**1. Zásilka (Shipment) - Odeslaný Payload:**")
        st.json(st.session_state.last_request_shipment)
        st.write("**1. Zásilka (Shipment) - Odpověď API:**")
        st.json(st.session_state.last_response_shipment)
        
        if st.session_state.last_pickup_response:
            st.write("**2. Svoz (Pickup Order) - Odpověď API:**")
            st.json(st.session_state.last_pickup_response)
