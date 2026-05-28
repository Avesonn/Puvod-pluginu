import streamlit as st
import requests
import json
import base64

API_BASE = "https://geoapi-test.dpd.cz"

# Inicializace session state pro uchování stavu mezi překresleními stránky
if 'api_key' not in st.session_state:
    st.session_state.api_key = ''
if 'addresses' not in st.session_state:
    st.session_state.addresses = []
if 'parcel_number' not in st.session_state:
    st.session_state.parcel_number = ''
if 'pdf_bytes' not in st.session_state:
    st.session_state.pdf_bytes = None
if 'last_request_shipment' not in st.session_state:
    st.session_state.last_request_shipment = None
if 'last_response_shipment' not in st.session_state:
    st.session_state.last_response_shipment = None
if 'last_request_label' not in st.session_state:
    st.session_state.last_request_label = None
if 'last_response_label' not in st.session_state:
    st.session_state.last_response_label = None

st.set_page_config(page_title="DPD GeoAPI 2.0 Dashboard", layout="centered")

st.title("📦 DPD Shipping Dashboard")
st.markdown("Kompletní testovací rozhraní pro GeoAPI 2.0")

# --- KROK 1: Přihlášení a načtení profilu ---
st.header("1. Přihlášení")
api_key_input = st.text_input("Zadejte API Klíč (x-api-key):", type="password", value=st.session_state.api_key)

if st.button("Načíst údaje z profilu (GET /me)"):
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
                    customers_data = data.get("customers", [])
                    
                    # Projdeme všechny zákaznické účty (customers) a jejich svozové adresy
                    for cust_block in customers_data:
                        current_dsw = cust_block.get("customer", {}).get("DSW", "")
                        
                        for addr in cust_block.get("addresses", []):
                            it4_id = addr.get("it4emId")
                            city = addr.get("address", {}).get("city", "")
                            street = addr.get("address", {}).get("street", "")
                            name = addr.get("info", {}).get("name1", "")
                            
                            label = f"{city}, {street} | {name} (DSW: {current_dsw}, ID: {it4_id})"
                            
                            parsed_addresses.append({
                                "dsw": current_dsw,
                                "it4emId": it4_id,
                                "label": label
                            })
                    
                    st.session_state.addresses = parsed_addresses
                    if parsed_addresses:
                        st.success(f"Úspěšně načteno! Nalezeno {len(parsed_addresses)} svozových adres.")
                    else:
                        st.warning("Přihlášení proběhlo, ale v profilu nebyly nalezeny žádné adresy.")
                else:
                    st.error(f"Chyba při volání /me (HTTP {response.status_code})")
                    st.text(response.text)
            except Exception as e:
                st.error(f"Nepodařilo se navázat spojení: {str(e)}")

st.divider()

# --- KROK 2 & 3: Formulář pro tvorbu zásilky ---
if st.session_state.addresses:
    st.header("2. Svozové místo a výběr služby")
    
    # Příprava adres pro výběr v roletce
    address_dict = {str(a["it4emId"]): a for a in st.session_state.addresses}
    selected_id_str = st.selectbox(
        "Vyberte odesílající adresu (Svoz):", 
        options=list(address_dict.keys()), 
        format_func=lambda x: address_dict[x]["label"]
    )
    
    selected_address_obj = address_dict[selected_id_str]
    active_dsw = selected_address_obj["dsw"]
    active_it4emId = selected_address_obj["it4emId"]
    
    service_type = st.selectbox(
        "Zvolte produkt/službu:", 
        options=["CLASSIC", "PRIVATE"], 
        format_func=lambda x: "DPD Classic (B2B - Scénář 101)" if x == "CLASSIC" else "DPD Private (B2C - Scénář 327)"
    )
    
    st.header("3. Detaily příjemce")
    col1, col2 = st.columns(2)
    with col1:
        r_name = st.text_input("Jméno a příjmení / Firma příjemce:", "Jan Novák")
        r_city = st.text_input("Město:", "Praha")
        r_street = st.text_input("Ulice:", "Nad Petruskou")
    with col2:
        r_house = st.text_input("Číslo popisné/orientační:", "63/1")
        r_zip = st.text_input("PSČ:", "12000")
        r_country = st.text_input("Kód státu (ISO Alpha-2):", "CZ", max_chars=2)
        
    st.markdown("### Referenční pole")
    ref1 = st.text_input("Reference 1 (např. ID objednávky z e-shopu):", "OBJ-2026-999")
    ref2 = st.text_input("Reference 2:", "")
    
    if st.button("Odeslat zásilku a vygenerovat PDF štítek", type="primary"):
        # Reset předchozího stavu před novým pokusem
        st.session_state.parcel_number = ''
        st.session_state.pdf_bytes = None
        
        # Sestavení těla požadavku přesně podle Postman kolekce
        payload = [{
            "customer": {"dsw": str(active_dsw)},
            "deliveryOptions": {"completeness": "CompleteOnly"},
            "shipmentType": "Standard",
            "sender": {"it4emId": int(active_it4emId)},
            "receiver": {
                "info": {
                    "name1": r_name,
                    "name2": "",
                    "contact": {"person": r_name, "phone": "777666444", "email": "dpd@test.cz"}
                },
                "address": {
                    "street": r_street,
                    "postalCode": r_zip,
                    "city": r_city,
                    "houseNumber": r_house,
                    "country": {"isoAlpha2": r_country.upper()}
                }
            },
            "references": {"ref1": ref1, "ref2": ref2, "ref3": "", "ref4": ""},
            "parcels": [{"references": {"ref1": ref1}, "weightGrams": 1500}],
            "services": {}
        }]
        
        # Pro DPD Private doplňujeme notifikaci do uzlu services
        if service_type == "PRIVATE":
            payload[0]["services"] = {"notification": True}
            
        headers = {"x-api-key": st.session_state.api_key, "Content-Type": "application/json"}
        st.session_state.last_request_shipment = payload
        
        # 1. Volání POST /v1/shipments
        with st.spinner("Vytvářím zásilku na serveru DPD..."):
            try:
                ship_res = requests.post(f"{API_BASE}/v1/shipments", headers=headers, json=payload)
                
                try:
                    ship_data = ship_res.json()
                    st.session_state.last_response_shipment = ship_data
                except Exception:
                    ship_data = {}
                    st.session_state.last_response_shipment = ship_res.text
                
                if ship_res.status_code not in [200, 201]:
                    st.error(f"Chyba při zakládání zásilky: HTTP {ship_res.status_code}")
                    st.stop()
                
                # Rekurzivní vyhledávač parcelNumber (prohledá strom odpovědi bez ohledu na hloubku)
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
                    st.error("Číslo zásilky nebylo z odpovědi API detekováno. Prověřte raw data níže.")
                    st.stop()
                    
                st.session_state.parcel_number = p_number
                
            except Exception as e:
                st.error(f"Chyba komunikace při tvorbě zásilky: {str(e)}")
                st.stop()
        
        # 2. Bezprostřední volání POST /v1/parcels/labels pro získání štítku
        if st.session_state.parcel_number:
            with st.spinner("Stahuji tiskový štítek..."):
                label_payload = {
                    "printType": "PDF",
                    "printProperties": {"pageSize": "A6", "labelsPerPage": 1},
                    "parcels": [{"parcelNumber": str(st.session_state.parcel_number)}]
                }
                st.session_state.last_request_label = label_payload
                
                try:
                    label_res = requests.post(f"{API_BASE}/v1/parcels/labels", headers=headers, json=label_payload)
                    
                    if label_res.status_code not in [200, 201]:
                        st.error(f"Chyba při stahování štítku: HTTP {label_res.status_code}")
                        st.session_state.last_response_label = label_res.text
                        st.stop()
                        
                    content_type = label_res.headers.get('Content-Type', '')
                    
                    # Detekce formátu: pokud odpověď začíná hlavičkou %PDF nebo nese příslušný Content-Type
                    if 'application/pdf' in content_type.lower() or label_res.content.startswith(b'%PDF'):
                        st.session_state.pdf_bytes = label_res.content
                        st.session_state.last_response_label = "[Surová binární PDF data štítku - v pořádku stažena]"
                        st.success("Zásilka byla úspěšně vygenerována a štítek je připraven!")
                    else:
                        # Záložní varianta, pokud by se vrátil textový JSON s base64 řetězcem uvnitř
                        label_data = label_res.json()
                        st.session_state.last_response_label = label_data
                        pdf_base64 = ""
                        if "labels" in label_data and len(label_data["labels"]) > 0:
                            pdf_base64 = label_data["labels"][0].get("content", "")
                        elif "content" in label_data:
                            pdf_base64 = label_data.get("content", "")
                            
                        if pdf_base64:
                            st.session_state.pdf_bytes = base64.b64decode(pdf_base64)
                            st.success("Zásilka byla úspěšně vygenerována a štítek dekódován z Base64!")
                        else:
                            st.error("Odpověď na štítek nebyla binární a kód v JSONu chybí.")
                except Exception as e:
                    st.error(f"Chyba komunikace při stahování štítku: {str(e)}")

st.divider()

# --- KROK 4: Výsledek a stažení hotového štítku ---
if st.session_state.parcel_number and st.session_state.pdf_bytes:
    st.header("4. Stažení štítku")
    st.info(f"Úspěšně vytvořeno číslo zásilky: **{st.session_state.parcel_number}**")
    
    st.download_button(
        label="📄 Stáhnout hotový PDF Štítek",
        data=st.session_state.pdf_bytes,
        file_name=f"DPD_Stitek_{st.session_state.parcel_number}.pdf",
        mime="application/pdf"
    )

# --- PANEL PRO LADĚNÍ (Lze rozbalit pro kontrolu raw JSONů) ---
if st.session_state.last_request_shipment or st.session_state.last_response_shipment:
    with st.expander("🛠️ Zobrazit technický detail komunikace (Ladění pro vývojáře)", expanded=False):
        st.subheader("1. Vytvoření zásilky (POST /v1/shipments)")
        st.markdown("**Odeslaný Request (JSON Payload):**")
        st.json(st.session_state.last_request_shipment)
        st.markdown("**Odpověď od DPD API:**")
        if isinstance(st.session_state.last_response_shipment, (dict, list)):
            st.json(st.session_state.last_response_shipment)
        else:
            st.text(st.session_state.last_response_shipment)
            
        if st.session_state.last_request_label:
            st.subheader("2. Generování štítku (POST /v1/parcels/labels)")
            st.markdown("**Odeslaný Request:**")
            st.json(st.session_state.last_request_label)
            st.markdown("**Odpověď od DPD API:**")
            if isinstance(st.session_state.last_response_label, (dict, list)):
                st.json(st.session_state.last_response_label)
            else:
                st.text(st.session_state.last_response_label)