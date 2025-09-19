import plotly.graph_objects as go
import pandas as pd

def grafica_total_mensual(df_total_mes, orden_meses):
    df_total_mes = df_total_mes.reindex([m for m in orden_meses if m in df_total_mes.index])
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_total_mes.index,
        y=df_total_mes.values,
        mode="lines+markers",
        name="Total",
        line=dict(color="blue"),
        hovertemplate="%{x}<br>Total: $%{y:,.2f}<extra></extra>"
    ))

    fig.update_layout(
        xaxis_title="Mes",
        yaxis_title="Monto",
        yaxis_tickformat=","
    )
    return fig

def grafica_diferencias_mensuales(df_mensual):
    df_mensual["color"] = df_mensual["diferencia"].apply(lambda x: "#f81515" if x >= 0 else "#33FF00")
    df_mensual["texto"] = df_mensual["diferencia"].apply(lambda x: f"${x:,.2f}")

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

    fig_dif.update_layout(
        title="Diferencia mensual de compras vs mes anterior",
        xaxis_title="Mes",
        yaxis_title="Diferencia en monto (MXN)",
        yaxis=dict(zeroline=True, zerolinecolor="black"),
        height=450,
        margin=dict(r=70)
    )
    return fig_dif