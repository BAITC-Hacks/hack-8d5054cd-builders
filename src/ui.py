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
        /* Final presentation layer: white surfaces, restrained teal, clear hierarchy. */
        .stApp [data-testid="stMain"] {
            background-image: radial-gradient(ellipse at 95% 0%, rgba(15,118,110,.055), transparent 45%);
        }
        .stApp .block-container { max-width: 1180px; }
        .stApp .ui-page-header { padding-bottom: .7rem; margin-bottom: .9rem; }
        .stApp .ui-page-header h1 {
            font-size: clamp(1.85rem, 3.2vw, 2.6rem);
            letter-spacing: -.045em;
            font-weight: 720;
            line-height: 1.16;
            max-width: 920px;
        }
        .stApp .ui-eyebrow {
            color: #0f766e;
            opacity: 1;
            font-size: .73rem;
            letter-spacing: .12em;
            margin-bottom: .85rem;
        }
        .stApp .ui-page-description { max-width: 660px; }
        .stApp [data-testid="stVerticalBlock"][class*="st-key-surface_"] {
            background: #fff;
            color: #263b47;
            border: 1px solid #e0e8e5;
            border-radius: 20px;
            padding: 1.5rem;
            box-shadow: 0 4px 20px rgba(26,59,48,.035);
        }
        .stApp [data-testid="stVerticalBlock"].st-key-surface_score {
            border-top: 3px solid #0f766e;
        }
        .stApp [data-testid="stVerticalBlock"].st-key-surface_filters { padding: 1rem 1.25rem; }
        .stApp [data-testid="stForm"] { border: 0; padding: 0; }
        .stApp [data-testid="stTextAreaRootElement"],
        .stApp [data-testid="stTextInputRootElement"] {
            border: 1px solid #dbe4e0;
            border-radius: 11px;
            background: #f8faf9;
            color: #263b47;
        }
        .stApp [data-testid="stTextAreaRootElement"]:focus-within,
        .stApp [data-testid="stTextInputRootElement"]:focus-within {
            border-color: #0f766e;
            box-shadow: 0 0 0 3px rgba(15,118,110,.1);
        }
        .stApp [data-testid="stExpander"] details {
            border-color: #e0e8e5;
            background: rgba(255,255,255,.45);
            border-radius: 13px;
        }
        .stApp [data-testid="stExpander"] summary { font-weight: 550; }
        .stApp [data-testid="stBaseButton-primary"],
        .stApp [data-testid="stBaseButton-primaryFormSubmit"] {
            border: 1px solid #0f766e;
            background: #0f766e;
            color: #fff;
            box-shadow: 0 3px 8px rgba(15,118,110,.12);
        }
        .stApp [data-testid="stBaseButton-primary"]:hover,
        .stApp [data-testid="stBaseButton-primaryFormSubmit"]:hover { background: #115e59; border-color: #115e59; }
        .stApp [data-testid="stSidebar"] { border-color: #e0e8e5; }
        .stApp [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
            background: #eaf4ef;
            border-color: transparent;
        }
        .ui-brand { display: flex; gap: .75rem; align-items: center; margin: .5rem 0 1.6rem; }
        .ui-brand-mark {
            display: grid; place-items: center; flex: 0 0 42px; height: 42px;
            background: #0f766e; color: #fff; border-radius: 13px;
            font-size: 1.35rem; font-weight: 700;
            box-shadow: 0 4px 10px rgba(15,118,110,.12);
        }
        .ui-brand-title { font-size: 1.3rem; font-weight: 750; letter-spacing: -.04em; }
        .ui-brand-note { font-size: .75rem; opacity: .75; margin-top: .12rem; }
        .stApp .ui-stepper { gap: .5rem; margin: 0 0 1.2rem; }
        .ui-step { padding: .85rem; border-color: #e0e8e5; border-radius: 12px; font-size: .84rem; }
        .ui-step-current { background: #eaf4ef; border-color: #7fb5a7; }
        .ui-step-number { width: 26px; height: 26px; font-size: .78rem; }
        .ui-readiness {
            display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: .4rem;
            margin: .25rem 0 .4rem;
        }
        .ui-readiness-item { padding: .55rem .65rem; border-left: 2px solid #dce5e0; color: #61746b; font-size: .75rem; }
        .ui-readiness-item strong { display: block; font-size: .8rem; }
        .ui-readiness-active { border-color: #0f766e; background: #edf6f1; color: #115e59; border-radius: 0 7px 7px 0; }
        .ui-breakdown-row { margin-bottom: .85rem; }
        .ui-breakdown-label { display: flex; justify-content: space-between; gap: .8rem; font-size: .84rem; margin-bottom: .35rem; }
        .ui-breakdown-label strong { white-space: nowrap; font-variant-numeric: tabular-nums; }
        .ui-breakdown-track { height: 6px; border-radius: 8px; background: #e7eeea; overflow: hidden; }
        .ui-breakdown-fill { height: 100%; border-radius: 8px; background: #0f766e; }
        .ui-badge { border-radius: 7px; padding: .35rem .7rem; }
        .ui-summary { padding: 1.35rem; border-radius: 16px; }
        .stApp [data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; letter-spacing: -.035em; }
        @media (max-width: 850px) {
            .stApp .block-container { padding-left: 1.25rem; padding-right: 1.25rem; }
            .ui-step { flex-basis: 160px; }
            .stApp [data-testid="stVerticalBlock"][class*="st-key-surface_"] { padding: 1.1rem; }
        }
        @media (prefers-reduced-motion: reduce) {
            .ui-step, .ui-badge, .ui-summary { transition: none; }
        }
        </style>
        """
    )


def brand() -> None:
    """Show the product wordmark without a competing page heading."""
    st.html(
        '<div class="ui-brand"><span class="ui-brand-mark" aria-hidden="true">П</span>'
        '<div><div class="ui-brand-title">Практикум</div>'
        '<div class="ui-brand-note">Бизнес-задачи. Опыт в деле.</div></div></div>'
    )


def readiness_track(score: int) -> None:
    """Display the four fixed readiness thresholds without changing the score."""
    value = max(0, min(int(score), 100))
    levels = ((0, 39, "Черновик"), (40, 69, "Рабочая"), (70, 89, "Готовая"), (90, 100, "Приоритетная"))
    items = []
    for lower, upper, label in levels:
        current = lower <= value <= upper
        css = " ui-readiness-active" if current else ""
        aria = ' aria-current="step"' if current else ""
        items.append(f'<div class="ui-readiness-item{css}"{aria}><strong>{label}</strong>{lower}–{upper} баллов</div>')
    st.html('<div class="ui-readiness" aria-label="Уровни готовности">' + "".join(items) + "</div>")


def rating_breakdown(rows: Sequence[dict]) -> None:
    """Render score components with visible numbers and accessible progress bars."""
    items = []
    for row in rows:
        possible = max(1, int(row["possible"]))
        earned = max(0, min(int(row["earned"]), possible))
        label = _text(row["label"])
        items.append(
            '<div class="ui-breakdown-row"><div class="ui-breakdown-label">'
            f'<span>{label}</span><strong>{earned} / {possible}</strong></div>'
            f'<div class="ui-breakdown-track" role="progressbar" aria-label="{label}" '
            f'aria-valuenow="{earned}" aria-valuemin="0" aria-valuemax="{possible}">'
            f'<div class="ui-breakdown-fill" style="width:{earned / possible * 100:.1f}%"></div></div></div>'
        )
    st.html('<div class="ui-breakdown">' + "".join(items) + "</div>")


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
