def tabla_totales_html(tabla_horizontal_df):
    tabla_html = tabla_horizontal_df.applymap(lambda x: f"${x:,.2f}")

    header_html = ''.join([
        f'<th style="background-color:#390570; color:white; padding:8px; text-align:left;">{col}</th>'
        for col in tabla_html.columns
    ])

    row_html = ''.join([
        f'<td style="padding:8px; text-align:left;">{val}</td>'
        for val in tabla_html.iloc[0]
    ])

    return f"""
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

def construir_tabla_comparativa(df_comp):
    estilos_css = """
    <style>
        .tabla-wrapper { overflow-x: auto; width: 100%; }
        .tabla-comparativa { min-width: 100%; width: max-content; border-collapse: collapse; }
        .tabla-comparativa thead th {
            background-color: #0B083D; color: white; padding: 8px;
            position: sticky; top: 0; z-index: 3;
        }
        .tabla-comparativa td, .tabla-comparativa th {
            padding: 8px; font-size: 14px; white-space: nowrap; border: 1px solid white;
        }
        .tabla-comparativa tbody td:first-child {
            position: sticky; left: 0; background-color: #0B083D; color: white; font-weight: bold;
        }
        .subida { background-color: #7D1F08; color: white; }
        .bajada { background-color: #184E08; color: white; }
        .neutra { color: white; }
    </style>
    """

    html = f"{estilos_css}<div class='tabla-wrapper'><table class='tabla-comparativa'>"
    html += "<thead><tr><th>Mes</th><th>Total Comprado</th><th>Diferencia ($)</th><th>Variación (%)</th></tr></thead><tbody>"

    for _, row in df.iterrows():
        clase_color = (
            "subida" if "⬆" in row["Diferencia ($)"] else
            "bajada" if "⬇" in row["Diferencia ($)"] else
            "neutra"
        )
        html += f"<tr><td>{row['Mes']}</td>"
        html += f"<td class='{clase_color}'>{row['Total Comprado']}</td>"
        html += f"<td class='{clase_color}'>{row['Diferencia ($)']}</td>"
        html += f"<td class='{clase_color}'>{row['Variación (%)']}</td></tr>"

    html += "</tbody></table></div>"
    return html
