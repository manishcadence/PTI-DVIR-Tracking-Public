"""Daily own-DVIR calendar: discrete statuses with readable cell labels."""
from html import escape
import plotly.graph_objects as go


COLORS = ['#eef2f6', '#d1fae5', '#fef3c7', '#ede9fe', '#dbeafe']


def calendar_figure(frame, events, dates):
    grouped = events[events.inspection_date.isin(dates)].groupby(
        ['driver_id', 'inspection_date']).agg(records=('record_key', 'size'), review=('needs_review', 'any'))
    values, labels, details, names = [], [], [], []
    for row in frame.itertuples():
        cells, text, hover = [], [], []
        name = escape(str(row.driver_name))
        driver_id = escape(str(row.driver_id))
        vehicles = escape(str(row.vehicle_names or 'Not supplied'))
        names.append(f'{name}<br><span style="font-size:10px">ID {driver_id}</span>')
        for day in dates:
            holiday = day in row.holidays
            if (row.driver_id, day) in grouped.index:
                entry = grouped.loc[(row.driver_id, day)]
                count = int(entry.records)
                mark = 2 if entry.review else 1
                label = f'{count}<br>Review' if entry.review else f'{count}<br>DVIR' + ('s' if count != 1 else '')
                status = f'Recorded · {count} own DVIR' + ('s' if count != 1 else '')
                if entry.review:
                    status += ' · data review needed'
                if holiday:
                    status += ' · day off (DVIR retained)'
                    label += '*'
            else:
                training_day=getattr(row,'training_completed_date',None)
                not_trained=getattr(row,'training_explicitly_incomplete',False)
                before_training=training_day is not None and day<=training_day
                if holiday:
                    mark,label,status=3,'Day off','Day off · no own DVIR recorded'
                elif not_trained or before_training:
                    mark=4
                    label='Not<br>trained' if not_trained else 'Training<br>date' if day==training_day else 'Before<br>training'
                    status='Not assessed for missing DVIR · not trained' if not_trained else f'Not assessed before/at training date: {training_day:%Y-%m-%d}'
                else:
                    mark,label,status=0,'No DVIR','No own DVIR recorded'
            cells.append(mark)
            text.append(label)
            hover.append(f'<b>{name}</b> · ID {driver_id}<br>{day:%A, %b %d, %Y}<br>'
                         f'<b>{status}</b><br>Vehicles in report: {vehicles}')
        values.append(cells)
        labels.append(text)
        details.append(hover)
    scale = []
    for index, color in enumerate(COLORS):
        scale.extend([[index / len(COLORS), color], [(index + 1) / len(COLORS), color]])
    fig = go.Figure(go.Heatmap(
        z=values, x=list(range(len(dates))), y=list(range(len(frame))),
        text=labels, customdata=details, texttemplate='%{text}', textfont=dict(size=11, color='#172b4d'),
        zmin=-0.5, zmax=len(COLORS)-0.5, colorscale=scale, showscale=False,
        xgap=3, ygap=3, hoverongaps=False, hovertemplate='%{customdata}<extra></extra>'))
    fig.update_xaxes(side='top', tickmode='array', tickvals=list(range(len(dates))),
                     ticktext=[f'<b>{day:%a}</b><br>{day:%b %d}' for day in dates],
                     tickfont=dict(size=11, color='#334155'), fixedrange=True,
                     showgrid=False, zeroline=False, automargin=True)
    fig.update_yaxes(autorange='reversed', tickmode='array', tickvals=list(range(len(frame))),
                     ticktext=names, tickfont=dict(size=12, color='#172b4d'), fixedrange=True,
                     showgrid=False, zeroline=False, automargin=True)
    fig.update_layout(height=max(230, 52 * len(frame) + 100),
                      margin=dict(l=8, r=10, t=65, b=12), font=dict(family='Inter, sans-serif'),
                      plot_bgcolor='#cbd5e1', paper_bgcolor='#ffffff', dragmode=False,
                      hoverlabel=dict(bgcolor='#ffffff', font_color='#172b4d', align='left'))
    return fig
