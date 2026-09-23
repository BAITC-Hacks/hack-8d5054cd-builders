"""Small, escaped presentation helpers shared by the Streamlit views."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from html import escape

import streamlit as st


_TONES = frozenset({"neutral", "success", "warning", "info", "danger"})
_MONTHS = ("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")
_LOCAL_TIMEZONE = timezone(timedelta(hours=5))


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _tone(value: str) -> str:
    return value if value in _TONES else "neutral"


def apply_ui() -> None:
    """Apply layout styles; native control colours come from Streamlit's theme."""
    st.html(
        """
        <style>
        .stApp {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        .stApp .block-container {
            max-width: 1200px;
            padding: 4.5rem 2.5rem 4rem;
        }
        .stApp h1, .stApp h2, .stApp h3 {
            font-family: inherit;
            letter-spacing: -.025em;
            line-height: 1.3;
            font-weight: 650;
            overflow-wrap: anywhere;
        }
        .stApp h1 { font-size: 2rem; padding-top: 0; }
        .stApp h2 { font-size: 1.4rem; }
        .stApp h3 { font-size: 1.12rem; }
        .stApp p, .stApp li { line-height: 1.65; }
        .stApp [data-testid="stCaptionContainer"] {
            font-size: .9rem;
            color: inherit;
            opacity: .8;
        }
        .stApp [data-testid="stWidgetLabel"] p {
            font-size: .95rem;
            font-weight: 550;
            line-height: 1.5;
        }
        .stApp [data-testid="stTextInput"] input,
        .stApp [data-testid="stTextArea"] textarea {
            font-size: 1rem;
            line-height: 1.6;
        }
        .stApp [data-testid="stTextInput"] input { min-height: 44px; }
        .stApp [data-testid="stTextArea"] textarea { padding: .75rem; }
        .stApp [data-baseweb="select"] > div { min-height: 46px; }
        .stApp [data-testid="stButton"] button,
        .stApp [data-testid="stFormSubmitButton"] button,
        .stApp [data-testid="stLinkButton"] a {
            min-height: 44px;
            padding: .55rem 1rem;
            border-radius: 9px;
            font-weight: 550;
        }
        .stApp button:focus-visible, .stApp a:focus-visible,
        .stApp input:focus-visible, .stApp textarea:focus-visible {
            outline: 3px solid #0f766e;
            outline-offset: 3px;
        }
        .stApp [data-testid="stVerticalBlockBorderWrapper"] > div,
        .stApp [data-testid="stForm"] {
            border-radius: 14px;
        }
        .stApp [data-testid="stForm"] { padding: 1.25rem; }
        .stApp [data-testid="stExpander"] details {
            border-radius: 12px;
        }
        .stApp [data-testid="stExpander"] summary {
            min-height: 48px;
            padding-top: .65rem;
            padding-bottom: .65rem;
        }
        .stApp [data-testid="stAlert"] { border-radius: 10px; }
        .stApp [data-testid="stMetricLabel"] { font-size: .9rem; }
        .stApp [data-testid="stMetricValue"] {
            font-size: 1.65rem;
            font-weight: 650;
            letter-spacing: -.025em;
        }
        .stApp [data-testid="stMetricDelta"] { font-size: .85rem; }
        .stApp [data-testid="stSidebar"] {
            border-right: 1px solid #e2e8f0;
        }
        .stApp [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-top: .5rem;
        }
        .stApp [data-testid="stSidebar"] h1 { font-size: 1.35rem; }
        .stApp [data-testid="stSidebar"] h2 { font-size: 1.1rem; }
        .stApp [data-testid="stSidebar"] [data-testid="stRadio"] label {
            min-height: 46px;
            padding: .6rem .75rem;
            border: 1px solid transparent;
            border-radius: 9px;
            margin: 0 0 .2rem;
            align-items: center;
        }
        .stApp [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
            background: #e8f4f1;
            border-color: #b6d8d1;
            color: #115e59;
        }
        .stApp [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p {
            color: #115e59;
            font-weight: 650;
        }
        .stApp [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:focus-visible) {
            outline: 3px solid #0f766e;
            outline-offset: 2px;
        }
        .ui-page-header { margin-bottom: .75rem; }
        .ui-eyebrow {
            font-size: .78rem;
            font-weight: 650;
            letter-spacing: .08em;
            text-transform: uppercase;
            opacity: .8;
            margin: 0 0 .55rem;
        }
        .ui-page-header h1 { margin: 0 0 .6rem; padding: 0; }
        .ui-page-description {
            max-width: 780px;
            font-size: 1rem;
            line-height: 1.65;
            opacity: .85;
            margin: 0;
            white-space: pre-line;
            overflow-wrap: anywhere;
        }
        .stApp .ui-stepper {
            display: flex;
            flex-wrap: wrap;
            gap: .65rem;
            padding: 0;
            margin: .25rem 0 1rem;
            list-style: none;
        }
        .ui-step {
            flex: 1 1 140px;
            display: flex;
            align-items: center;
            gap: .65rem;
            padding: .85rem 1rem;
            border: 1px solid #dce3e8;
            border-radius: 12px;
            background: #ffffff;
            color: #64748b;
            font-size: .92rem;
            font-weight: 500;
        }
        .ui-step-number {
            display: inline-flex;
            flex-shrink: 0;
            width: 28px;
            height: 28px;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            background: #f1f5f9;
            color: #475569;
            font-size: .85rem;
            font-weight: 650;
        }
        .ui-step-current { background: #edf7f4; border-color: #0f766e; color: #115e59; font-weight: 650; }
        .ui-step-current .ui-step-number { background: #0f766e; color: #ffffff; }
        .ui-step-done { color: #115e59; border-color: #c8ddd7; }
        .ui-step-done .ui-step-number { background: #e7f2ee; color: #115e59; }
        .ui-badge {
            display: inline-block;
            padding: .28rem .65rem;
            border-radius: 6px;
            font-size: .8rem;
            font-weight: 600;
            line-height: 1.5;
            overflow-wrap: anywhere;
        }
        .ui-neutral { background: #edf1f5; color: #475569; border-color: #dce3e8; }
        .ui-success { background: #eaf4ee; color: #256043; border-color: #c7ddce; }
        .ui-warning { background: #fff6e5; color: #805415; border-color: #ead9b5; }
        .ui-info { background: #edf4fa; color: #315b7c; border-color: #cbdbe8; }
        .ui-danger { background: #f9eeed; color: #934c48; border-color: #e7cfcc; }
        .ui-summary {
            padding: 1rem 1.2rem;
            border: 1px solid;
            border-color: inherit;
            border-radius: 12px;
            margin-bottom: .35rem;
        }
        .ui-summary.ui-neutral { border-color: #dce3e8; }
        .ui-summary.ui-success { border-color: #c7ddce; }
        .ui-summary.ui-warning { border-color: #ead9b5; }
        .ui-summary.ui-info { border-color: #cbdbe8; }
        .ui-summary.ui-danger { border-color: #e7cfcc; }
        .ui-summary h3 { margin: 0 0 .35rem; padding: 0; color: inherit; font-size: 1rem; }
        .ui-summary p { margin: 0; font-size: .95rem; line-height: 1.65; white-space: pre-line; overflow-wrap: anywhere; }
        @media (max-width: 850px) {
            .stApp .block-container { padding-left: 1.25rem; padding-right: 1.25rem; }
            .ui-step { flex-basis: 160px; }
        }
        @media (prefers-reduced-motion: reduce) {
            .ui-step, .ui-badge, .ui-summary { transition: none; }
        }
        </style>
        """
    )


def page_header(eyebrow: str, title: str, description: str = "") -> None:
    """Render a single page heading with a short, plain-language introduction."""
    st.html(
        '<header class="ui-page-header">'
        f'<p class="ui-eyebrow">{_text(eyebrow)}</p>'
        f'<h1>{_text(title)}</h1>'
        f'<p class="ui-page-description">{_text(description)}</p>'
        "</header>"
    )


def stepper(labels: Sequence[str], current_index: int) -> None:
    """Show ordered steps; current_index is zero-based. This is not navigation."""
    if not labels:
        return
    current = max(0, min(current_index, len(labels) - 1))
    items = []
    for index, label in enumerate(labels):
        state = "current" if index == current else "done" if index < current else "upcoming"
        marker = "✓" if index < current else str(index + 1)
        aria = ' aria-current="step"' if index == current else ""
        description = "завершён" if index < current else "текущий" if index == current else "впереди"
        accessible_label = _text(f"Шаг {index + 1}: {label}, {description}")
        items.append(
            f'<li class="ui-step ui-step-{state}"{aria} aria-label="{accessible_label}">'
            f'<span class="ui-step-number" aria-hidden="true">{marker}</span>'
            f"<span>{_text(label)}</span></li>"
        )
    st.html('<ol class="ui-stepper" aria-label="Этапы создания задачи">' + "".join(items) + "</ol>")


def status_badge(label: str, tone: str = "neutral") -> None:
    """Render a text status with a restrained, accessible colour treatment."""
    st.html(f'<span class="ui-badge ui-{_tone(tone)}">{_text(label)}</span>')


def summary_card(title: str, body: str, tone: str = "neutral") -> None:
    """Render a compact explanation or next action; body is plain text."""
    st.html(
        f'<section class="ui-summary ui-{_tone(tone)}">'
        f"<h3>{_text(title)}</h3><p>{_text(body)}</p></section>"
    )


def format_date(iso: str) -> str:
    """Format an ISO date in the demo's Kazakhstan timezone (UTC+5)."""
    if not isinstance(iso, str) or not iso.strip():
        return "Дата не указана"
    try:
        value = datetime.fromisoformat(iso.strip().replace("Z", "+00:00"))
    except ValueError:
        return "Дата не указана"
    if len(iso.strip()) == 10:
        return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(_LOCAL_TIMEZONE)
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}, {value:%H:%M}"
