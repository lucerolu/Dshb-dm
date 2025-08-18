import streamlit as st
import pandas as pd
import pymysql
import plotly.graph_objects as go
import plotly.express as px
import json
import os
import math
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.colors as mcolors
from matplotlib.colors import LinearSegmentedColormap
from datetime import datetime
from datetime import timedelta
import locale
import io
import requests
import itertools
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
from st_aggrid import ColumnsAutoSizeMode, AgGridTheme
from babel.dates import format_datetime
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import time 



# Cargar configuración desde secrets y convertirla a dict normal
auth_config = dict(st.secrets["auth"])

# Convertir la parte de credenciales a dict normal
credentials = {k: dict(v) if isinstance(v, dict) else v for k, v in auth_config["credentials"].items()}

# Crear autenticador usando una copia modificable
authenticator = stauth.Authenticate(
    credentials,
    auth_config["cookie"]["name"],
    auth_config["cookie"]["key"],
    auth_config["cookie"]["expiry_days"],
    auth_config.get("preauthorized", {}).get("emails", [])
)

# Login
name, authentication_status, username = authenticator.login("Iniciar Sesión", "main")

# Proteger contenido
if authentication_status:
    # Solo aquí guardas el nombre para usar en el sidebar más adelante
    st.session_state["user_name"] = name
    
    #==========================================================================================================
    # -------------- CONFIGURACION GENERAL --------------------------------------------------------------------
    #==========================================================================================================
    st.set_page_config(page_title="Dashboard Compras 2025", layout="wide")

    with open("config_colores.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    colores_sucursales = config["sucursales"]

    API_BASE = "https://fastapi-api-454780168370.us-central1.run.app"

    def obtener_datos_api():
        url = f"{API_BASE}/datos"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            return pd.DataFrame(data)
        except Exception as e:
            st.error(f"Error al obtener datos de la API: {e}")
            return pd.DataFrame()

    def obtener_estado_cuenta_api():
        url = f"{API_BASE}/estado_cuenta"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # EXTRAER los datos correctamente
            lista_datos = data.get("datos", [])
            fecha_corte = pd.to_datetime(data.get("fecha_corte"))

            df = pd.DataFrame(lista_datos)

            if df.empty:
                return pd.DataFrame(), None

            return df, fecha_corte

        except Exception as e:
            st.error(f"Error al obtener estado de cuenta de la API: {e}")
            return pd.DataFrame(), None


    def mostrar_fecha_actualizacion():
        try:
            respuesta = requests.get(f"{API_BASE}/ultima_actualizacion")
            if respuesta.status_code == 200:
                data = respuesta.json()
                fecha_dt = datetime.fromisoformat(data['fecha'])
                
                fecha_formateada = format_datetime(fecha_dt, "d 'de' MMMM 'de' yyyy, h:mm a", locale="es")

                st.markdown(
                    f'<p style="background-color:#DFF2BF; color:#4F8A10; padding:10px; border-radius:5px;">'
                    f'🕒 <b>Última actualización de datos:</b> {fecha_formateada}<br>'
                    f'📋 <i>{data["descripcion"]}</i>'
                    f'</p>', unsafe_allow_html=True
                )
            else:
                st.warning("No se pudo obtener la fecha de última actualización.")
        except Exception as e:
            st.error(f"Error de conexión con la API: {e}")

    # ----------------------------------------------- OBTENER DATOS -------------------------------------------------------------------------------
    df = obtener_datos_api()
    if not df.empty:
        df = df.dropna(subset=["sucursal"])

        meses_es = {
            'January': 'Enero', 'February': 'Febrero', 'March': 'Marzo', 'April': 'Abril',
            'May': 'Mayo', 'June': 'Junio', 'July': 'Julio', 'August': 'Agosto',
            'September': 'Septiembre', 'October': 'Octubre', 'November': 'Noviembre', 'December': 'Diciembre'
        }

        df["mes_dt"] = pd.to_datetime(df["mes"])
        df["mes_nombre"] = df["mes_dt"].dt.month_name().map(meses_es) + " " + df["mes_dt"].dt.year.astype(str)
        df["mes_period"] = df["mes_dt"].dt.to_period("M")
        df = df.sort_values("mes_dt")
        # Orden ascendente (para gráficas que van de enero a diciembre)
        orden_meses_asc = (
            df.drop_duplicates(subset="mes_period")
            .sort_values("mes_period", ascending=True)["mes_nombre"]
            .tolist()
        )

        # Orden descendente (para gráficas que van de mes más reciente al más antiguo)
        orden_meses_desc = orden_meses_asc[::-1]
        orden_meses = orden_meses_asc

        # ------------------------------------------ DIVISIONES ----------------------------------------------------
        divisiones = config["divisiones"]
        mapa_codigos = {}
        colores_divisiones = {}
        for division, info in divisiones.items():
            for codigo in info["codigos"]:
                mapa_codigos[codigo] = division
            colores_divisiones[division] = info["color"]

        df["division"] = df["codigo_normalizado"].map(mapa_codigos)
        df_divisiones = df.dropna(subset=["division"])  # descarta cuentas sin división
        df_divisiones["mes_dt"] = pd.to_datetime(df_divisiones["mes"])
        df_divisiones["mes_nombre"] = df_divisiones["mes_dt"].dt.month_name().map(meses_es) + " " + df_divisiones["mes_dt"].dt.year.astype(str)
    else:
        st.warning("No hay datos disponibles para mostrar.")


    #------------------------------ MAPEO COLOR ABREVIATURA -------------------------------------------------------------------------
    # Cargar configuración de colores
    with open("config_colores.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    # Crear un dict {codigo: (color, abreviatura)}
    codigo_division_map = {}
    for division, datos in config["divisiones"].items():
        for cod in datos["codigos"]:
            codigo_division_map[cod] = {
                "color": datos["color"],
                "abreviatura": datos["abreviatura"],
                "division": division
            }

    # ------------------- MENU LATERAL -------------------------------------------------
    with st.sidebar:
        # Mostrar bienvenida solo si el usuario está autenticado
        if "user_name" in st.session_state:
            st.markdown(f"👋 **Bienvenido {st.session_state['user_name']}**")

        # Menú para las vistas
        opcion = st.selectbox("Selecciona una vista", [
            "Estado de cuenta",
            "Resumen General",
            "Compra por División",
            "Compra por Cuenta",
            "Compra por Sucursal",
            "Vista por Sucursal",
            "Estado de Ligado",
        ])

        # Botón cerrar sesión
        authenticator.logout("Cerrar sesión", "sidebar")

        # Fecha de última actualización al final del sidebar
        mostrar_fecha_actualizacion()

    # ==========================================================================================================
    # ============================= ESTADO DE CUENTA ============================================================
    # ==========================================================================================================
    if opcion == "Estado de cuenta":
        st.title("Cuadro de estado de cuenta")
        
        df_estado_cuenta, fecha_corte = obtener_estado_cuenta_api()
        if df_estado_cuenta.empty or fecha_corte is None:
            st.warning("No hay datos de estado de cuenta.")
        else:
            st.markdown(f"### Estado de cuenta actualizado a {fecha_corte.strftime('%d/%m/%Y')}")
            #------------------------------------- TARJETAS DE CREDITO DISPONIBLE --------------------------------------------------
            # Límite de crédito
            CREDITO_MAX = 180_000_000
            # Obtener los datos
            df_estado_cuenta, fecha_corte = obtener_estado_cuenta_api()

            if not df_estado_cuenta.empty:
                total_estado_cuenta = df_estado_cuenta["total"].sum()

                credito_disponible = CREDITO_MAX - total_estado_cuenta
                porcentaje_disponible = (credito_disponible / CREDITO_MAX) * 100
                porcentaje_usado = (total_estado_cuenta / CREDITO_MAX) * 100

                # Crear las tarjetas
                col1, col2, col3 = st.columns(3)
                col1.metric("💰 Crédito disponible", f"${credito_disponible:,.2f}")
                col2.metric("📊 % Crédito disponible", f"{porcentaje_disponible:.2f}%")
                col3.metric("📈 % Crédito usado", f"{porcentaje_usado:.2f}%")
            else:
                st.info("No hay datos disponibles para mostrar el crédito.")
            st.markdown("<div class='spacer'></div>", unsafe_allow_html=True)
            #----------------------------------------- TARJETAS DE VENCIMIENTO -------------------------------------------------------------------
            df_estado_cuenta["fecha_exigibilidad"] = pd.to_datetime(df_estado_cuenta["fecha_exigibilidad"])
            hoy = pd.to_datetime(datetime.today().date())
            
            total_vencido = df_estado_cuenta[df_estado_cuenta["fecha_exigibilidad"] < hoy]["total"].sum()
            por_vencer_30 = df_estado_cuenta[
                (df_estado_cuenta["fecha_exigibilidad"] >= hoy) &
                (df_estado_cuenta["fecha_exigibilidad"] <= hoy + timedelta(days=30))
            ]["total"].sum()
            por_vencer_90 = df_estado_cuenta[
                df_estado_cuenta["fecha_exigibilidad"] > hoy + timedelta(days=90)
            ]["total"].sum()
            
            col1, col2, col3 = st.columns(3)
            col1.metric("🔴 Total vencido", f"${total_vencido:,.2f}")
            col2.metric("🟡 Por vencer en 30 días", f"${por_vencer_30:,.2f}")
            col3.metric("🟢 Por vencer >90 días", f"${por_vencer_90:,.2f}")

            #-------------------------------------- GRAFICO DE LÍNEAS DEL ESTADO DE CUENTA -----------------------------------------------------------
            # ------------------ Cargar configuración de colores y divisiones ------------------
            with open("config_colores.json", "r", encoding="utf-8") as f:
                config = json.load(f)

            divisiones = config["divisiones"]
            colores_sucursales = config["sucursales"]

            # ------------------ Función para abreviatura ------------------
            def obtener_abreviatura(codigo):
                for division, info in divisiones.items():
                    if codigo in info["codigos"]:
                        return info["abreviatura"]
                return ""

            # ------------------ Preparar DataFrame ------------------
            df_estado_cuenta["fecha_exigibilidad"] = pd.to_datetime(df_estado_cuenta["fecha_exigibilidad"])
            df_estado_cuenta["codigo"] = df_estado_cuenta["codigo_6digitos"].astype(str)

            df_estado_cuenta["abreviatura"] = df_estado_cuenta["codigo"].apply(obtener_abreviatura)
            df_estado_cuenta["cuenta_sucursal"] = (
                df_estado_cuenta["codigo"] + " (" + df_estado_cuenta["abreviatura"] + ") - " + df_estado_cuenta["sucursal"]
            )

            # Crear diccionario cuenta_sucursal -> color_sucursal
            color_cuentas = {
                row["cuenta_sucursal"]: colores_sucursales.get(row["sucursal"], "#808080")
                for _, row in df_estado_cuenta.drop_duplicates("cuenta_sucursal").iterrows()
            }

            # Convertir fechas a strings ordenadas para que se comporten como categorías
            df_estado_cuenta["fecha_exigibilidad_str"] = df_estado_cuenta["fecha_exigibilidad"].dt.strftime("%d/%m/%Y")

            # Ordenar las fechas para que aparezcan correctamente en el eje
            fechas_ordenadas = sorted(df_estado_cuenta["fecha_exigibilidad_str"].unique(),
                                    key=lambda x: pd.to_datetime(x, format="%d/%m/%Y"))

            # Crear gráfico usando eje X categórico
            fig = px.line(
                df_estado_cuenta,
                x="fecha_exigibilidad_str",  # eje categórico
                y="total",
                color="cuenta_sucursal",
                color_discrete_map=color_cuentas,
                category_orders={"fecha_exigibilidad_str": fechas_ordenadas},  # asegura orden correcto
                custom_data=["sucursal", "codigo", "abreviatura"]
            )

            fig.update_traces(
                hovertemplate=(
                    "<b>Fecha:</b> %{x}<br>"
                    "<b>Código:</b> %{customdata[1]}<br>"
                    "<b>Sucursal:</b> %{customdata[0]}<br>"
                    "<b>División:</b> %{customdata[2]}<br>"
                    "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
                )
            )

            fig.update_layout(
                xaxis_title="Fecha de exigibilidad",
                yaxis_title="Monto",
                hovermode="closest",  # <-- cambiar aquí
                template="plotly_white"
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "scrollZoom": True,
                    "modeBarButtonsToKeep": [
                        "toImage",
                        "zoom2d",
                        "autoScale2d",
                        "toggleFullscreen"
                    ],
                    "displaylogo": False
                }
            )

            #------------------------------------------ TABLA: ESTADO DE CUENTA -----------------------------------------------------------------------
            # --- Preparar datos ---
            df_estado_cuenta["fecha_exigibilidad"] = pd.to_datetime(df_estado_cuenta["fecha_exigibilidad"])
            df_estado_cuenta["fecha_exigibilidad_str"] = df_estado_cuenta["fecha_exigibilidad"].dt.strftime("%d/%m/%Y")

            df_pivot = df_estado_cuenta.pivot_table(
                index=["sucursal", "codigo_6digitos"],
                columns="fecha_exigibilidad_str",
                values="total",
                aggfunc="sum",
                fill_value=0,
                margins=True,
                margins_name="Total"
            )

            # Ordenar columnas por fecha
            cols_ordenadas = sorted(
                [c for c in df_pivot.columns if c != "Total"],
                key=lambda x: datetime.strptime(x, "%d/%m/%Y")
            )
            if "Total" in df_pivot.columns:
                cols_ordenadas.append("Total")
            df_pivot = df_pivot[cols_ordenadas]

            df_pivot.index = df_pivot.index.set_names(["sucursal", "codigo"])
            df_reset = df_pivot.reset_index()
            df_reset["codigo"] = df_reset["codigo"].astype(str)

            # --- Separar fila total ---
            mascara_total = (
                df_reset["codigo"].str.strip().str.lower() == "total"
            ) | (
                df_reset["sucursal"].str.strip().str.lower() == "total"
            )
            total_row = df_reset[mascara_total].copy()
            data_sin_total = df_reset[~mascara_total].copy()

            # Columnas numéricas excluyendo índices y columna Total
            ultima_col = data_sin_total.columns[-1]
            numeric_cols_sin_total = [c for c in data_sin_total.columns if c not in ["sucursal", "codigo", ultima_col]]

            # --- Formateador de valores con comas y 2 decimales ---
            value_formatter = JsCode("""
            function(params) { 
                if (params.value == null) return '0.00';
                return params.value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
            }
            """)

            # --- Degradado por celda (excluye la fila Total) ---
            min_val = data_sin_total[numeric_cols_sin_total].min().min()
            max_val = data_sin_total[numeric_cols_sin_total].max().max()
            gradient_code = JsCode(f"""
            function(params) {{
                const totalCol = '{ultima_col}';
                if (params.node.rowPinned || 
                    (params.data && (
                        (typeof params.data.codigo === 'string' && params.data.codigo.trim().toLowerCase() === 'total') ||
                        (typeof params.data.sucursal === 'string' && params.data.sucursal.trim().toLowerCase() === 'total')
                    ))
                ) {{
                    return {{
                        backgroundColor: '#0B083D',
                        color: 'white',
                        fontWeight: 'bold',
                        textAlign: 'left'  // fila Total alineada a la izquierda
                    }};
                }}
                if (params.colDef.field === totalCol) {{
                    return {{
                        backgroundColor: '#0B083D',
                        color: 'white',
                        fontWeight: 'bold',
                        textAlign: 'left'  // columna Total alineada a la izquierda
                    }};
                }}
                let val = params.value;
                let min = {min_val};
                let max = {max_val};
                if (!isNaN(val) && max > min) {{
                    let ratio = (val - min) / (max - min);
                    let r,g,b;
                    if(ratio <= 0.5) {{
                        let t = ratio/0.5;
                        r = Math.round(117 + t*(232-117));
                        g = Math.round(222 + t*(229-222));
                        b = Math.round(84 + t*(70-84));
                    }} else {{
                        let t = (ratio-0.5)/0.5;
                        r = 232; g = Math.round(229 + t*(96-229)); b = 70;
                    }}
                    return {{ backgroundColor: `rgb(${{r}},${{g}},${{b}})`, textAlign:'left' }};
                }}
                return {{ textAlign:'left' }};
            }}
            """)

            # --- Reordenar columnas para que "codigo" sea la primera y "sucursal" la segunda ---
            columnas = list(data_sin_total.columns)
            if "codigo" in columnas and "sucursal" in columnas:
                columnas.remove("codigo")
                columnas.remove("sucursal")
                data_sin_total = data_sin_total[["codigo", "sucursal"] + columnas]

            # --- Configuración inicial del grid ---
            gb = GridOptionsBuilder.from_dataframe(data_sin_total)
            gb.configure_default_column(resizable=True, filter=False, valueFormatter=value_formatter)

            # Columna "codigo" anclada y alineada a la derecha
            gb.configure_column(
                "codigo",
                pinned="left",
                minWidth=90,
                width=90,
                cellStyle={
                    'backgroundColor': '#0B083D',
                    'color': 'white',
                    'fontWeight': 'bold',
                    'textAlign': 'right'
                }
            )

            # Columna "sucursal" sin anclar pero con mismo estilo
            gb.configure_column(
                "sucursal",
                minWidth=130,
                width=130,
                cellStyle={
                    'backgroundColor': '#0B083D',
                    'color': 'white',
                    'fontWeight': 'bold',
                    'textAlign': 'right'
                }
            )

            # Columnas numéricas con degradado y header alineado a la izquierda
            for col in numeric_cols_sin_total:
                gb.configure_column(
                    col,
                    cellStyle=gradient_code,
                    valueFormatter=value_formatter,
                    minWidth=100,  # mínimo ancho para evitar aplastamiento en móviles
                    headerClass='header-left'
                )

            # Columna Total con estilo y alineada a la izquierda
            gb.configure_column(
                ultima_col,
                cellStyle={
                    'backgroundColor': '#0B083D',
                    'color': 'white',
                    'fontWeight': 'bold',
                    'textAlign': 'left'
                },
                sortable=True,  
                valueFormatter=value_formatter,
                minWidth=120,
                headerClass='header-left'
            )

            # --- CSS para headers alineados a la izquierda ---
            custom_css = {
                ".header-left": {
                    "text-align": "left"
                },
                ".ag-center-cols-container .ag-row": {
                    "height": "20px",
                    "line-height": "16px",
                    "padding-top": "2px",
                    "padding-bottom": "2px"
                },
                ".ag-pinned-left-cols-container .ag-row": {
                    "height": "20px",
                    "line-height": "16px",
                    "padding-top": "2px",
                    "padding-bottom": "2px"
                }
            }


            # --- Script para scroll horizontal en móviles y ajuste solo en pantallas grandes ---
            on_grid_ready = JsCode("""
            function(params) {
                function ajustarColumnas() {
                    if (window.innerWidth <= 768) {
                        params.api.resetColumnState();
                    } else {
                        params.api.sizeColumnsToFit();
                    }
                }

                // Ejecutar de inmediato
                ajustarColumnas();

                // Ejecutar un poco después de que todo se cargue
                setTimeout(ajustarColumnas, 300);

                // Escuchar cambios de tamaño reales de ventana
                window.addEventListener('resize', ajustarColumnas);

                // Observador para detectar cambios de tamaño del contenedor
                const gridDiv = params.api.gridBodyCtrl.eGridBody;
                if (window.ResizeObserver) {
                    const ro = new ResizeObserver(() => ajustarColumnas());
                    ro.observe(gridDiv);
                }
            }
            """)

            grid_options = gb.build()
            grid_options["onGridReady"] = on_grid_ready

            # --- Fila Total fija al final ---
            pinned_total_row = total_row.copy()
            for col in pinned_total_row.columns:
                if col in numeric_cols_sin_total + [ultima_col]:
                    pinned_total_row[col] = pinned_total_row[col]
            grid_options['pinnedBottomRowData'] = pinned_total_row.to_dict('records')

            # --- Renderizado final ---
            AgGrid(
                data_sin_total,
                gridOptions=grid_options,
                custom_css=custom_css,
                height=800,
                allow_unsafe_jscode=True,
                theme=AgGridTheme.ALPINE,
                fit_columns_on_grid_load=False,  # desactiva ajuste automático
                columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
                enable_enterprise_modules=False
            )

            #--------------------- BOTON DE DESCARGA -----------
            def to_excel(df):
                import io
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, sheet_name='EstadoCuenta')
                return output.getvalue()
            
            excel_data = to_excel(df_pivot)
            st.download_button(
                label="Descargar tabla en Excel",
                data=excel_data,
                file_name=f"estado_cuenta_{fecha_corte.strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            #----------------------------------- GRAFICO DE ANILLOS ------------------------------------------------------------------------------------------------------------------------
            # --- helper para formato moneda ---
            def fmt(v):
                try:
                    return f"${float(v):,.2f}"
                except Exception:
                    return "$0.00"

            # Asegura que estas columnas existan y tipos correctos
            df_estado_cuenta["fecha_exigibilidad_str"] = df_estado_cuenta["fecha_exigibilidad"].dt.strftime("%d/%m/%Y")
            df_estado_cuenta["codigo"] = df_estado_cuenta["codigo_6digitos"].astype(str)

            # Loop: 2 gráficos por fila
            for i in range(0, len(fechas_ordenadas), 2):
                col1, col2 = st.columns(2)
                for j, col in enumerate([col1, col2]):
                    if i + j >= len(fechas_ordenadas):
                        break

                    fecha = fechas_ordenadas[i + j]
                    # --- dataset de esa fecha ---
                    df_fecha_raw = df_estado_cuenta[df_estado_cuenta["fecha_exigibilidad_str"] == fecha].copy()

                    # MUY IMPORTANTE: agrupar por sucursal + cuenta para evitar duplicados
                    df_fecha = (
                        df_fecha_raw.groupby(["sucursal", "cuenta_sucursal", "codigo", "abreviatura"], as_index=False)["total"]
                        .sum()
                    )

                    # Totales por sucursal (para texto del nodo padre)
                    tot_por_suc = df_fecha.groupby("sucursal", as_index=False)["total"].sum().rename(columns={"total": "total_sucursal"})
                    map_tot_suc = dict(zip(tot_por_suc["sucursal"], tot_por_suc["total_sucursal"]))

                    # --- construir nodos: ids, parents, values, labels, colors, text, hover ---
                    ids, parents, values, labels, colors, texts, hovertexts = [], [], [], [], [], [], []

                    # Nodos de sucursal (padres)
                    for _, r in tot_por_suc.iterrows():
                        suc = r["sucursal"]
                        t_suc = r["total_sucursal"]
                        sid = f"S|{suc}"
                        ids.append(sid)
                        parents.append("")                  # raíz implícita
                        values.append(t_suc)                # branchvalues='total' y valor del padre = suma cuentas
                        labels.append(suc)
                        colors.append(colores_sucursales.get(suc, "#808080"))
                        texts.append(fmt(t_suc))            # muestra total sucursal en el anillo interno
                        hovertexts.append(
                            f"<b>Fecha:</b> {fecha}<br>"
                            f"<b>Sucursal:</b> {suc}<br>"
                            f"<b>Total Sucursal:</b> {fmt(t_suc)}"
                        )

                    # Nodos de cuenta (hijas)
                    # Orden estable por sucursal para consistencia visual
                    df_fecha = df_fecha.sort_values(["sucursal", "cuenta_sucursal"]).reset_index(drop=True)
                    for _, r in df_fecha.iterrows():
                        suc = r["sucursal"]
                        cuenta = r["cuenta_sucursal"]
                        monto = float(r["total"])
                        codigo = r["codigo"]
                        abrev = r["abreviatura"]
                        t_suc = map_tot_suc.get(suc, 0.0)

                        cid = f"A|{suc}|{cuenta}"
                        ids.append(cid)
                        parents.append(f"S|{suc}")
                        values.append(monto)
                        labels.append(cuenta)                      # etiqueta externa = cuenta (como querías)
                        colors.append(colores_sucursales.get(suc, "#808080"))   # color por sucursal
                        texts.append(fmt(monto))                   # muestra monto cuenta en el anillo externo
                        hovertexts.append(
                            f"<b>Fecha:</b> {fecha}<br>"
                            f"<b>Código:</b> {codigo}<br>"
                            f"<b>Sucursal:</b> {suc}<br>"
                            f"<b>División:</b> {abrev}<br>"
                            f"<b>Monto Cuenta:</b> {fmt(monto)}<br>"
                            f"<b>Total Sucursal:</b> {fmt(t_suc)}"
                        )

                    # --- Sunburst GO: control total, sin customdata que se desordene ---
                    fig = go.Figure(
                        go.Sunburst(
                            ids=ids,
                            parents=parents,
                            values=values,
                            labels=labels,
                            text=texts,                 # monto visible en cada porción
                            textinfo="label+text",
                            insidetextorientation="horizontal",
                            marker=dict(
                                colors=colors,
                                line=dict(color="white", width=1)
                            ),
                            branchvalues="total",
                            hovertext=hovertexts,
                            hovertemplate="%{hovertext}<extra></extra>"
                        )
                    )

                    fig.update_layout(
                        title={
                            'text': f"Distribución por cuenta - {fecha}",
                            'x': 0.5,            # centrado
                            'xanchor': 'center', # ancla en el centro
                            'yanchor': 'top'     # opcional: ancla arriba
                        },
                        title_font=dict(size=18, color="#E1E1EC", family="Arial"),
                        template="plotly_white",
                        margin=dict(t=60, l=0, r=0, b=0)
                    )


                    col.plotly_chart(fig, use_container_width=True)


    # ==========================================================================================================
    # ============================== RESUMEN GENERAL ==========================================
    # ==========================================================================================================
    elif opcion == "Resumen General":
        st.title("Resumen General de Compras")

        # ----------------- Selector de periodo compacto -----------------
        opciones_periodo = ["Año Natural", "Año Fiscal"]
        periodo = st.radio("Selecciona periodo", opciones_periodo, horizontal=True)

        # Detectar años disponibles
        df["fecha"] = pd.to_datetime(df["mes"])  # asegúrate de tener columna 'mes' en formato fecha
        años_disponibles = sorted(df["fecha"].dt.year.unique())
        año_seleccionado = st.selectbox("Selecciona el año", años_disponibles, index=len(años_disponibles)-1)
        st.markdown("<br><br>", unsafe_allow_html=True)

        # Filtrar por periodo
        if periodo == "Año Natural":
            df_filtrado = df[df["fecha"].dt.year == año_seleccionado]
            titulo_periodo = f"{año_seleccionado}"

        elif periodo == "Año Fiscal":
            # Año fiscal: 1 nov (año_seleccionado-1) -> 31 oct (año_seleccionado)
            inicio_fiscal = pd.Timestamp(año_seleccionado-1, 11, 1)
            fin_fiscal = pd.Timestamp(año_seleccionado, 10, 31)
            df_filtrado = df[(df["fecha"] >= inicio_fiscal) & (df["fecha"] <= fin_fiscal)]
            titulo_periodo = f"Fiscal {año_seleccionado}"

        #--------------- TARJETAS: total comprado en el año y en el mes corriente  ------------------------------------------
        ahora = datetime.now()
        ahora_pd = pd.Timestamp(ahora)
        mes_actual_period = ahora_pd.to_period("M")
        mes_actual_esp = meses_es.get(ahora.strftime("%B"), "") + " " + str(ahora.year)

        col1, col2 = st.columns(2)

        with col1:
            total_anual = df_filtrado["monto"].sum()
            st.metric(f"Total comprado ({titulo_periodo})", f"${total_anual:,.2f}")

        with col2:
            total_mes_actual = df_filtrado[df_filtrado["mes_period"] == mes_actual_period]["monto"].sum()
            st.metric(f"Total comprado en {mes_actual_esp}", f"${total_mes_actual:,.2f}")

        st.markdown("<br><br>", unsafe_allow_html=True)

        # ------------------------------------ GÁFICA DE LÍNEAS DEL TOTAL GENERAL  -----------------------------------------------------------------------------------------------------------------
        # Agrupar y conservar solo los meses que realmente existen en df_filtrado
        df_total_mes = df_filtrado.groupby("mes_nombre")["monto"].sum()

        # Ordenar los meses que sí están presentes
        df_total_mes = df_total_mes.reindex([m for m in orden_meses if m in df_total_mes.index])

        # Crear figura
        fig_total = go.Figure()
        fig_total.add_trace(go.Scatter(
            x=df_total_mes.index,
            y=df_total_mes.values,
            mode="lines+markers",
            name="Total",
            line=dict(color="blue"),
            hovertemplate="%{x}<br>Total: $%{y:,.2f}<extra></extra>"
        ))

        fig_total.update_layout(
            xaxis_title="Mes",
            yaxis_title="Monto",
            yaxis_tickformat=","
        )

        st.markdown("### Evolución mensual del total comprado")
        st.plotly_chart(fig_total, use_container_width=True)

        # ----------------------------------------- TABLA: TOTAL COMPRADO POR MES --------------------------------------------------------------------------------------------
        st.markdown("### Total comprado por mes")

        # Agrupar
        tabla_horizontal = df_filtrado.groupby("mes_nombre")["monto"].sum()

        # Filtrar y ordenar solo los meses presentes en df_filtrado
        meses_presentes = [m for m in orden_meses if m in tabla_horizontal.index]
        tabla_horizontal = tabla_horizontal.reindex(meses_presentes)

        # Crear DataFrame y transponer
        tabla_horizontal_df = pd.DataFrame(tabla_horizontal).T
        tabla_horizontal_df.index = ["Total Comprado"]

        # Calcular Total
        tabla_horizontal_df["Total"] = tabla_horizontal_df.sum(axis=1)

        # Reordenar columnas
        cols = [col for col in tabla_horizontal_df.columns if col != "Total"] + ["Total"]
        tabla_horizontal_df = tabla_horizontal_df[cols]

        # Formatear montos como moneda
        tabla_html = tabla_horizontal_df.applymap(lambda x: f"${x:,.2f}")

        # HTML dinámico
        header_html = ''.join([
            f'<th style="background-color:#390570; color:white; padding:8px; text-align:left;">{col}</th>'
            for col in tabla_html.columns
        ])

        row_html = ''.join([
            f'<td style="padding:8px; text-align:left;">{val}</td>'
            for val in tabla_html.iloc[0]
        ])

        html_table = f"""
        <div style="overflow-x:auto; width: 100%;">
        <table style="border-collapse:collapse; min-width:800px; width:100%;">
            <thead>
            <tr>
                <th style="background-color:#390570; padding:8px; color:white; text-align:left; position:sticky; left:0; z-index:1;">
                </th>
                {header_html}
            </tr>
            </thead>
            <tbody>
            <tr>
                <td style="padding:8px; text-align:right; background-color:#281436; color:white; font-weight:bold; position:sticky; left:0; z-index:1;">
                Total Comprado
                </td>
                {row_html}
            </tr>
            </tbody>
        </table>
        </div>
        """

        st.markdown(html_table, unsafe_allow_html=True)

    # -------------------------------------------- GRÁFICA: Total comprado por mes ------------------------------------------------------------------------------
        #st.markdown("### Gráfica de Total comprado por mes")
        # Agrupar de nuevo (en bruto, sin formato)
        df_mensual = df_filtrado.groupby("mes_nombre", as_index=False)["monto"].sum()
        df_mensual["mes_nombre"] = pd.Categorical(df_mensual["mes_nombre"], categories=orden_meses, ordered=True)
        df_mensual = df_mensual.sort_values("mes_nombre")

        # Formato de texto
        df_mensual["texto_monto"] = df_mensual["monto"].apply(lambda x: f"${x:,.2f}")

        # Crear gráfica
        fig = go.Figure()

        fig.add_trace(go.Bar(
            y=df_mensual["mes_nombre"],
            x=df_mensual["monto"],
            orientation='h',
            marker_color="#1f77b4",  # azul default
            text=df_mensual["texto_monto"],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>Total: %{text}<extra></extra>"
        ))

        # Ajustes visuales
        altura_total = max(400, len(df_mensual) * 40)

        fig.update_layout(
            xaxis_title="Monto de compra (MXN)",
            yaxis_title="Mes",
            xaxis_tickformat=",",
            height=altura_total,
            margin=dict(r=70),
            bargap=0.25
        )

        st.plotly_chart(fig, use_container_width=True)
        st.markdown("<br><br>", unsafe_allow_html=True)

        #------------------------------------------ COMPARATIVO: MES VS MES ANTERIOR ---------------------------------------------------------------------------------------------------------
        st.markdown("### Comparativo de compras mensuales")
        st.markdown("#### Compra vs mes anterior")

        # Agrupar y ordenar por mes
        df_mensual = df_filtrado.groupby("mes_nombre", as_index=False)["monto"].sum()
        df_mensual["mes_nombre"] = pd.Categorical(df_mensual["mes_nombre"], categories=orden_meses, ordered=True)
        df_mensual = df_mensual.sort_values("mes_nombre").reset_index(drop=True)

        # Calcular diferencia y variación
        df_mensual["diferencia"] = df_mensual["monto"].diff().fillna(0)
        df_mensual["variacion_pct"] = df_mensual["monto"].pct_change().fillna(0) * 100

        # Flechas al final
        df_mensual["monto_str"] = df_mensual["monto"].apply(lambda x: f"${x:,.2f}")
        df_mensual["diferencia_str"] = df_mensual["diferencia"].apply(
            lambda x: f"${x:,.2f} ⬆" if x > 0 else f"${x:,.2f} ⬇" if x < 0 else "$0 ➖"
        )
        df_mensual["variacion_str"] = df_mensual["variacion_pct"].apply(
            lambda x: f"{x:.1f}% ⬆" if x > 0 else f"{x:.1f}% ⬇" if x < 0 else "0.0% ➖"
        )

        # Tabla base
        df_comp = df_mensual[["mes_nombre", "monto_str", "diferencia_str", "variacion_str"]]
        df_comp.columns = ["Mes", "Total Comprado", "Diferencia ($)", "Variación (%)"]

        # Convertir a HTML
        def construir_tabla_comparativa(df):
            estilos_css = """
            <style>
                .tabla-wrapper {
                    overflow-x: auto;
                    width: 100%;
                }

                .tabla-comparativa {
                    min-width: 100%;
                    width: max-content;
                    border-collapse: collapse;
                    table-layout: auto;
                }

                .tabla-comparativa thead th {
                    background-color: #0B083D;
                    color: white;
                    padding: 8px;
                    white-space: nowrap;
                    position: sticky;
                    top: 0;
                    z-index: 3;
                    border: 1px solid white;
                }

                .tabla-comparativa thead th:first-child {
                    text-align: right;
                    left: 0;
                    position: sticky;
                    z-index: 5;
                }

                .tabla-comparativa thead th:not(:first-child) {
                    text-align: left;
                }

                .tabla-comparativa td, .tabla-comparativa th {
                    padding: 8px;
                    font-size: 14px;
                    white-space: nowrap;
                    border: 1px solid white;
                }

                .tabla-comparativa tbody td:first-child,
                .tabla-comparativa tfoot td:first-child {
                    position: sticky;
                    left: 0;
                    background-color: #0B083D;
                    color: white;
                    font-weight: bold;
                    text-align: right;
                    z-index: 4;
                }

                .tabla-comparativa tbody td:not(:first-child) {
                    text-align: left;
                }

                .subida {
                    background-color: #7D1F08;
                    color: white;
                }

                .bajada {
                    background-color: #184E08;
                    color: white;
                }

                .neutra {
                    color: white;
                }
            </style>
            """

            html = f"{estilos_css}<div class='tabla-wrapper'><table class='tabla-comparativa'>"
            html += (
                "<thead><tr>"
                "<th>Mes</th>"
                "<th>Total Comprado</th>"
                "<th>Diferencia ($)</th>"
                "<th>Variación (%)</th>"
                "</tr></thead><tbody>"
            )

            for _, row in df.iterrows():
                html += "<tr>"

                # Determinar clase de color
                clase_color = (
                    "subida" if "⬆" in row["Diferencia ($)"] else
                    "bajada" if "⬇" in row["Diferencia ($)"] else
                    "neutra"
                )

                html += f"<td>{row['Mes']}</td>"
                html += f"<td class='{clase_color}'>{row['Total Comprado']}</td>"
                html += f"<td class='{clase_color}'>{row['Diferencia ($)']}</td>"
                html += f"<td class='{clase_color}'>{row['Variación (%)']}</td>"

                html += "</tr>"

            html += "</tbody></table></div>"
            return html

        # Mostrar tabla
        tabla_html = construir_tabla_comparativa(df_comp)
        st.markdown(tabla_html, unsafe_allow_html=True)
        st.markdown("<div class='spacer'></div>", unsafe_allow_html=True)

        # --------------------------------------- GRÁFICA DE DIFERENCIAS MENSUALES --------------------------------------------------------------------------------------------
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("### Variación de compras respecto al mes anterior")

        # Agrupar y ordenar por mes
        df_mensual = df_filtrado.groupby("mes_nombre", as_index=False)["monto"].sum()
        df_mensual["mes_nombre"] = pd.Categorical(df_mensual["mes_nombre"], categories=orden_meses, ordered=True)
        df_mensual = df_mensual.sort_values("mes_nombre").reset_index(drop=True)

        # Calcular diferencias
        df_mensual["diferencia"] = df_mensual["monto"].diff().fillna(0)
        df_mensual["color"] = df_mensual["diferencia"].apply(lambda x: "#f81515" if x >= 0 else "#33FF00")
        df_mensual["texto"] = df_mensual["diferencia"].apply(lambda x: f"${x:,.2f}")

        # Crear gráfica
        fig_dif = go.Figure()

        fig_dif.add_trace(go.Bar(
            x=df_mensual["mes_nombre"],
            y=df_mensual["diferencia"],
            marker_color=df_mensual["color"],
            text=df_mensual["texto"],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{x}<br>Diferencia: %{text}<extra></extra>"
        ))

        # Ajustes visuales
        fig_dif.update_layout(
            title="Diferencia mensual de compras vs mes anterior",
            xaxis_title="Mes",
            yaxis_title="Diferencia en monto (MXN)",
            yaxis=dict(zeroline=True, zerolinecolor="black"),
            height=450,
            margin=dict(r=70)
        )

        st.plotly_chart(fig_dif, use_container_width=True)

    # ================================================================================================================================
    # ============================================= COMPRA POR DIVISION ==================================================================
    # ================================================================================================================================
    elif opcion == "Compra por División":
        st.title("Distribución de Compras por División - 2025")
        # ----------------- Selector de periodo compacto -----------------
        opciones_periodo = ["Año Natural", "Año Fiscal"]
        periodo = st.radio("Selecciona periodo", opciones_periodo, horizontal=True)

        # Detectar años disponibles
        df["fecha"] = pd.to_datetime(df["mes"])  # asegúrate de tener columna 'mes' en formato fecha
        años_disponibles = sorted(df["fecha"].dt.year.unique())
        año_seleccionado = st.selectbox("Selecciona el año", años_disponibles, index=len(años_disponibles)-1)
        st.markdown("<br><br>", unsafe_allow_html=True)

        # Filtrar por periodo
        if periodo == "Año Natural":
            df_filtrado = df[df["fecha"].dt.year == año_seleccionado]
            titulo_periodo = f"{año_seleccionado}"

        elif periodo == "Año Fiscal":
            # Año fiscal: 1 nov (año_seleccionado-1) -> 31 oct (año_seleccionado)
            inicio_fiscal = pd.Timestamp(año_seleccionado-1, 11, 1)
            fin_fiscal = pd.Timestamp(año_seleccionado, 10, 31)
            df_filtrado = df[(df["fecha"] >= inicio_fiscal) & (df["fecha"] <= fin_fiscal)]
            titulo_periodo = f"Fiscal {año_seleccionado}"
        st.markdown("<br><br>", unsafe_allow_html=True)

        # Usar df_filtrado en lugar del df original
        df_divisiones_filtrado = df_filtrado.dropna(subset=["division"])

        # Agrupar para el gráfico de pastel
        #df_agrupado = df_divisiones_filtrado.groupby("division")["monto"].sum().reset_index()

        #------------------------- GRÁFICO DE PASTEL ---------------------------------------------------------
        df_agrupado = df_divisiones_filtrado.groupby("division")["monto"].sum().reset_index()

        fig_pie = px.pie(
            df_agrupado,
            values="monto",
            names="division",
            color="division",
            color_discrete_map=colores_divisiones,
            hole=0.4
        )

        fig_pie.update_traces(
            textinfo="percent+label",
            textposition="inside",
            hovertemplate=(
                "<b>División:</b> %{label}<br>"
                "<b>Monto:</b> $%{value:,.2f}<br>"
                "<b>Porcentaje:</b> %{percent}<extra></extra>"
            )
        )

        fig_pie.update_layout(
            height=500,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.2,
                xanchor="center",
                x=0.5
            )
        )

        # 👇 Título con Markdown y menos espacio debajo
        st.markdown("### Distribución del total anual comprado por División")
        st.markdown("<div style='margin-top:-10px'></div>", unsafe_allow_html=True)

        st.plotly_chart(fig_pie, use_container_width=True)

        # ------------------------- TARJETAS: TOTAL COMPRADO POR DIVISIÓN ------------------------------
        st.markdown("<br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        divs = df_agrupado.set_index("division")

        with col1:
            monto = divs.loc["Agrícola", "monto"]
            st.metric("Agrícola", f"${monto:,.2f}")

        with col2:
            monto = divs.loc["Construcción", "monto"]
            st.metric("Construcción", f"${monto:,.2f}")

        with col3:
            monto = divs.loc["Jardinería y Golf", "monto"]
            st.metric("Jardinería y Golf", f"${monto:,.2f}")
        st.markdown("<br><br>", unsafe_allow_html=True)

        # --------------- GRÁFICO DE BARRAS DEL TOTAL ANUAL COMPRADO POR DIVISIÓN ----------------------------------------------
        df_agrupado["porcentaje"] = df_agrupado["monto"] / df_agrupado["monto"].sum() * 100
        df_agrupado["texto_barra"] = df_agrupado.apply(
            lambda row: f"${row['monto']:,.0f}<br>{row['porcentaje']:.1f}%", axis=1
        )

        fig_bar = px.bar(
            df_agrupado,
            x="division",
            y="monto",
            color="division",
            text="texto_barra",
            custom_data=["division", "porcentaje"],  # ← para usar en hovertemplate
            color_discrete_map=colores_divisiones,
            labels={"monto": "Monto Comprado", "division": "División"}
        )

        fig_bar.update_traces(
            textposition="inside",
            texttemplate="%{text}",
            hovertemplate=(
                "<b>División:</b> %{customdata[0]}<br>"
                "<b>Monto:</b> $%{y:,.2f}<br>"
                "<b>Porcentaje:</b> %{customdata[1]:.1f}%<extra></extra>"
            )
        )

        fig_bar.update_layout(
            showlegend=False
        )

        # 👇 Título con Markdown y menos espacio debajo
        st.markdown("### Monto total anual por División")
        st.markdown("<div style='margin-top:-10px'></div>", unsafe_allow_html=True)

        st.plotly_chart(fig_bar, use_container_width=True)

        # ---------------- TABLA: TOTAL MENSUAL COMPRADO POR DIVISIÓN ---------------------------------------------------------------------------
        # Crear tabla pivote
        tabla_pivot = df_divisiones_filtrado.pivot_table(
            index="division",
            columns="mes_nombre",
            values="monto",
            aggfunc="sum",
            fill_value=0
        )

        # Reordenar columnas según el orden cronológico (solo las que existan)
        meses_validos = [m for m in orden_meses if m in tabla_pivot.columns]
        tabla_pivot = tabla_pivot[meses_validos]

        tabla_pivot.index.name = "División"
        tabla_pivot = tabla_pivot.reset_index()

        # Convertir a HTML con estilo
        def construir_tabla_divisiones_html(df):
            estilos_css = """
            <style>
                .tabla-wrapper {
                    overflow-x: auto;
                    width: 100%;
                }

                .tabla-divisiones {
                    min-width: 100%;
                    width: max-content;
                    border-collapse: collapse;
                    table-layout: auto;
                }

                .tabla-divisiones thead th {
                    background-color: #0B083D;
                    color: white;
                    padding: 8px;
                    white-space: nowrap;
                    position: sticky;
                    top: 0;
                    z-index: 3;
                    border: 1px solid white;
                }

                .tabla-divisiones thead th:first-child {
                    text-align: right;
                }

                .tabla-divisiones thead th:not(:first-child) {
                    text-align: left;
                }

                /* Fijar el encabezado de la columna División */
                .tabla-divisiones thead th:first-child {
                    left: 0;
                    position: sticky;
                    z-index: 5;
                }

                .tabla-divisiones td, .tabla-divisiones th {
                    padding: 8px;
                    font-size: 14px;
                    white-space: nowrap;
                    border: 1px solid white;
                }

                /* Fijar toda la columna División (incluyendo celdas del tbody y tfoot) */
                .tabla-divisiones tbody td:first-child,
                .tabla-divisiones tfoot td:first-child {
                    position: sticky;
                    left: 0;
                    background-color: #eeeeee;
                    color: black;
                    font-weight: bold;
                    text-align: right;
                    z-index: 4;
                }

                /* También fijar la celda total primera columna (la última fila) */
                .tabla-divisiones tbody tr:last-child td:first-child {
                    background-color: #0B083D;
                    color: white;
                    z-index: 6;
                }

                /* Texto columnas excepto División alineado a la izquierda */
                .tabla-divisiones tbody td:not(:first-child) {
                    text-align: left;
                }

                .agricola {
                    background-color: #367C2B !important;
                    color: white;
                }

                .construccion {
                    background-color: #FFDE00 !important;
                    color: black;
                }

                .jardineria {
                    background-color: #FFA500 !important;
                    color: black;
                }

                .grad {
                    color: black;
                    font-weight: bold;
                    text-align: left;
                }

                /* Estilo celdas totales */
                .celda-total {
                    background-color: #0B083D !important;
                    color: white !important;
                    font-weight: bold;
                    text-align: left;
                }
            </style>
            """

            # Calcular totales por fila (división)
            df['Total'] = df[meses_validos].sum(axis=1)

            # Calcular totales por columna (meses + total)
            totales_columna = df[meses_validos + ['Total']].sum()

            # Añadimos columna Total a orden_meses para pintar totales por columna
            columnas_completas = meses_validos + ['Total']

            html = estilos_css + "<div class='tabla-wrapper'><table class='tabla-divisiones'>"
            html += "<thead><tr>"
            for col in df.columns:
                html += f"<th>{col}</th>"
            html += "</tr></thead><tbody>"

            for _, row in df.iterrows():
                html += "<tr>"

                # Estilo para División
                division = row["División"]
                clase_div = ""
                if "Agrícola" in division:
                    clase_div = "agricola"
                elif "Construcción" in division:
                    clase_div = "construccion"
                elif "Jardinería" in division or "Golf" in division:
                    clase_div = "jardineria"
                html += f"<td class='{clase_div}'>{division}</td>"

                # Valores por fila (incluyendo total)
                valores_fila = [row[col] for col in meses_validos]
                max_val = max(valores_fila)
                min_val = min(valores_fila)
                rango = max_val - min_val if max_val != min_val else 1

                # Mostrar celdas de meses con degradado azul por fila
                for col in meses_validos:
                    val = row[col]
                    ratio = (val - min_val) / rango
                    azul = int(255 - (ratio * 120))
                    color_fondo = f"rgb({azul},{azul + 20},255)"
                    html += f"<td class='grad' style='background-color:{color_fondo}'>{val:,.2f}</td>"

                # Mostrar total por fila (sin degradado, con color fijo)
                total_fila = row['Total']
                html += f"<td class='celda-total'>{total_fila:,.2f}</td>"

                html += "</tr>"

            # Fila totales por columna
            html += "<tr>"
            html += "<td class='celda-total'>Total</td>"
            max_total = totales_columna.max()
            min_total = totales_columna.min()
            rango_total = max_total - min_total if max_total != min_total else 1

            for col in columnas_completas:
                val = totales_columna[col]
                ratio = (val - min_total) / rango_total
                azul = int(255 - (ratio * 120))
                color_fondo = f"rgb({azul},{azul + 20},255)"
                html += f"<td class='celda-total' style='background-color:{color_fondo}'>{val:,.2f}</td>"
            html += "</tr>"

            html += "</tbody></table></div>"
            return html

        # Mostrar tabla
        st.markdown("### Comparativo por división")
        st.markdown(construir_tabla_divisiones_html(tabla_pivot), unsafe_allow_html=True)
        st.markdown("<br><br>", unsafe_allow_html=True)

        # ------------ GRÁFICA DE BARRAS AGRUPADAS: EVOLUCIÓN MENSUAL COMPRADO POR DIVISIÓN ------------------------------------------------------------
        df_mes_div = df_divisiones_filtrado.groupby(["mes_nombre", "division"])["monto"].sum().reset_index()
        df_mes_div["mes_nombre"] = pd.Categorical(df_mes_div["mes_nombre"], categories=orden_meses, ordered=True)
        df_mes_div = df_mes_div.sort_values("mes_nombre")

        fig_mes_div = px.bar(
            df_mes_div,
            x="mes_nombre",
            y="monto",
            color="division",
            text="monto",
            custom_data=["division"],         
            color_discrete_map=colores_divisiones,
            labels={"mes_nombre":"Mes","monto":"Total Comprado","division":"División"}
        )

        fig_mes_div.update_traces(
            texttemplate="$%{y:,.0f}",
            textposition="inside",
            hovertemplate=(
                "<b>Mes:</b> %{x}<br>"
                "<b>División:</b> %{customdata[0]}<br>"
                "<b>Total Comprado:</b> $%{y:,.2f}<extra></extra>"
            )
        )

        fig_mes_div.update_layout(
            barmode="stack",  # usa 'group' si quieres barras agrupadas en lugar de apiladas
            xaxis=dict(tickangle=-45),
            margin=dict(t=60, b=100),
            legend=dict(orientation="h", yanchor="bottom", y=-0.6, xanchor="center", x=0.5)
        )

        st.markdown("### Evolución mensual de compras por División")
        st.markdown("<div style='margin-top:-10px'></div>", unsafe_allow_html=True)

        st.plotly_chart(
            fig_mes_div, 
            use_container_width=True,
            config={
                "modeBarButtonsToRemove": [
                    "pan2d",
                    "select2d",
                    "lasso2d",
                    "zoomIn2d",
                    "zoomOut2d",
                    "resetScale2d",
                    "hoverClosestCartesian",
                    "hoverCompareCartesian"
                ],
                "displaylogo": False
            }
        )

        #----------------- GRÁFICA DE BARRAS AGRUPADAS: COMPRA POR SUCURSAL Y DIVISIÓN ------------------------------------------------------------
        df_suc_div = df_divisiones_filtrado.groupby(["sucursal", "division"])["monto"].sum().reset_index()

        fig_suc_div = px.bar(
            df_suc_div,
            x="sucursal",
            y="monto",
            color="division",
            text="monto",
            custom_data=["division"],  # ← aquí mandamos la división como dato adicional
            color_discrete_map=colores_divisiones,
            labels={"sucursal": "Sucursal", "monto": "Total Comprado", "division": "División"}
        )

        fig_suc_div.update_traces(
            texttemplate="$%{y:,.0f}",
            textposition="inside",
            hovertemplate=(
                "<b>Sucursal:</b> %{x}<br>"
                "<b>División:</b> %{customdata[0]}<br>"
                "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
            )
        )

        fig_suc_div.update_layout(
            barmode="stack",  # usa 'group' si prefieres barras agrupadas
            xaxis_tickangle=-45,
            margin=dict(t=60, b=100),
            legend=dict(orientation="h", yanchor="bottom", y=-0.6, xanchor="center", x=0.5)
        )

        st.markdown("### Compra anual por Sucursal y División")
        st.markdown("<div style='margin-top:-10px'></div>", unsafe_allow_html=True)

        st.plotly_chart(fig_suc_div, use_container_width=True)


        #----------------------- Tabla de compra por division y sucursal ----------------------------------
        tabla_sucursal_division = pd.pivot_table(
            df_divisiones_filtrado,   # ✅ aquí aplicamos el filtrado
            values="monto",
            index="division",
            columns="sucursal",
            aggfunc="sum",
            margins=True,
            margins_name="Total",
        )

        # Renombrar índice
        tabla_sucursal_division.index.rename("División", inplace=True)

        # Llenar NaN con 0
        tabla_sucursal_division = tabla_sucursal_division.fillna(0)

        # Convertimos el índice en columna para trabajar con HTML
        tabla_sucursal_division = tabla_sucursal_division.reset_index()

        # Reordenamos para poner "Total" al final si no lo está
        tabla_sucursal_division = tabla_sucursal_division.sort_values(by="División", key=lambda x: x == "Total", ascending=True)

        # Extraer lista de sucursales (columnas)
        sucursales = [col for col in tabla_sucursal_division.columns if col != "División"]

        # Diccionario de colores
        colores_div = {
            "Agrícola": "#367C2B",
            "Construcción": "#FFDE00",
            "Jardinería y Golf": "#FFA500"
        }

        # Función para construir la tabla con estilo
        def construir_tabla_sucursal_division_html(df, columnas_sucursales):
            estilos_css = """
            <style>
                .tabla-wrapper {
                    overflow-x: auto;
                    width: 100%;
                }

                .tabla-divisiones {
                    min-width: 100%;
                    width: max-content;
                    border-collapse: collapse;
                    table-layout: auto;
                }

                .tabla-divisiones thead th {
                    background-color: #0B083D;
                    color: white;
                    padding: 8px;
                    white-space: nowrap;
                    position: sticky;
                    top: 0;
                    z-index: 3;
                    border: 1px solid white;
                }

                .tabla-divisiones thead th:first-child {
                    text-align: right;
                    left: 0;
                    position: sticky;
                    z-index: 5;
                }

                .tabla-divisiones thead th:not(:first-child) {
                    text-align: left;
                }

                .tabla-divisiones td, .tabla-divisiones th {
                    padding: 8px;
                    font-size: 14px;
                    white-space: nowrap;
                    border: 1px solid white;
                }

                .tabla-divisiones tbody td:first-child {
                    position: sticky;
                    left: 0;
                    font-weight: bold;
                    text-align: right;
                    background-color: #eeeeee;
                    z-index: 4;
                }

                .tabla-divisiones tbody tr:last-child td:first-child {
                    background-color: #0B083D;
                    color: white;
                    z-index: 6;
                }

                .tabla-divisiones tbody td:not(:first-child) {
                    text-align: left;
                }

                .celda-total {
                    background-color: #0B083D !important;
                    color: white !important;
                    font-weight: bold;
                    text-align: left;
                }

                .grad {
                    font-weight: bold;
                    text-align: left;
                    color: black;
                }
            </style>
            """

            html = estilos_css + "<div class='tabla-wrapper'><table class='tabla-divisiones'>"
            html += "<thead><tr><th>División</th>"
            for col in columnas_sucursales:
                html += f"<th>{col}</th>"
            html += "</tr></thead><tbody>"

            for i, row in df.iterrows():
                division = row["División"]
                es_total_fila = division == "Total"
                color_fondo_div = "#0B083D" if es_total_fila else colores_div.get(division, "#eeeeee")
                color_texto = "white" if es_total_fila else ("black" if color_fondo_div != "#FFDE00" else "black")

                html += f"<tr><td style='background-color:{color_fondo_div}; color:{color_texto}'>{division}</td>"
                columnas_sucursales = [col for col in df.columns if col not in ("División", "Total")]

                if not es_total_fila:
                    valores = [row[col] for col in columnas_sucursales]
                    max_val = max(valores)
                    min_val = min(valores)
                    rango = max_val - min_val if max_val != min_val else 1

                for col in columnas_sucursales + ["Total"]:
                    val = row[col]
                    if es_total_fila or col == "Total":
                        clase = "celda-total"
                        html += f"<td class='{clase}'>{val:,.0f}</td>"
                    else:
                        ratio = (val - min_val) / rango
                        azul = int(255 - (ratio * 120))
                        color_fondo = f"rgb({azul},{azul + 20},255)"
                        html += f"<td class='grad' style='background-color:{color_fondo}'>{val:,.0f}</td>"

                html += "</tr>"

            html += "</tbody></table></div>"
            return html
        
        st.subheader("Monto anual comprado por sucursal y división")
        st.markdown(
            construir_tabla_sucursal_division_html(tabla_sucursal_division, sucursales),
            unsafe_allow_html=True
        )
        st.markdown("<br><br>", unsafe_allow_html=True)


        #----------- Graficos de columnas de compra mensual por división y sucursal -------------

        # Cargar colores de divisiones
        with open("config_colores.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        colores_divisiones = {k: v["color"] for k, v in config["divisiones"].items()}

        # Agrupar datos
        df_smd = df_filtrado.groupby(["sucursal", "mes_nombre", "division"], as_index=False)["monto"].sum()
        df_smd["sucursal"] = df_smd["sucursal"].astype(str)
        df_smd["mes_nombre"] = df_smd["mes_nombre"].astype(str)
        df_smd["division"] = df_smd["division"].astype(str)

        sucursales = df_smd["sucursal"].unique()
        num_sucursales = len(sucursales)

        # Lista en español
        orden_meses_con_anio = [
            "Enero 2025", "Febrero 2025", "Marzo 2025", "Abril 2025", "Mayo 2025", "Junio 2025",
            "Julio 2025", "Agosto 2025", "Septiembre 2025", "Octubre 2025", "Noviembre 2025", "Diciembre 2025"
        ]

        # Mapeo español → inglés para conversión
        meses_es_en = {
            'Enero': 'January', 'Febrero': 'February', 'Marzo': 'March', 'Abril': 'April',
            'Mayo': 'May', 'Junio': 'June', 'Julio': 'July', 'Agosto': 'August',
            'Septiembre': 'September', 'Octubre': 'October', 'Noviembre': 'November', 'Diciembre': 'December'
        }

        # Columna temporal para conversión
        df_smd["mes_nombre_en"] = df_smd["mes_nombre"].str.extract(r"(\w+)\s+(\d{4})").apply(
            lambda row: f"{meses_es_en.get(row[0], row[0])} {row[1]}", axis=1
        )

        # Convertir a datetime
        df_smd["fecha_mes"] = pd.to_datetime(df_smd["mes_nombre_en"], format="%B %Y")

        # Filtrar hasta el mes más reciente
        max_fecha = df_smd["fecha_mes"].max()
        orden_meses_fecha = [
            pd.to_datetime(f"{meses_es_en[m.split()[0]]} {m.split()[1]}", format="%B %Y")
            for m in orden_meses_con_anio
        ]
        meses_hasta_max = [
            orden_meses_con_anio[i] for i, fecha in enumerate(orden_meses_fecha) if fecha <= max_fecha
        ]

        # Categorizar para orden
        df_smd["mes_nombre"] = pd.Categorical(df_smd["mes_nombre"], categories=meses_hasta_max, ordered=True)
        df_smd = df_smd.sort_values(["sucursal", "mes_nombre"])
        df_smd.drop(columns=["mes_nombre_en"], inplace=True)

        st.title("Evolución de compras por sucursal")

        # Columnas por fila
        num_columnas = st.radio("Número de columnas de gráficos por fila:", options=[1, 2], index=1)

        # Orden de divisiones y paleta
        divisiones_ordenadas = sorted(df_smd["division"].unique())
        palette = [colores_divisiones.get(div, "#777777") for div in divisiones_ordenadas]

        for i in range(0, num_sucursales, num_columnas):
            cols = st.columns(num_columnas)
            for j in range(num_columnas):
                if i + j < num_sucursales:
                    suc = sucursales[i + j]
                    df_sucursal = df_smd[df_smd["sucursal"] == suc]

                    fig, ax = plt.subplots(figsize=(8, 4))
                    fig.patch.set_facecolor('#121212')
                    ax.set_facecolor('#121212')

                    # Divisiones presentes en este subset y paleta ajustada
                    divisiones_presentes = df_filtrado["division"].unique()
                    palette_grafico = {div: colores_divisiones.get(div, "#777777") for div in divisiones_presentes}

                    sns.barplot(
                        data=df_sucursal,
                        x="monto",
                        y="mes_nombre",
                        hue="division",
                        hue_order=divisiones_presentes,  # solo divisiones presentes
                        palette=palette_grafico,
                        ax=ax,
                        orient="h"
                    )

                    # Etiquetas de las barras, al borde para no sobreponerse
                    for container in ax.containers:
                        ax.bar_label(
                            container,
                            labels=[f"${x:,.0f}" for x in container.datavalues],
                            padding=3,
                            color='white',
                            fontsize=9,
                            label_type='edge'
                        )

                    # Formato eje X
                    ax.xaxis.set_major_formatter(mtick.StrMethodFormatter('${x:,.0f}'))
                    ax.set_title(f"{suc} - Evolución de Compras", color="white")
                    ax.set_xlabel("Monto", color="white")
                    ax.set_ylabel("Mes", color="white")
                    ax.tick_params(colors="white")

                    # Leyenda solo con divisiones presentes
                    leg = ax.get_legend()
                    if leg is not None:
                        leg.set_title("División")
                        leg.get_title().set_color("white")  # título en blanco
                        for text in leg.get_texts():
                            text.set_color("white")           # labels en blanco
                        leg.get_frame().set_facecolor('#121212')
                        leg.get_frame().set_edgecolor('white')
                        # mover la leyenda
                        leg.set_bbox_to_anchor((1.15, 1))   # desplazamiento horizontal
                        leg._legend_box.align = "left"

                    # Ajustar márgenes para que la leyenda no se encime con el gráfico
                    fig.subplots_adjust(right=0.80)

                    cols[j].pyplot(fig)

    # ==========================================================================================================
    # ===================== COMPRA POR CUENTA ======================================
    # ==========================================================================================================
    #---------------------- GRÁFICO DE BARRAS: COMPRA ANUAL POR CUENTA -------------------------------------------------------
    elif opcion == "Compra por Cuenta":
        st.title("Compra Total Anual por Cuenta (2025)")
        
        # Agrupar monto total por cuenta y sucursal
        df_cta = df_divisiones.groupby(["codigo_normalizado", "sucursal", "division"], as_index=False)["monto"].sum()

        # Crear etiqueta tipo "1234 - Monterrey"
        df_cta["cuenta_sucursal"] = df_cta["codigo_normalizado"] + " - " + df_cta["sucursal"]

        # Ordenar de mayor a menor monto
        df_cta = df_cta.sort_values("monto", ascending=False)

        # Aplicar color por división
        df_cta["color_div"] = df_cta["division"].map(colores_divisiones).fillna("#777777")

        fig = px.bar(
            df_cta,
            x="monto",
            y="cuenta_sucursal",
            color="division",
            color_discrete_map=colores_divisiones,
            orientation="h",
            labels={"monto": "Monto", "cuenta_sucursal": "Cuenta - Sucursal", "division": "División"},
            #title="Monto Total por Cuenta en 2025"
        )

        # Custom data para el hover
        fig.update_traces(
            customdata=df_cta[["cuenta_sucursal", "division", "monto"]],
            hovertemplate=(
                "<b>Cuenta - Sucursal:</b> %{customdata[0]}<br>"
                "<b>División:</b> %{customdata[1]}<br>"
                "<b>Monto:</b> $%{customdata[2]:,.2f}<extra></extra>"
            ),
            text=df_cta["monto"].apply(lambda x: f"${x:,.2f}"),
            textposition="outside",
            cliponaxis=False
        )

        fig.update_layout(
            xaxis_title="Monto (MXN)",
            yaxis_title="Cuenta - Sucursal",
            margin=dict(r=70),
            template="plotly_dark",
            yaxis={'categoryorder': 'total ascending'},
            height=800,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.15,
                xanchor="center",
                x=0.5
            )
        )
        st.markdown("### Monto Total por Cuenta en 2025")
        st.markdown("<div style='margin-top:-30px'></div>", unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("<br><br>", unsafe_allow_html=True)

        #------------------------------ TABLA: COMPRA MENSUAL POR CUENTA: 2025 ---------------------------------------------------
        st.title("Compra mensual por Cuenta (2025)")
        st.markdown("<div style='margin-top:-5px'></div>", unsafe_allow_html=True)

        def obtener_abreviatura(codigo):
            for division, info in divisiones.items():
                if codigo in info["codigos"]:
                    return info["abreviatura"]
            return ""

        df["abreviatura"] = df["codigo_normalizado"].apply(obtener_abreviatura)
        df["cuenta_sucursal"] = df["codigo_normalizado"] + " (" + df["abreviatura"] + ") - " + df["sucursal"]

        # Usar meses en español con tu diccionario meses_es para formatear mes_año
        df["mes_anio"] = df["mes_dt"].dt.month_name().map(meses_es) + " " + df["mes_dt"].dt.year.astype(str)
        df["orden_mes"] = df["mes_dt"].dt.to_period("M")

        tabla_compras = df.pivot_table(
            index="cuenta_sucursal",
            columns="mes_anio",
            values="monto",
            aggfunc="sum",
            fill_value=0
        )

        orden_columnas = df.drop_duplicates("mes_anio").sort_values("orden_mes")["mes_anio"].tolist()
        tabla_compras = tabla_compras[orden_columnas]

        tabla_compras["Total Cuenta"] = tabla_compras.sum(axis=1)
        tabla_compras.loc["Total General"] = tabla_compras.sum(axis=0)

        tabla_compras = tabla_compras.rename_axis("Cuenta - Sucursal")
        tabla_compras_reset = tabla_compras.reset_index()

        def formato_numero(x):
            if isinstance(x, (int, float)):
                return f"{x:,.2f}"
            return x

        tabla_formateada = tabla_compras_reset.copy()
        for col in tabla_formateada.columns[1:]:
            tabla_formateada[col] = tabla_formateada[col].apply(formato_numero)

        estilo_css = """
        <style>
        .tabla-scroll {
            max-height: 500px;
            overflow: auto;
            margin: 0; 
            padding: 0;
            border: 0;
        }

        /* Margen inferior para separar del botón */
        .spacer {
            height: 16px;
        }

        /* Tabla */
        table {
            border-collapse: collapse;
            width: 100%;
            min-width: 900px;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px 12px;
            white-space: nowrap;
        }
        /* Encabezado */
        th {
            background-color: #0B083D;
            color: white;
            position: sticky;
            top: 0;
            z-index: 2;
            text-align: left;
        }
        /* Primera columna (cuenta) */
        th:first-child {
            background-color: #0B083D;
            color: white;
            text-align: right;
            font-weight: bold;
            position: sticky;
            left: 0;
            top: 0;
            z-index: 5; /* más alto que el header normal */
        }

        td:first-child {
            background-color: #0B083D;
            color: white;
            text-align: right;
            font-weight: bold;
            position: sticky;
            left: 0;
            z-index: 4;
        }
        /* Totales: última fila */
        tr:last-child td {
            background-color: #0B083D;
            color: white;
            font-weight: bold;
        }
        /* Totales: última columna */
        td:last-child {
            background-color: #0B083D;
            color: white;
            font-weight: bold;
        }
        /* Celdas normales (no totales, no primera columna) */
        tbody tr:not(:last-child) td:not(:first-child):not(:last-child) {
            background-color: white;
            color: black;
        }
        </style>
        """

        def generar_html_tabla(df):
            html = "<div class='tabla-scroll'><table>"
            # Encabezado
            html += "<thead><tr>"
            for col in df.columns:
                html += f"<th>{col}</th>"
            html += "</tr></thead>"
            # Cuerpo
            html += "<tbody>"
            for i, row in df.iterrows():
                html += "<tr>"
                for j, val in enumerate(row):
                    html += f"<td>{val}</td>"
                html += "</tr>"
            html += "</tbody></table></div>"
            return html

        html_tabla = estilo_css + generar_html_tabla(tabla_formateada)

        st.markdown(html_tabla, unsafe_allow_html=True)

        # Aquí agregamos un div vacío con altura para separar visualmente
        st.markdown("<div class='spacer'></div>", unsafe_allow_html=True)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            tabla_compras.to_excel(writer, sheet_name='Compras')
        processed_data = output.getvalue()

        st.download_button(
            label="📥 Descargar tabla en Excel",
            data=processed_data,
            file_name="compras_por_mes_por_cuenta.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.markdown("<br><br>", unsafe_allow_html=True)

        #-------------------- GRÁFICO DE LÍNEAS: COMPRAS MENSUALES POR CUENTA --------------------------------------------------------------------------
        # Asegúrate de que la columna mes_dt existe
        if "mes_dt" not in df_divisiones.columns:
            df_divisiones["mes_dt"] = pd.to_datetime(df_divisiones["fecha"]).dt.to_period("M").dt.to_timestamp()

        # Crear columna mes_nombre y mes_anio en español
        df_divisiones["mes_nombre"] = df_divisiones["mes_dt"].dt.month_name().map(meses_es)
        df_divisiones["mes_anio"] = df_divisiones["mes_nombre"] + " " + df_divisiones["mes_dt"].dt.year.astype(str)

        # Función para obtener abreviatura de la división
        def obtener_abreviatura(codigo):
            codigo_str = str(codigo).strip()
            for division, info in divisiones.items():
                if codigo_str in info["codigos"]:
                    return info["abreviatura"]
            return ""

        # Crear columna abreviatura y cuenta_sucursal
        df_divisiones["abreviatura"] = df_divisiones["codigo_normalizado"].apply(obtener_abreviatura)
        df_divisiones["cuenta_sucursal"] = (
            df_divisiones["codigo_normalizado"].astype(str) + " (" +
            df_divisiones["abreviatura"] + ") - " +
            df_divisiones["sucursal"]
        )

        # Preparar datos para plotly (long-form)
        df_grafico = df_divisiones.groupby(["mes_anio", "cuenta_sucursal", "abreviatura"], as_index=False)["monto"].sum()

        # Definir el orden de los meses
        orden_meses = df_divisiones.drop_duplicates("mes_anio").sort_values("mes_dt")["mes_anio"].tolist()

        # Obtener lista de cuentas únicas
        cuentas = df_grafico["cuenta_sucursal"].unique()

        # Crear todas las combinaciones posibles mes-cuenta
        import itertools
        combinaciones = pd.DataFrame(list(itertools.product(orden_meses, cuentas)), columns=["mes_anio", "cuenta_sucursal"])

        # Merge para tener todas las combinaciones y completar montos faltantes con cero
        df_grafico = combinaciones.merge(df_grafico, on=["mes_anio", "cuenta_sucursal"], how="left")
        df_grafico["monto"] = df_grafico["monto"].fillna(0)

        # Convertir mes_anio en categoría ordenada
        df_grafico["mes_anio"] = pd.Categorical(df_grafico["mes_anio"], categories=orden_meses, ordered=True)
        df_grafico = df_grafico.sort_values("mes_anio")

        # Selector de cuentas
        cuentas_disponibles = sorted(df_grafico["cuenta_sucursal"].unique())
        cuentas_seleccionadas = st.multiselect("Selecciona cuentas a mostrar:", cuentas_disponibles, default=cuentas_disponibles)

        # Filtrar el DataFrame según selección
        df_filtrado = df_grafico[df_grafico["cuenta_sucursal"].isin(cuentas_seleccionadas)]

        # Mostrar advertencia si no hay datos
        if df_filtrado.empty:
            st.warning("No hay datos para mostrar con las cuentas seleccionadas.")
            st.dataframe(df_grafico.head(10))
        else:
            # Crear gráfico de líneas con customdata incluyendo abreviatura
            fig = px.line(
                df_filtrado,
                x="mes_anio",
                y="monto",
                color="cuenta_sucursal",
                markers=True,
                custom_data=["mes_anio", "cuenta_sucursal", "monto", "abreviatura"]
            )

            # Formato de hovertemplate mostrando abreviatura
            fig.update_traces(
                hovertemplate=(
                    "<b>Mes:</b> %{customdata[0]}<br>"
                    "<b>Cuenta - Sucursal:</b> %{customdata[1]}<br>"
                    "<b>Monto:</b> $%{customdata[2]:,.2f}<br>"
                    "<b>División:</b> %{customdata[3]}<extra></extra>"
                )
            )

            fig.update_layout(
                xaxis_title="Mes",
                yaxis_title="Monto (MXN)",
                yaxis_tickformat=",",
                legend_title="Cuenta - Sucursal"
            )

            config = {
                "scrollZoom": True,
                "modeBarButtonsToKeep": [
                    "toImage", "zoom2d", "autoScale2d", "toggleFullscreen"
                ],
                "displaylogo": False
            }

            st.markdown("<br><br>", unsafe_allow_html=True)
            st.markdown("### Compras mensuales por cuenta")
            st.markdown("<div style='margin-top:-30px'></div>", unsafe_allow_html=True)
            st.plotly_chart(fig, use_container_width=True, config=config)


        #---------------- GRAFICAS DE BARRAS: COMPRA POR CUENTA POR MES POR SUCURSAL ------------------------------------------------------------------------------
        st.header("Evolución mensual de compras por cuenta")
        if df_divisiones.empty:
            st.warning("No hay datos disponibles.")
        else:
            # Crear columna abreviatura y cuenta_sucursal igual que en tabla
            def obtener_abreviatura(codigo):
                codigo_str = str(codigo).strip()
                for division, info in divisiones.items():
                    if codigo_str in info["codigos"]:
                        return info["abreviatura"]
                return ""

            df_divisiones["abreviatura"] = df_divisiones["codigo_normalizado"].apply(obtener_abreviatura)
            df_divisiones["cuenta_sucursal"] = (
                df_divisiones["codigo_normalizado"].astype(str) + " (" +
                df_divisiones["abreviatura"] + ") - " +
                df_divisiones["sucursal"]
            )


            df_divisiones["sucursal_nombre"] = df_divisiones["cuenta_sucursal"].str.split(" - ").str[-1]

            # Crear columna mes_nombre en español
            df_divisiones["mes_nombre"] = df_divisiones["mes_dt"].dt.month_name().map(meses_es) + " " + df_divisiones["mes_dt"].dt.year.astype(str)

            # Agrupar
            df_barras = df_divisiones.groupby(["mes_nombre", "cuenta_sucursal"], as_index=False)["monto"].sum()

            # Obtener cuentas y meses para completar combinaciones
            orden_meses = [m for m in orden_meses_desc if pd.notna(m)]
            todas_cuentas = df_divisiones["cuenta_sucursal"].unique()

            idx = pd.MultiIndex.from_product([orden_meses, todas_cuentas], names=["mes_nombre", "cuenta_sucursal"])

            df_barras = df_barras.set_index(["mes_nombre", "cuenta_sucursal"]).reindex(idx, fill_value=0).reset_index()

            df_sucursales = df_divisiones.drop_duplicates("cuenta_sucursal")[["cuenta_sucursal", "sucursal_nombre"]]
            df_barras = df_barras.merge(df_sucursales, on="cuenta_sucursal", how="left")

            df_barras["mes_nombre"] = pd.Categorical(df_barras["mes_nombre"], categories=orden_meses, ordered=True)

            for mes in orden_meses:
                df_mes = df_barras[df_barras["mes_nombre"] == mes].copy()

                if df_mes.empty:
                    continue

                df_mes = df_mes.sort_values("monto", ascending=False)
                df_mes["cuenta_sucursal"] = pd.Categorical(df_mes["cuenta_sucursal"], categories=df_mes["cuenta_sucursal"], ordered=True)
                df_mes["texto_monto"] = df_mes["monto"].apply(lambda x: f"${x:,.2f}")

                fig = go.Figure()

                for i, row in df_mes.iterrows():
                    fig.add_trace(go.Bar(
                        y=[row["cuenta_sucursal"]],
                        x=[row["monto"]],
                        orientation='h',
                        name=row["sucursal_nombre"],
                        marker_color=colores_sucursales.get(row["sucursal_nombre"], "#CCCCCC"),
                        text=row["texto_monto"],
                        textposition="outside",
                        cliponaxis=False,
                        hovertemplate=f"{row['cuenta_sucursal']}<br>Monto: $%{{x:,.2f}}<extra></extra>"
                    ))

                altura_por_barra = 40
                numero_barras = len(df_mes)
                altura_total = max(600, numero_barras * altura_por_barra)

                fig.update_layout(
                    title=f"Compras por Cuenta - {mes}",
                    xaxis_title="Monto de compra (MXN)",
                    yaxis_title="Cuenta",
                    xaxis_tickformat=",",
                    legend_title="Sucursal",
                    barmode="stack",
                    margin=dict(r=70),
                    showlegend=False,
                    height=altura_total,
                    bargap=0.15,
                    bargroupgap=0.1
                )

                st.plotly_chart(fig, use_container_width=True)

    # ==========================================================================================================
    # =========================== COMPRA POR SUCURSAL ======================================
    #==========================================================================================================
    elif opcion == "Compra por Sucursal":
        st.title("Total de Compras por Mes y Sucursal - 2025")

        #------------------------------------ GRÁFICA DE BARRAS AGRUPADA ---------------------------------------------------------------------------------------
        df_pivot = df.pivot_table(index="mes_nombre", columns="sucursal", values="monto", aggfunc="sum").fillna(0)
        df_pivot = df_pivot.reindex(orden_meses)
        df_percent = df_pivot.div(df_pivot.sum(axis=1), axis=0) * 100

        fig = go.Figure()
        for sucursal in sorted(df_pivot.columns):
            fig.add_trace(go.Bar(
                y=df_percent.index,
                x=df_percent[sucursal],
                orientation='h',
                name=sucursal,
                marker=dict(color=colores_sucursales.get(sucursal)),
                customdata=df_pivot[sucursal],
                text=[
                    f"{df_percent.loc[mes, sucursal]:.1f}%<br>${df_pivot.loc[mes, sucursal]:,.0f}"
                    if df_pivot.loc[mes, sucursal] > 0 else ""
                    for mes in df_percent.index
                ],
                hovertemplate="<b>%{fullData.name}</b><br>%{x:.1f}%<br>$%{customdata:,.2f}<extra></extra>",
                textposition='inside'
            ))
        fig.update_layout(
            barmode='stack',
            #title='Distribución porcentual de compras por sucursal (2025)',
            xaxis=dict(title='Porcentaje', ticksuffix='%'),
            yaxis=dict(title='Mes'),
            legend=dict(orientation='h', yanchor='top', y=-0.25, xanchor='center', x=0.5),
            height=650, margin=dict(t=100)
        )
        # Configuración personalizada para scroll + barra de herramientas limpia
        config = {
            "scrollZoom": True,
            "modeBarButtonsToKeep": [
                "toImage",
                "zoom2d",
                "autoScale2d",
                "toggleFullscreen"
            ],
            "displaylogo": False
        }
        st.markdown("### Distribución porcentual de compras por sucursal (2025)")
        st.markdown("<div style='margin-top:px'></div>", unsafe_allow_html=True)
        # Mostrar gráfica con zoom y opciones de barra
        st.plotly_chart(fig, use_container_width=True, config=config)


        #------------------------------- TABLA: RESUMEN TOTAL POR MES Y SUCURSAL ------------------------------------
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("### Resumen total por mes y sucursal")

        # Crear tabla pivote con totales
        tabla = df.pivot_table(
            index="mes_nombre",
            columns="sucursal",
            values="monto",
            aggfunc="sum",
            margins=True,
            margins_name="Total"
        ).fillna(0)

        # Reordenar filas (meses + total)
        tabla = tabla.reindex(orden_meses + ["Total"])

        # Cambiar nombre índice
        tabla.index.name = "Mes"

        # Resetear índice para AgGrid (sin formatear números)
        tabla_reset = tabla.reset_index()

        tabla_reset = tabla.reset_index().fillna(0)

        for col in tabla_reset.columns:
            if col != "Mes":
                tabla_reset[col] = pd.to_numeric(tabla_reset[col], errors='coerce').fillna(0)

        total_row = tabla_reset[tabla_reset["Mes"] == "Total"]
        data_sin_total = tabla_reset[tabla_reset["Mes"] != "Total"]

        print(data_sin_total[["Tierra blanca", "Tuxtla Gtz"]])

        # Separar la fila Total para fijarla abajo
        total_row = tabla_reset[tabla_reset["Mes"] == "Total"]
        data_sin_total = tabla_reset[tabla_reset["Mes"] != "Total"].copy()
        data_sin_total = data_sin_total.fillna(0)
        for col in data_sin_total.columns:
            if col != "Mes":
                data_sin_total[col] = pd.to_numeric(data_sin_total[col], errors='coerce').fillna(0)
      
        print(data_sin_total.columns.tolist())

        # Asegurar que columnas numéricas sean floats
        ultima_col = tabla_reset.columns[-1]
        for col in data_sin_total.columns:
            if col not in ["Mes", ultima_col]:
                data_sin_total[col] = pd.to_numeric(data_sin_total[col], errors='coerce').fillna(0)

        # Calcular min y max por sucursal (excluyendo total vertical)
        min_max_dict = {}
        for col in data_sin_total.columns:
            if col not in ["Mes", ultima_col]:
                valores = data_sin_total[col]
                min_max_dict[col] = (valores.min(), valores.max())

        # JS arreglo meses para orden cronológico
        orden_meses_js_array = str(orden_meses).replace("'", '"')

        # Comparator JS para ordenar meses
        month_comparator = JsCode(f"""
        function(month1, month2) {{
            var orden = {orden_meses_js_array};
            var i1 = orden.indexOf(month1);
            var i2 = orden.indexOf(month2);
            return i1 - i2;
        }}
        """)

        # Formatter para mostrar números con comas y 2 decimales
        value_formatter = JsCode("""
        function(params) {
            if (params.value === undefined || params.value === null) return '0.00';
            return params.value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }
        """)

        # JS para pintar celdas con escala rojo → amarillo → verde pastel
        cell_style_gradient_template = """
        function(params) {
            const totalCol = '%s';
            if (params.colDef.field !== 'Mes' && params.colDef.field !== totalCol && params.data['Mes'] !== 'Total') {
                let val = params.value;
                let min = %f;
                let max = %f;
                if (!isNaN(val) && max > min) {
                    let ratio = (val - min) / (max - min);

                    // Colores definidos
                    let r, g, b;
                    if (ratio <= 0.5) {
                        // Verde (#75DE54) a Amarillo (#E8E546)
                        let t = ratio / 0.5;
                        r = Math.round(117 + t * (232 - 117));
                        g = Math.round(222 + t * (229 - 222));
                        b = Math.round(84  + t * (70  - 84));
                    } else {
                        // Amarillo (#E8E546) a Rojo (#E86046)
                        let t = (ratio - 0.5) / 0.5;
                        r = Math.round(232 + t * (232 - 232));
                        g = Math.round(229 + t * (96  - 229));
                        b = Math.round(70  + t * (70  - 70));
                    }

                    return {
                        backgroundColor: `rgb(${r},${g},${b})`,
                        textAlign: 'left'
                    };
                }
            }
            return { textAlign: 'left' };
        }
        """

        # Construir opciones de grid para AgGrid
        gb = GridOptionsBuilder.from_dataframe(data_sin_total)
        gb.configure_default_column(resizable=True, filter=False)

        # Columna Mes fija en azul y con comparator para orden cronológico
        gb.configure_column(
            "Mes",
            pinned="left",
            width=180,
            cellStyle={
                'textAlign': 'right',
                'backgroundColor': '#0B083D',
                'color': 'white',
                'fontWeight': 'bold'
            },
            comparator=month_comparator
        )

        # Configurar columnas numéricas con valueGetter simple y valueFormatter
        for col in data_sin_total.columns:
            if col not in ["Mes", ultima_col]:
                min_val, max_val = min_max_dict[col]
                gradient_code = JsCode(cell_style_gradient_template % (ultima_col, min_val, max_val))
                gb.configure_column(
                    col,
                    width=120,
                    cellStyle=gradient_code,
                    sortable=True,
                    valueGetter=JsCode(f"function(params) {{ return params.data['{col}']; }}"),
                    valueFormatter=value_formatter
                )

        gb.configure_column(
            col,
            width=120,
            cellStyle=gradient_code,
            sortable=True,
            valueGetter=JsCode(f"function(params) {{ return params.data['{col}']; }}"),
            valueFormatter=value_formatter
        )

        # Columna Total vertical fija azul y sin orden
        gb.configure_column(
            ultima_col,
            width=120,
            cellStyle={
                'textAlign': 'left',
                'backgroundColor': '#0B083D',
                'color': 'white',
                'fontWeight': 'bold'
            },
            sortable=False,
            valueFormatter=value_formatter  # <-- acá el formatter
        )

        # JS para pintar fila total fija abajo
        get_row_style = JsCode("""
        function(params) {
            if(params.node.rowPinned) {
                return {
                    backgroundColor: '#0B083D',
                    color: 'white',
                    fontWeight: 'bold'
                };
            }
            return null;
        }
        """)

        grid_options = gb.build()
        grid_options['pinnedBottomRowData'] = total_row.to_dict('records')
        grid_options['getRowStyle'] = get_row_style
        grid_options['domLayout'] = 'autoHeight'

        # CSS para header azul de la tabla
        custom_css = {
            ".ag-header-cell-label": {
                "background-color": "#0B083D !important",
                "color": "white !important",
                "font-weight": "bold !important",
                "justify-content": "center !important"
            },
            ".ag-header-cell-text": {
                "color": "white !important",
                "font-weight": "bold !important"
            }
        }

        # --- Layout de título + botón en dos columnas ---
        col1, col2 = st.columns([3, 1])  # proporción de ancho 3:1
        with col1:
            st.subheader("Tabla resumen del monto sin ligar por mes y sucursal")

        with col2:
            buffer = io.BytesIO()
            tabla_reset.to_excel(buffer, index=False)
            buffer.seek(0)

            st.download_button(
                label="📥 Descargar tabla en Excel",
                data=buffer,
                file_name="resumen_mensual.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # --- Mostrar tabla debajo ---
        AgGrid(
            data_sin_total,
            gridOptions=grid_options,
            height=400,  # altura de la tabla
            fit_columns_on_grid_load=False,
            allow_unsafe_jscode=True,
            custom_css=custom_css,
            enable_enterprise_modules=False,
            theme="ag-theme-alpine"
        )

        # ------------------------- GRÁFICO DE LÍNEAS: EVOLUCIÓN DE COMPRAS POR MES Y SUCURSAL -------------------------------------
        fig_lineas = go.Figure()

        for sucursal in df_pivot.columns:
            # Prepara los datos para pasar mes y sucursal por customdata
            customdata = list(zip(df_pivot.index.astype(str), [sucursal]*len(df_pivot)))

            fig_lineas.add_trace(go.Scatter(
                x=df_pivot.index,
                y=df_pivot[sucursal],
                mode='lines+markers',
                name=sucursal,
                line=dict(color=colores_sucursales.get(sucursal)),
                customdata=customdata,
                hovertemplate=(
                    "<b>Sucursal:</b> %{customdata[1]}<br>" +
                    "<b>Mes:</b> %{customdata[0]}<br>" +
                    "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
                )
            ))

        fig_lineas.update_layout(
            #title="Evolución de Compras por Mes y Sucursal (2025)",
            xaxis_title="Mes",
            yaxis_title="Total Comprado",
            xaxis=dict(tickangle=-45),
            height=500,
            margin=dict(t=60)
        )
        
        # --- Espacio responsivo ---
        st.markdown("<div style='margin-top:1.5em; margin-bottom:1em'></div>", unsafe_allow_html=True)
        #st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("### Evolución de Compras por Mes y Sucursal (2025)")
        st.markdown("<div style='margin-top:-30px'></div>", unsafe_allow_html=True)
        st.plotly_chart(
            fig_lineas,
            use_container_width=True,
            config={
                "scrollZoom": True,
                "modeBarButtonsToKeep": [
                    "toImage",
                    "zoom2d",
                    "autoScale2d",
                    "toggleFullscreen"
                ],
                "displaylogo": False
            }
        )

        #------------------------- GRÁFICAS DE BARRAS: COMPRAS POR SUCURSAL, MES A MES  -----------------------------------------------------
        # Obtener mes actual
        mes_actual = datetime.today().month

        # Lista ordenada de meses base (enero a diciembre) en español
        orden_meses_base = [
            "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
        ]

        # Generar orden desde el mes actual hacia atrás
        mes_inicio = (mes_actual - 1) % 12
        orden_meses_reversa = [orden_meses_base[(mes_inicio - i) % 12] for i in range(12)]

        # Agregar el año a cada mes en el orden correcto, tomando en cuenta los datos reales
        orden_meses_reversa_completa = []
        for mes_simple in orden_meses_reversa:
            meses_disponibles = [m for m in orden_meses_desc if m.startswith(mes_simple)]
            orden_meses_reversa_completa.extend(meses_disponibles)

        # Mostrar las gráficas
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("### Compras por Sucursal, mes a mes")

        for i, mes in enumerate(orden_meses_reversa_completa):
            df_mes = df[df["mes_nombre"] == mes].copy()
            
            # Agrupar solo por sucursal, sumando montos
            df_mes = df_mes.groupby("sucursal", as_index=False).agg({"monto": "sum"})
            
            if df_mes["monto"].sum() == 0:
                continue

            total_mes = df_mes["monto"].sum()
            df_mes["porcentaje"] = df_mes["monto"] / total_mes * 100
            df_mes["texto"] = df_mes.apply(
                lambda row: f"${row['monto']:,.2f}<br>({row['porcentaje']:.1f}%)", axis=1
            )
            df_mes["custom_data"] = list(zip(df_mes["sucursal"], df_mes["monto"], df_mes["porcentaje"]))

            fig_mes = px.bar(
                df_mes,
                x="sucursal",
                y="monto",
                title=f"Compras en {mes}",
                labels={"monto": "Total Comprado", "sucursal": "Sucursal"},
                color="sucursal",
                color_discrete_map=colores_sucursales,
                text="texto",
                custom_data=["sucursal", "monto", "porcentaje"]
            )

            fig_mes.update_traces(
                textposition='inside',
                texttemplate='%{text}',
                hovertemplate=(
                    "<b>Sucursal:</b> %{customdata[0]}<br>"
                    "<b>Monto:</b> $%{customdata[1]:,.2f}<br>"
                    "<b>Porcentaje:</b> %{customdata[2]:.1f}%<extra></extra>"
                )
            )

            fig_mes.update_layout(showlegend=False)
            st.plotly_chart(fig_mes, use_container_width=True, key=f"bar_{i}_{mes}")

    # ==========================================================================================================
    # ================================ VISTA POR SUCURSAL ====================================
    # ==========================================================================================================
    elif opcion == "Vista por Sucursal":
        st.title("Vista detallada por Sucursal")

        # Recalcular df_pivot
        df_pivot = df.pivot_table(index="mes_nombre", columns="sucursal", values="monto", aggfunc="sum").fillna(0)
        df_pivot = df_pivot.reindex(orden_meses)

        # ------------------------------- SELECTOR DE SUCURSALES ----------------------------------------------------------------------------------------------------
        sucursales_disponibles = sorted(df["sucursal"].unique())
        sucursales_seleccionadas = st.multiselect("Selecciona una o varias sucursales", options=sucursales_disponibles, default=sucursales_disponibles)
        st.markdown("<br><br>", unsafe_allow_html=True)
        # ----------------------------- TARJETAS: TOTAL ACUMULADO ANUAL Y MES ACTUAL ------------------------------------------------------------------------------------------------------------------
        if sucursales_seleccionadas:  # si hay selección
            df_filtrado = df[df["sucursal"].isin(sucursales_seleccionadas)]
        else:
            df_filtrado = df.copy()  # o un df vacío si quieres no mostrar nada

        total_anual = df_filtrado["monto"].sum()

        ultimo_mes = df_filtrado["mes_dt"].max()

        # Validar si ultimo_mes es NaT
        if pd.isna(ultimo_mes):
            texto_mes = "Sin datos"
            total_mensual = 0
        else:
            mes_en_ingles = ultimo_mes.strftime('%B')
            mes_en_espanol = meses_es.get(mes_en_ingles, mes_en_ingles)
            texto_mes = f"{mes_en_espanol} {ultimo_mes.year}"
            total_mensual = df_filtrado[df_filtrado["mes_dt"] == ultimo_mes]["monto"].sum()


        col1, col2 = st.columns(2)
        col1.metric(label="Total Acumulado Anual (2025)", value=f"${total_anual:,.2f}")
        col2.metric(label=f"Total Acumulado {texto_mes}", value=f"${total_mensual:,.2f}")

        st.title("Evolución mensual de compras por sucursal")
        
        # --------------------------- GRÁFICA DE LÍNEAS (evolución mensual) ------------------------------------------------------------------------------------------------------------------------------
        fig_lineas = go.Figure()
        for sucursal in sucursales_seleccionadas:
            if sucursal in df_pivot.columns:
                # Crear customdata con mes y sucursal para cada punto
                customdata = list(zip(df_pivot.index.astype(str), [sucursal]*len(df_pivot)))
                
                fig_lineas.add_trace(go.Scatter(
                    x=df_pivot.index,
                    y=df_pivot[sucursal],
                    mode='lines+markers',
                    name=sucursal,
                    line=dict(color=colores_sucursales.get(sucursal)),
                    customdata=customdata,
                    hovertemplate=(
                        "<b>Sucursal:</b> %{customdata[1]}<br>" +
                        "<b>Mes:</b> %{customdata[0]}<br>" +
                        "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
                    )
                ))

        fig_lineas.update_layout(
            title="Evolución mensual por sucursal",
            xaxis_title="Mes",
            yaxis_title="Total Comprado"
        )

        st.plotly_chart(
            fig_lineas,
            use_container_width=True,
            config={
                "scrollZoom": True,
                "modeBarButtonsToKeep": [
                    "toImage",
                    "zoom2d",
                    "autoScale2d",
                    "toggleFullscreen"
                ],
                "displaylogo": False
            }
        )

        #------------------------------ GRÁFICA DE BARRAS: COMPRAS ACUMULADAS POR CUENTA --------------------------------------------------------------------------------------
        # 1️⃣ Agregar abreviatura de la división
        df_filtrado = df[df["sucursal"].isin(sucursales_seleccionadas)].copy()

        # Función para obtener abreviatura
        def obtener_abreviatura(codigo):
            codigo_str = str(codigo).strip()
            for division, info in divisiones.items():
                if codigo_str in info["codigos"]:
                    return info["abreviatura"]
            return ""

        df_filtrado["abreviatura"] = df_filtrado["codigo_normalizado"].apply(obtener_abreviatura)

        # Agrupar por cuenta y sucursal
        df_cta = df_filtrado.groupby(["codigo_normalizado", "sucursal", "abreviatura"], as_index=False)["monto"].sum()

        # Crear etiqueta con abreviatura incluida
        df_cta["cuenta_sucursal"] = (
            df_cta["codigo_normalizado"].astype(str) + " (" +
            df_cta["abreviatura"] + ") - " +
            df_cta["sucursal"]
        )

        # Ordenar
        df_cta = df_cta.sort_values("monto", ascending=True)

        # Abreviar sucursal para leyenda
        df_cta["sucursal_abrev"] = df_cta["sucursal"].apply(lambda x: x[:3].capitalize())

        # 2️⃣ Crear gráfico con hovertemplate personalizado
        if not df_cta.empty:
            st.markdown("### Compras acumuladas por cuenta (anual)")

            fig = px.bar(
                df_cta,
                x="monto",
                y="cuenta_sucursal",
                orientation="h",
                color="sucursal_abrev",
                color_discrete_map={k[:3].capitalize(): v for k, v in colores_sucursales.items()},
                labels={
                    "monto": "Monto (MXN)",
                    "cuenta_sucursal": "Cuenta - Sucursal",
                    "sucursal_abrev": "Sucursal"
                },
                text=df_cta["monto"].apply(lambda x: f"${x:,.2f}"),
                custom_data=["sucursal", "abreviatura", "monto"]
            )

            altura_grafica = max(300, min(50 * len(df_cta), 1000))

            fig.update_traces(
                textposition="outside",
                cliponaxis=False,
                hovertemplate=(
                    "<b>Sucursal:</b> %{customdata[0]}<br>"
                    "<b>División:</b> %{customdata[1]}<br>"
                    "<b>Monto:</b> $%{customdata[2]:,.2f}<extra></extra>"
                )
            )

            fig.update_layout(
                xaxis_title="Monto (MXN)",
                yaxis_title="Cuenta - Sucursal",
                yaxis={"categoryorder": "total ascending"},
                height=altura_grafica,
                margin=dict(r=70, b=30),
                showlegend=False
            )

            st.plotly_chart(fig, use_container_width=True)
            st.markdown("<br><br>", unsafe_allow_html=True)

        #=================== GRAFICA DE BARRAS APILADAS DE MONTO POR MES Y CUENTA ========================
        # Validar selección
        if not sucursales_seleccionadas:
            st.warning("Selecciona al menos una sucursal para ver esta gráfica.")
        else:
            st.markdown("### Compras por Sucursal, mes a mes")
            # Filtrar por sucursales seleccionadas
            df_filtrado = df[df["sucursal"].isin(sucursales_seleccionadas)].copy()

            # Crear etiqueta cuenta_sucursal
            df_filtrado["cuenta_sucursal"] = df_filtrado["codigo_normalizado"] + " - " + df_filtrado["sucursal"]

            # Agregar abreviatura de la división
            df_filtrado["abreviatura"] = df_filtrado["codigo_normalizado"].apply(obtener_abreviatura)

            # Crear columna con cuenta-sucursal-abreviatura
            df_filtrado["cuenta_sucursal_abrev"] = (
                df_filtrado["codigo_normalizado"].astype(str) + " (" +
                df_filtrado["abreviatura"] + ") - " +
                df_filtrado["sucursal"]
            )

            # Agrupar por mes y cuenta_sucursal_abrev (en lugar de la columna anterior)
            df_mes_cta = df_filtrado.groupby(
                ["mes_nombre", "cuenta_sucursal_abrev", "sucursal", "division"], as_index=False
            )["monto"].sum()

            # Ordenar meses según orden_meses
            df_mes_cta["mes_nombre"] = pd.Categorical(df_mes_cta["mes_nombre"], categories=orden_meses, ordered=True)
            df_mes_cta = df_mes_cta.sort_values("mes_nombre")

            # Mostrar texto solo si seleccionó menos sucursales que las disponibles
            mostrar_texto = len(sucursales_seleccionadas) < len(sucursales_disponibles)

            # Definir colores y variable de color según cantidad de sucursales seleccionadas
            if len(sucursales_seleccionadas) == 1:
                # Colorear según división
                color_columna = "division"
                color_mapa = colores_divisiones  # asumo que tienes este dict definido con colores por división
            else:
                # Colorear según sucursal
                color_columna = "sucursal"
                color_mapa = colores_sucursales

            def es_color_claro(hex_color):
                """Devuelve True si el color es claro, False si es oscuro."""
                try:
                    r, g, b = mcolors.to_rgb(hex_color)
                    brillo = (r * 299 + g * 587 + b * 114) / 1000
                    return brillo > 0.6
                except Exception:
                    return False  # color inválido, lo tratamos como oscuro

            # Calcular porcentaje y texto
            df_mes_cta["total_mes"] = df_mes_cta.groupby("mes_nombre")["monto"].transform("sum")
            df_mes_cta["porcentaje"] = df_mes_cta["monto"] / df_mes_cta["total_mes"] * 100
            df_mes_cta["texto_monto"] = df_mes_cta.apply(lambda row: f"${row['monto']:,.0f} ({row['porcentaje']:.1f}%)", axis=1)

            fig = go.Figure()

            for valor in df_mes_cta[color_columna].unique():
                df_grupo = df_mes_cta[df_mes_cta[color_columna] == valor]
                fig.add_trace(go.Bar(
                    x=df_grupo["monto"],
                    y=df_grupo["mes_nombre"],
                    orientation="h",
                    name=valor,
                    marker=dict(color=color_mapa.get(valor, "#999999")),
                    text=df_grupo["texto_monto"] if mostrar_texto else None,
                    textposition="inside" if mostrar_texto else "none",
                    insidetextanchor="start",
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"  # ← ahora cuenta-sucursal-abreviatura
                        "<b>Monto:</b> $%{x:,.2f}<br>"
                        "<b>Porcentaje:</b> %{customdata[1]:.1f}%<extra></extra>"
                    ),
                    customdata=df_grupo[["cuenta_sucursal_abrev", "porcentaje"]]
                ))

            # Layout
            fig.update_layout(
                barmode="stack",
                height=max(300, min(70 * len(df_mes_cta["mes_nombre"].unique()), 800)),
                xaxis_title="Monto (MXN)",
                yaxis_title="Mes",
                xaxis_tickformat=",",  # ← importante también para ejes
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.3,
                    xanchor="center",
                    x=0.5,
                    title=None
                )
            )


            if mostrar_texto:
                colores_barras = df_mes_cta[color_columna].map(color_mapa).fillna("#666666")
                colores_texto = colores_barras.apply(lambda c: "black" if es_color_claro(c) else "white")
                df_mes_cta["color_texto"] = colores_texto.values

                for trace in fig.data:
                    barras_colores_texto = df_mes_cta[df_mes_cta[color_columna] == trace.name]["color_texto"].tolist()
                    trace.textfont = dict(color=barras_colores_texto)
                    trace.textposition = "inside"
                    trace.insidetextanchor = "middle"
                    trace.marker.line.width = 1
                    trace.marker.line.color = "black"
            else:
                for trace in fig.data:
                    trace.text = None
                    trace.marker.line.width = 1
                    trace.marker.line.color = "black"

            st.plotly_chart(
                fig,
                use_container_width=True,
                config={
                    "scrollZoom": True,
                    "modeBarButtonsToKeep": [
                        "zoom2d",        # Zoom con caja
                        "zoomIn2d",      # Zoom +
                        "zoomOut2d",     # Zoom -
                        "autoScale2d",   # Reset zoom
                        "pan2d",         # Pan (mover)
                        "toImage",       # Descargar imagen
                        "toggleSpikelines", # Líneas guía al pasar mouse (opcional)
                        "toggleFullscreen"
                    ],
                    "displaylogo": False
                }
            )

        # ============================== GRÁFICA DE BARRAS POR SUCURSAL ==============================================================================================
        if len(sucursales_seleccionadas) == 1:
            sucursal = sucursales_seleccionadas[0]
            df_suc = df[df["sucursal"] == sucursal].copy()
            df_suc = df_suc.groupby(["mes_nombre", "mes_dt"], as_index=False).agg({"monto": "sum"})
            df_suc = df_suc.sort_values("mes_dt", ascending=False)  # orden descendente
            df_suc["texto"] = df_suc["monto"].apply(lambda x: f"${x:,.0f}")

            fig_barras = px.bar(
                df_suc,
                x="mes_nombre",
                y="monto",
                text="texto",
                color_discrete_sequence=[colores_sucursales.get(sucursal, "#636EFA")],
                title=f"Compras mensuales de {sucursal} en 2025"
            )

            # Agregamos hovertemplate
            fig_barras.update_traces(
                textposition='inside',
                texttemplate='%{text}',
                hovertemplate=(
                    "<b>Sucursal:</b> " + sucursal + "<br>"
                    "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
                ),
                customdata=df_suc[["porcentaje"]] if "porcentaje" in df_suc.columns else df_suc.assign(porcentaje=100)[["porcentaje"]]
            )

            fig_barras.update_traces(textposition='inside', texttemplate='%{text}')
            fig_barras.update_layout(showlegend=False, xaxis_title="Mes", yaxis_title="Total Comprado")
            st.plotly_chart(fig_barras, use_container_width=True)
        else:
            #st.markdown("### Compras por Sucursal, mes a mes")
            for mes in orden_meses_desc:  # <- aquí el cambio para orden descendente
                df_mes = df[df["mes_nombre"] == mes]
                df_mes = df_mes[df_mes["sucursal"].isin(sucursales_seleccionadas)].copy()
                df_mes = df_mes.groupby("sucursal", as_index=False).agg({"monto": "sum"})
                total_mes = df_mes["monto"].sum()
                if total_mes == 0:
                    continue
                df_mes["porcentaje"] = df_mes["monto"] / total_mes * 100
                df_mes["texto"] = df_mes.apply(lambda row: f"${row['monto']:,.0f}<br>({row['porcentaje']:.1f}%)", axis=1)
                df_mes = df_mes.sort_values("monto", ascending=False)
                df_mes["sucursal"] = pd.Categorical(df_mes["sucursal"], categories=df_mes["sucursal"], ordered=True)

                fig_mes = px.bar(
                    df_mes,
                    x="sucursal",
                    y="monto",
                    text="texto",
                    color="sucursal",
                    color_discrete_map=colores_sucursales,
                    title=f"Compras en {mes}"
                )

                fig_mes.update_traces(
                    textposition='inside',
                    texttemplate='%{text}',
                    hovertemplate=(
                        "<b>Sucursal:</b> %{x}<br>"
                        "<b>Porcentaje:</b> %{customdata[0]:.1f}%<br>"
                        "<b>Monto:</b> $%{y:,.2f}<extra></extra>"
                    ),
                    customdata=df_mes[["porcentaje"]]
                )

                fig_mes.update_traces(textposition='inside', texttemplate='%{text}')
                fig_mes.update_layout(showlegend=False)
                st.plotly_chart(fig_mes, use_container_width=True, key=f"mes_{mes}")



    # ==========================================================================================================
    # ================================ ESTADO DE LIGADO ========================================
    # ==========================================================================================================
    elif opcion == "Estado de Ligado":
        st.title("Estado de Ligado de Facturas")
        # ----------- Información General - Estado de Ligado  (TARJETAS) -----------
        st.markdown("### Información general")
        # Filtramos el dataframe para obtener totales según el ligado_sistema
        monto_ligado = df[df["ligado_sistema"] == 1]["monto"].sum()
        monto_pendiente = df[df["ligado_sistema"] == 0]["monto"].sum()
        # Mostramos en tarjetas
        col1, col2 = st.columns(2)

        with col1:
            st.metric("✅ Total ligado en sistema", f"${monto_ligado:,.2f}")

        with col2:
            st.metric("🕒 Pendiente de ligar", f"${monto_pendiente:,.2f}")

        # ---------------- FILTRAR FACTURAS NO LIGADAS (GRAFICO DE LÍNEAS) ---------------------------------------------
        df_no_ligado = df[df["ligado_sistema"] == 0]

        # Agrupar por mes
        monto_mensual_no_ligado = (
            df_no_ligado.groupby("mes_nombre")["monto"]
            .sum()
            .reindex(orden_meses)
        )

        # --- GRÁFICO ---
        st.subheader("Monto mensual sin ligar")
        fig = px.line(
            x=monto_mensual_no_ligado.index,
            y=monto_mensual_no_ligado.values,
            labels={"x": "Mes", "y": "Monto sin ligar"},
            markers=True,
        )

        fig.update_traces(
            hovertemplate=(
                "<b>Mes:</b> %{x}<br>"
                "<b>Monto sin ligar:</b> $%{y:,.2f}<extra></extra>"
            )
        )

        fig.update_layout(
            xaxis_title="Mes",
            yaxis_title="Monto sin ligar",
            title="Tendencia mensual de facturas no ligadas"
        )

        st.plotly_chart(fig, use_container_width=True)

        # --- ---------CANTIDAD SIN LIGAR MENSUAL POR SUCURSAL (GRAFICO DE BARRAS APILADAS) -----------------------------------------------
       # Filtrar solo facturas sin ligar
        df_no_ligado = df[df["ligado_sistema"] == 0].copy()

        # Asegurarnos que mes_dt exista y sea datetime
        if "mes_dt" not in df_no_ligado.columns:
            df_no_ligado["mes_dt"] = pd.to_datetime(df_no_ligado["mes"].astype(str))

        # Obtener el mes actual (en formato periodo M)
        mes_actual = pd.to_datetime("today").to_period("M")

        # Agrupar monto por mes_nombre, sucursal y mes_dt (fecha)
        monto_por_mes_sucursal = df_no_ligado.groupby(
            ["mes_nombre", "sucursal", "mes_dt"]
        )["monto"].sum().reset_index()

        # Filtrar para excluir mes actual y posteriores
        monto_por_mes_sucursal = monto_por_mes_sucursal[
            monto_por_mes_sucursal["mes_dt"].dt.to_period("M") < mes_actual
        ]

        # Crear orden correcto solo con los meses filtrados
        meses_filtrados = [m for m in orden_meses if m in monto_por_mes_sucursal["mes_nombre"].unique()]
        monto_por_mes_sucursal["mes_nombre"] = pd.Categorical(
            monto_por_mes_sucursal["mes_nombre"],
            categories=meses_filtrados,
            ordered=True
        )

        # Ordenar DataFrame por fecha para que Plotly respete el orden cronológico
        monto_por_mes_sucursal = monto_por_mes_sucursal.sort_values("mes_dt")

        # Crear gráfico de barras apiladas horizontales con customdata
        fig = px.bar(
            monto_por_mes_sucursal,
            x="monto",
            y="mes_nombre",
            color="sucursal",
            orientation="h",
            title="Distribución mensual del monto sin ligar por sucursal",
            labels={"monto": "Monto sin ligar", "mes_nombre": "Mes"},
            category_orders={"mes_nombre": meses_filtrados},
            custom_data=["sucursal"]  # <-- para usar en hovertemplate
        )

        fig.update_layout(
            barmode="stack",
            xaxis_title="Monto sin ligar",
            yaxis_title="Mes"
        )

        # Hovertemplate personalizado usando customdata[0]
        fig.update_traces(
            hovertemplate=(
                "<b>Mes:</b> %{y}<br>"
                "<b>Sucursal:</b> %{customdata[0]}<br>"
                "<b>Monto sin ligar:</b> $%{x:,.2f}<extra></extra>"
            )
        )

        st.plotly_chart(fig, use_container_width=True)

        #------------- TABLA ------------------------------
        tabla_resumen = monto_por_mes_sucursal.pivot_table(
            index="mes_nombre",
            columns="sucursal",
            values="monto",
            aggfunc="sum",
            fill_value=0
        )

        # Ordenar los meses correctamente
        tabla_resumen = tabla_resumen.reindex(meses_filtrados)

        # Renombrar índice
        tabla_resumen.index.name = "Mes"

        # Función para aplicar estilo condicional
        def resaltar_valores(val):
            color = 'background-color: #BC13FE' if val != 0 else ''
            return color

        # Mostrar en Streamlit con estilo
        st.subheader("Tabla resumen del monto sin ligar por mes y sucursal")
        st.dataframe(
            tabla_resumen.style
                .applymap(resaltar_valores)
                .format("${:,.2f}")
        )

#------------------------------------------------------------------------------------------------------------------------------------------------

elif authentication_status is False:
    st.error("Usuario o contraseña incorrectos")
elif authentication_status is None:
    st.warning("Por favor ingresa tus credenciales")

# =============================
