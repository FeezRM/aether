"""Prepare Form and Fill & Sign: create, edit, detect and fill form fields; sign."""

from __future__ import annotations

import re
from typing import Literal

import pymupdf as fitz

from ..coords import parse_color, to_mu_point, to_mu_rect
from . import Ctx, op, page_list

FIELD_TYPES = {
    "text": fitz.PDF_WIDGET_TYPE_TEXT,
    "checkbox": fitz.PDF_WIDGET_TYPE_CHECKBOX,
    "radio": fitz.PDF_WIDGET_TYPE_RADIOBUTTON,
    "combobox": fitz.PDF_WIDGET_TYPE_COMBOBOX,
    "listbox": fitz.PDF_WIDGET_TYPE_LISTBOX,
    "signature": fitz.PDF_WIDGET_TYPE_SIGNATURE,
    "button": fitz.PDF_WIDGET_TYPE_BUTTON,
}

FieldType = Literal["text", "checkbox", "radio", "combobox", "listbox", "signature", "button"]


def iter_widgets(doc: fitz.Document):
    for page in doc:
        for w in page.widgets():
            yield page, w


def _find(doc: fitz.Document, name: str) -> list[tuple[fitz.Page, fitz.Widget]]:
    found = [(p, w) for p, w in iter_widgets(doc) if w.field_name == name]
    if not found:
        raise ValueError(f"No form field named {name!r}")
    return found


def _set_flag(flags: int, flag: int, on: bool | None) -> int:
    if on is None:
        return flags
    return flags | flag if on else flags & ~flag


@op("add_field", "forms", "Add a form field (text, checkbox, radio, dropdown, list, signature, button)")
def add_field(doc: fitz.Document, ctx: Ctx, page: int, rect: list[float], type: FieldType,
              name: str, value: str | bool | None = None, options: list[str] | None = None,
              multiline: bool = False, required: bool = False, readonly: bool = False,
              fontsize: float = 0, tooltip: str = "", button_caption: str = ""):
    page_list(doc, [page])
    pg = doc[page]
    if not name.strip():
        raise ValueError("Field name is required")
    if type != "radio" and any(w.field_name == name for _p, w in iter_widgets(doc)):
        raise ValueError(f"A field named {name!r} already exists")
    w = fitz.Widget()
    w.field_type = FIELD_TYPES[type]
    w.field_name = name
    w.rect = to_mu_rect(pg, rect)
    w.text_fontsize = fontsize
    w.field_label = tooltip
    w.border_color = (0.45, 0.5, 0.6)
    w.border_width = 1
    w.fill_color = (0.93, 0.95, 1.0)
    flags = 0
    flags = _set_flag(flags, fitz.PDF_FIELD_IS_REQUIRED, required)
    flags = _set_flag(flags, fitz.PDF_FIELD_IS_READ_ONLY, readonly)
    if type == "text" and multiline:
        flags |= fitz.PDF_TX_FIELD_IS_MULTILINE
    w.field_flags = flags
    if type in ("combobox", "listbox"):
        if not options:
            raise ValueError("Dropdown and list fields need options")
        w.choice_values = options
        w.field_value = value if isinstance(value, str) and value in options else options[0]
    elif type in ("checkbox", "radio"):
        w.field_value = bool(value)
    elif type == "button":
        w.button_caption = button_caption or name
    elif value is not None:
        w.field_value = str(value)
    pg.add_widget(w)
    return {"name": name}


@op("update_field", "forms", "Change a field's name, flags, options, size or position")
def update_field(doc: fitz.Document, ctx: Ctx, name: str, new_name: str | None = None,
                 required: bool | None = None, readonly: bool | None = None,
                 options: list[str] | None = None, fontsize: float | None = None,
                 tooltip: str | None = None, rect: list[float] | None = None):
    for pg, w in _find(doc, name):
        if new_name:
            w.field_name = new_name
        w.field_flags = _set_flag(w.field_flags, fitz.PDF_FIELD_IS_REQUIRED, required)
        w.field_flags = _set_flag(w.field_flags, fitz.PDF_FIELD_IS_READ_ONLY, readonly)
        if options is not None:
            w.choice_values = options
        if fontsize is not None:
            w.text_fontsize = fontsize
        if tooltip is not None:
            w.field_label = tooltip
        if rect is not None:
            w.rect = to_mu_rect(pg, rect)
        w.update()


@op("delete_field", "forms", "Delete a form field")
def delete_field(doc: fitz.Document, ctx: Ctx, name: str):
    for pg, w in _find(doc, name):
        pg.delete_widget(w)


def _apply_value(w: fitz.Widget, value) -> None:
    t = w.field_type
    if t == fitz.PDF_WIDGET_TYPE_CHECKBOX:
        on = value is True or str(value).lower() in ("true", "yes", "on", "1", w.on_state().lower())
        w.field_value = w.on_state() if on else "Off"
    elif t == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
        # For a radio group the value names the on-state of the chosen button.
        w.field_value = w.on_state() if str(value) in (w.on_state(), "True", "true") else "Off"
    elif t in (fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX):
        w.field_value = str(value)
    elif t == fitz.PDF_WIDGET_TYPE_TEXT:
        w.field_value = "" if value is None else str(value)
    else:
        return
    w.update()


@op("fill_fields", "forms", "Fill form fields: {field name: value}")
def fill_fields(doc: fitz.Document, ctx: Ctx, values: dict[str, str | bool | None]):
    missing = [n for n in values if not any(w.field_name == n for _p, w in iter_widgets(doc))]
    if missing:
        raise ValueError(f"Unknown fields: {', '.join(missing)}")
    for _pg, w in iter_widgets(doc):
        if w.field_name in values:
            _apply_value(w, values[w.field_name])
    return {"filled": len(values)}


@op("clear_form", "forms", "Reset every editable field to empty / unchecked (read-only fields keep their value)")
def clear_form(doc: fitz.Document, ctx: Ctx):
    for _pg, w in iter_widgets(doc):
        if w.field_flags & fitz.PDF_FIELD_IS_READ_ONLY:
            continue
        if w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
            w.field_value = "Off"
        elif w.field_type == fitz.PDF_WIDGET_TYPE_TEXT:
            w.field_value = ""
        else:
            continue
        w.update()


@op("detect_fields", "forms", "Auto-detect fillable areas (underscores, blank lines, boxes) and add fields")
def detect_fields(doc: fitz.Document, ctx: Ctx, pages: list[int] | None = None):
    added = []
    counter = sum(1 for _ in iter_widgets(doc))
    for i in page_list(doc, pages):
        pg = doc[i]
        existing = [w.rect for w in pg.widgets()]
        candidates: list[tuple[str, fitz.Rect, str]] = []
        words = pg.get_text("words")
        # 1. Runs of underscores in the text layer.
        for idx, w in enumerate(words):
            if re.fullmatch(r"_{4,}", w[4]):
                r = fitz.Rect(w[:4])
                label = words[idx - 1][4] if idx and words[idx - 1][6] == w[6] else ""
                candidates.append(("text", fitz.Rect(r.x0, r.y1 - 14, r.x1, r.y1 + 1), label))
        # 2. Drawn horizontal lines and small squares.
        for d in pg.get_drawings():
            r = d["rect"]
            if r.width > 60 and r.height < 2.5:
                above = fitz.Rect(r.x0, r.y0 - 14, r.x1, r.y0 - 0.5)
                if not pg.get_textbox(above).strip():
                    candidates.append(("text", fitz.Rect(r.x0, r.y0 - 14, r.x1, r.y0), ""))
            elif 7 <= r.width <= 18 and 7 <= r.height <= 18 and abs(r.width - r.height) < 2:
                candidates.append(("checkbox", fitz.Rect(r), ""))
        for kind, rect, label in candidates:
            if any(rect.intersects(e) for e in existing):
                continue
            counter += 1
            base = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_") or kind
            name = f"{base}_{counter}"
            w = fitz.Widget()
            w.field_type = FIELD_TYPES[kind]
            w.field_name = name
            w.rect = rect
            w.border_color = (0.45, 0.5, 0.6)
            w.fill_color = (0.93, 0.95, 1.0)
            if kind == "checkbox":
                w.field_value = False
            pg.add_widget(w)
            existing.append(rect)
            added.append({"page": i, "name": name, "type": kind})
    return {"added": added}


# --- Fill & Sign ---------------------------------------------------------

@op("place_mark", "fillsign", "Place a check, cross, dot, circle or line on the page (Fill & Sign)")
def place_mark(doc: fitz.Document, ctx: Ctx, page: int, point: list[float],
               mark: Literal["check", "cross", "dot", "circle", "line"] = "check",
               size: float = 12, color: str = "#000000"):
    page_list(doc, [page])
    pg = doc[page]
    p = to_mu_point(pg, point)
    rgb = parse_color(color)
    shape = pg.new_shape()
    h = size / 2
    if mark == "check":
        shape.draw_polyline([(p.x - h, p.y), (p.x - h / 3, p.y + h * 0.8), (p.x + h, p.y - h)])
        shape.finish(color=rgb, width=size / 8, closePath=False)
    elif mark == "cross":
        shape.draw_line((p.x - h, p.y - h), (p.x + h, p.y + h))
        shape.draw_line((p.x - h, p.y + h), (p.x + h, p.y - h))
        shape.finish(color=rgb, width=size / 8)
    elif mark == "dot":
        shape.draw_circle(p, size / 5)
        shape.finish(color=rgb, fill=rgb)
    elif mark == "circle":
        shape.draw_oval(fitz.Rect(p.x - size, p.y - h, p.x + size, p.y + h))
        shape.finish(color=rgb, width=1.2)
    else:
        shape.draw_line((p.x - size, p.y), (p.x + size, p.y))
        shape.finish(color=rgb, width=1.2)
    shape.commit()


@op("add_signature", "fillsign", "Sign with a drawn signature, an uploaded image, or typed text")
def add_signature(doc: fitz.Document, ctx: Ctx, page: int, rect: list[float],
                  strokes: list[list[list[float]]] | None = None,
                  stroke_box: list[float] | None = None,
                  blob_id: str | None = None, text: str | None = None,
                  color: str = "#0b1f66"):
    """strokes are in a local drawing box `stroke_box` = [width, height] and get scaled into rect."""
    if sum(x is not None for x in (strokes, blob_id, text)) != 1:
        raise ValueError("Give exactly one of strokes, blob_id or text")
    page_list(doc, [page])
    pg = doc[page]
    box = to_mu_rect(pg, rect)
    rgb = parse_color(color)
    if blob_id:
        _n, data = ctx.blob(blob_id)
        pg.insert_image(box, stream=data, keep_proportion=True)
    elif text:
        size = min(box.height * 0.7, box.width / max(len(text), 1) * 1.9)
        pg.insert_text(fitz.Point(box.x0 + 2, box.y1 - box.height * 0.25), text,
                       fontname="tiit", fontsize=size, color=rgb)
    else:
        if not stroke_box or len(stroke_box) != 2:
            raise ValueError("stroke_box [width, height] is required with strokes")
        sw, sh = stroke_box
        scale = min(box.width / sw, box.height / sh)
        ox = box.x0 + (box.width - sw * scale) / 2
        oy = box.y0 + (box.height - sh * scale) / 2
        shape = pg.new_shape()
        for s in strokes:
            if len(s) >= 2:
                shape.draw_polyline([(ox + x * scale, oy + y * scale) for x, y in s])
        shape.finish(color=rgb, width=max(1.0, 1.6 * scale), closePath=False,
                     lineCap=1, lineJoin=1)
        shape.commit()
