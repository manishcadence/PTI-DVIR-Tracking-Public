"""Calendar heatmap with accessible labels and discrete activity colors."""
import plotly.graph_objects as go
import streamlit as st

from ..analytics import daily_status
from ..filters import Scope
from .charts import GRAY, GREEN, RED, YELLOW

LABELS = ["No recorded PTI", "Done (pre/post-trip)", "Requires review", "Unsafe inspection"]
COLORS = [GRAY, GREEN, YELLOW, RED]


def heatmap(scope: Scope, driver_ids: list[str]) -> None:
    if not driver_ids:
        return
    cells = daily_status(scope, driver_ids)
    names = scope.drivers.set_index("driver_id").driver_name.to_dict()
    labels = [f"{names.get(key) or 'Unknown'} ({key})" for key in driver_ids]
    colorscale = [(edge, color) for index, color in enumerate(COLORS)
                  for edge in (index / 4, (index + 1) / 4)]
    figure = go.Figure(go.Heatmap(
        z=cells.to_numpy(), x=[day.isoformat() for day in scope.dates], y=labels,
        zmin=-0.5, zmax=3.5, xgap=3, ygap=3, colorscale=colorscale, showscale=False,
        text=[[LABELS[value] for value in row] for row in cells.to_numpy()],
        hovertemplate="%{y}<br>%{x}<br>%{text}<extra></extra>",
    ))
    figure.update_xaxes(type="category", side="top", tickangle=-35)
    figure.update_yaxes(autorange="reversed", automargin=True)
    figure.update_layout(height=max(130, 26 * len(labels) + 72),
                         margin=dict(l=8, r=12, t=60, b=10))
    st.plotly_chart(figure, width="stretch", config={"displaylogo": False, "displayModeBar": False})
    st.caption("🟩 Done (pre/post-trip)　 🟨 Requires review　 🟥 Unsafe inspection　 ⬜ No recorded PTI")
