import json
import streamlit as st

@st.cache_data
def cargar_config():
    """Carga el archivo de configuración de colores y divisiones."""
    with open("config_colores.json", "r", encoding="utf-8") as f:
        return json.load(f)
