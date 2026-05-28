import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import base64
import re

API_BASE = "https://geoapi-test.dpd.cz"

# Roztažení na celou šířku
st.set_page_config(page_title="DPD GeoAPI 2.0 Dashboard", layout="wide")

# Seznam států pro našeptávač
countries = {
    "Česká republika": "CZ", "Slovensko": "SK", "Maďarsko": "HU", 
    "Rumunsko": "RO", "Německo": "DE", "Polsko": "PL", "Rakousko": "AT"
}

# Inicializace
if 'api_key' not in st.session_state: st.session_state.api_key = ''
if 'addresses' not in st.session_state: st.session_state.addresses = []

st.title("📦 DPD Shipping Dashboard")

# --- KROK 1 ---
st.header("1. Přihlášení")
api_key_input = st.text_input("API Klíč:", type="password", value=st.session_state.api_key)
if st.button("Načíst data"):
    # (Logika načtení adres zůstává stejná, jen pro stručnost v tomto bloku)
    st.session_state.api_key = api_key_input
    # ... (zde by byla tvoje stávající logika pro načtení adres)

st.divider()

# --- KROK 2 & 3 ---
if st.session_state.addresses:
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.header("2. Služby")
        # Dlaždice pomocí radio
        service_type = st.radio(
            "Zvolte službu:",
            ["CLASSIC", "PRIVATE", "PICKUP", "SHOP_TO_SHOP"],
            format_func=lambda x: {"CLASSIC": "Classic", "PRIVATE": "Private", "PICKUP": "Pickup", "SHOP_TO_SHOP": "Shop to Shop"}[x],
            horizontal=True
        )

        cod_enabled = st.checkbox("Aktivovat dobírku (COD)")
        if cod_enabled:
            cod_amount = st.number_input("Částka dobírky:", min_value=0.0, step=1.0)
        
        st.header("3. Detaily příjemce")
        r_name = st.text_input("Jméno příjemce:")
        r_phone = st.text_input("Telefon:")
        r_email = st.text_input("Email:")
        r_street = st.text_input("Ulice a č.p.:")
        r_city = st.text_input("Město:")
        r_zip = st.text_input("PSČ:")
        country_name = st.selectbox("Stát:", list(countries.keys()))
        country_code = countries[country_name]

    with col_right:
        if service_type in ["PICKUP", "SHOP_TO_SHOP"]:
            st.header("📍 Výdejní místo")
            st.markdown("Zkopírujte ID pobočky z mapy:")
            pickup_id = st.text_input("ID výdejního místa:")
            components.iframe("https://api.dpd.cz/widget/latest/demo.html", height=400)
        
        if st.button("Odeslat zásilku", type="primary"):
            # Logika payloadu s dobírkou
            payload = [{
                # ... zde bude logika sestavení JSONu podle dokumentace
                # Pokud cod_enabled:
                # "services": { "cod": { "amount": cod_amount, "currency": "CZK" } ... }
            }]
            st.success("Zásilka odeslána!")
