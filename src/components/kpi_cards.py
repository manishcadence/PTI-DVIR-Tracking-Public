"""Reusable dashboard metric cards."""
import streamlit as st
from hashlib import sha256


def metrics(values: list[tuple[str, int]]) -> None:
    for offset in range(0, len(values), 4):
        row = values[offset:offset + 4]
        for column, (label, value) in zip(st.columns(len(row)), row):
            column.metric(label, f"{value:,}", border=True)


def colored_metrics(values, *, details=None):
    """Native accessible metrics inside themed cards; never embed uploaded text in HTML."""
    tones={'blue':('#eff6ff','#1e40af','#bfdbfe'),
           'green':('#f0fdf4','#166534','#bbf7d0'),
           'amber':('#fffbeb','#92400e','#fde68a'),
           'purple':('#faf5ff','#6b21a8','#e9d5ff')}
    details=details or {}
    for offset in range(0,len(values),4):
        row=values[offset:offset+4]
        for column,(label,value) in zip(st.columns(len(row)),row):
            tone,description=details.get(label,('blue','TruckMate roster · current report scope'))
            background,accent,border=tones[tone]
            key='tracking-card-'+sha256(label.encode()).hexdigest()[:12]
            st.markdown(f'''<style>
                .st-key-{key} {{background:{background};border:1px solid {border};
                    border-top:4px solid {accent};border-radius:12px;padding:16px;min-height:172px;}}
                .st-key-{key} [data-testid="stMetricValue"] {{color:{accent};}}
                .st-key-{key} [data-testid="stMetricLabel"] p {{color:#172940;}}
                .st-key-{key} [data-testid="stCaptionContainer"] p {{color:#475569;}}
            </style>''',unsafe_allow_html=True)
            with column.container(key=key):
                st.metric(label,f'{value:,}',help=description)
                st.caption(description)
