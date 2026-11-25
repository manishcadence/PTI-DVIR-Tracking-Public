"""A direct daily driver trend with clearly separated inspection volume."""
import plotly.express as px
import streamlit as st

from ..stakeholder import daily_activity_report
from .charts import GREEN, show
from .tables import table


def render_daily_participation(scope):
    frame = daily_activity_report(scope)
    total = len(scope.drivers)
    latest = frame.iloc[-1]
    best = frame.loc[frame.drivers_with_PTI.idxmax()]
    st.subheader('Drivers recording PTI each day')
    st.caption(f'Each point counts drivers with at least one pre/post-trip inspection that day. '
               f'Population: {total:,} drivers in the filtered report.')
    left, middle, right = st.columns(3)
    with left:
        st.markdown(f'**Latest day · {latest.date:%b %d}**  \n'
                    f'{latest.drivers_with_PTI:,} drivers · {latest.share_of_drivers_percent:.1f}%')
    with middle:
        st.markdown(f'**Highest daily count · {best.date:%b %d}**  \n'
                    f'{best.drivers_with_PTI:,} drivers · {best.share_of_drivers_percent:.1f}%')
    with right:
        st.markdown(f'**Daily average**  \n{frame.drivers_with_PTI.mean():.1f} drivers')
    figure = px.line(frame, x='date', y='drivers_with_PTI', markers=True,
                     text='drivers_with_PTI', color_discrete_sequence=[GREEN],
                     custom_data=['share_of_drivers_percent', 'PTI_records', 'drivers_without_record'],
                     labels={'date': '', 'drivers_with_PTI': 'Drivers with PTI'})
    figure.update_traces(
        line=dict(width=3), marker=dict(size=9), textposition='top center',
        cliponaxis=False,
        hovertemplate='<b>%{x|%a, %b %d}</b><br>Drivers with PTI: %{y:,}'
                      '<br>Share of report: %{customdata[0]:.1f}%'
                      '<br>PTI records: %{customdata[1]:,}'
                      '<br>Drivers without a record: %{customdata[2]:,}<extra></extra>')
    figure.update_xaxes(tickformat='%a<br>%b %d', dtick='D1')
    figure.update_yaxes(range=[0, max(1, frame.drivers_with_PTI.max()) * 1.2], dtick=None)
    show(figure, 'overview-daily-participation', height=330)
    st.caption('A driver counts once per date, even with several inspections. '
               'A day without a record does not establish a missed required inspection.')
    with st.expander('Daily counts and CSV download'):
        table(frame.rename(columns={'date': 'inspection_date'}), 'overview-daily-counts', size=15)
