import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
import os
import base64
import numpy as np

# --- Streamlit用パッチ (背景表示エラー回避) ---
import streamlit.elements.image as st_image
import streamlit.elements.lib.image_utils as image_utils
if not hasattr(st_image, "image_to_url"):
    st_image.image_to_url = image_utils.image_to_url
class FakeLayoutConfig:
    def __init__(self, width):
        self.width = width
        self.use_container_width = False
original_image_to_url = st_image.image_to_url
def patched_image_to_url(image, width_or_config, *args, **kwargs):
    if isinstance(width_or_config, (int, float)):
        width_or_config = FakeLayoutConfig(int(width_or_config))
    return original_image_to_url(image, width_or_config, *args, **kwargs)
st_image.image_to_url = patched_image_to_url
image_utils.image_to_url = patched_image_to_url

# ==========================================
# 定数定義
# ==========================================
PAPER_SIZES = {
    "2L版 (127x178mm)": (600, 840),
    "L版 (89x127mm)": (420, 600),
    "ハガキ (100x148mm)": (472, 700),
    "A4 (210x297mm)": (700, 990)
}
PRESET_TEXT_COLORS = {
    "漆黒 ⚫": "#000000",
    "濃いグレー 🔘": "#333333",
    "墨色 🔘": "#444444",
    "ホワイト ⚪": "#FFFFFF",
    "ダークブラウン 🪵": "#3D2B1F",
    "ゴールド風 🟡": "#B8860B"
}
FONT_PATH = "msgothic.ttc"
CARD_INNER_PAD = 36
GAP = 12

st.set_page_config(page_title="プロ・メモリアルカード", layout="wide")

# ==========================================
# 関数
# ==========================================
def load_designs():
    cards_dir = "cards"
    os.makedirs(cards_dir, exist_ok=True)
    exts = (".jpg", ".jpeg", ".png")
    files = sorted([f for f in os.listdir(cards_dir) if f.lower().endswith(exts)])
    if not files:
        return {"（デフォルト背景）": None}
    return {os.path.splitext(f)[0]: os.path.join(cards_dir, f) for f in files}

DESIGNS = load_designs()

def make_bg_image(design_name, size_key):
    W, H = PAPER_SIZES[size_key]
    path = DESIGNS.get(design_name)
    if path and os.path.exists(path):
        bg = Image.open(path).convert("RGBA").resize((W, H), Image.LANCZOS)
    else:
        bg = Image.new("RGBA", (W, H), (250, 248, 243, 255))
        draw = ImageDraw.Draw(bg)
        border_outer = 10
        draw.rectangle([border_outer, border_outer, W - border_outer, H - border_outer], outline=(160, 130, 90, 255), width=3)
    return bg

def pil_to_b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def wrap_text(text, max_chars_per_line):
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current_line = ""
        char_count = 0
        for char in paragraph:
            char_width = 2 if ord(char) > 0x7F else 1
            if char_count + char_width > max_chars_per_line * 2:
                lines.append(current_line)
                current_line = char
                char_count = char_width
            else:
                current_line += char
                char_count += char_width
        if current_line:
            lines.append(current_line)
    return "\n".join(lines)

def calculate_font_size_and_wrap(text, area_width, area_height, font_size_hint=36):
    font_size = font_size_hint
    min_font = 14
    while font_size >= min_font:
        chars_per_line = max(1, int(area_width / font_size))
        wrapped = wrap_text(text, chars_per_line)
        line_count = len(wrapped.split("\n"))
        total_height = line_count * (font_size + 8)
        if total_height <= area_height:
            return wrapped, font_size
        font_size -= 2
    return wrap_text(text, max(1, int(area_width / min_font))), min_font

# --- 🤖 自動レイアウト ---
def auto_layout(photo_infos, text_defs, card_w, card_h):
    n = len(photo_infos)
    objects = []
    margin = CARD_INNER_PAD + 20
    x0, y0 = margin, margin
    aw, ah = card_w - margin * 2, card_h - margin * 2

    full_text = "\n".join([t.get("text", "") for t in text_defs])
    if full_text:
        text_zone_h = min(int(ah * 0.35), len(full_text.split("\n")) * 42 + 20)
    else:
        text_zone_h = 0
    ph_area_h = ah - text_zone_h - (GAP if full_text else 0)

    rects = []
    if n == 1: rects = [(x0, y0, aw, ph_area_h)]
    elif n == 2:
        pw = (aw - GAP) // 2
        rects = [(x0, y0, pw, ph_area_h), (x0 + pw + GAP, y0, pw, ph_area_h)]
    elif n == 3:
        pw_l = int(aw * 0.55) - GAP // 2
        pw_r = aw - pw_l - GAP
        ph_r = (ph_area_h - GAP) // 2
        rects = [(x0, y0, pw_l, ph_area_h), (x0 + pw_l + GAP, y0, pw_r, ph_r), (x0 + pw_l + GAP, y0 + ph_r + GAP, pw_r, ph_r)]
    elif n >= 4:
        cols = 2 if n <= 4 else 3
        rows = (n + cols - 1) // cols
        pw, ph = (aw - GAP * (cols - 1)) // cols, (ph_area_h - GAP * (rows - 1)) // rows
        for i in range(n): rects.append((x0 + (i % cols) * (pw + GAP), y0 + (i // cols) * (ph + GAP), pw, ph))

    for info, (rx, ry, rw, rh) in zip(photo_infos, rects):
        ow, oh = info["w"], info["h"]
        scale = min(rw / ow, rh / oh)
        objects.append({
            "type": "image", "src": info["src"], "left": int(rx + (rw - ow * scale) // 2), "top": int(ry + (rh - oh * scale) // 2),
            "scaleX": scale, "scaleY": scale, "originX": "left", "originY": "top", "_id": info.get("_id")
        })

    if full_text:
        ty = y0 + ph_area_h + GAP
        remaining_h = text_zone_h
        for t in text_defs:
            wrapped, final_size = calculate_font_size_and_wrap(t.get("text", ""), aw - 20, remaining_h, t.get("fontSize", 32))
            obj = dict(t)
            obj.update({"text": wrapped, "fontSize": final_size, "left": x0 + aw // 2, "top": ty, "originX": "center", "width": aw - 20, "textAlign": "center"})
            objects.append(obj)
            ty += len(wrapped.split("\n")) * (final_size + 8) + 10
    return objects

# ==========================================
# メインセッション
# ==========================================
if "S" not in st.session_state:
    st.session_state.S = {
        "canvas_objects": [], "photo_store": [], "canvas_key": 0, "design": list(DESIGNS.keys())[0],
        "text_defs": [], "processed_files": set(), "color_mode": "代表的な色", "custom_color": "#333333"
    }
S = st.session_state.S

# ==========================================
# UI
# ==========================================
st.title("🕯️ プロ・メモリアルカード (AI自動レイアウト)")

with st.sidebar:
    st.header("📋 基本設定")
    selected_size = st.selectbox("出力サイズ", list(PAPER_SIZES.keys()))
    W_val, H_val = PAPER_SIZES[selected_size]

    new_design = st.selectbox("デザイン選択 (枠)", list(DESIGNS.keys()), index=list(DESIGNS.keys()).index(S["design"]))
    if new_design != S["design"]:
        S["design"] = new_design
        S["canvas_key"] += 1
        st.rerun()

    st.header("📸 写真追加")
    uploaded = st.file_uploader("写真を選択", accept_multiple_files=True)
    if uploaded:
        new_fs = [f for f in uploaded if f.name not in S["processed_files"]]
        if new_fs and st.button(f"{len(new_fs)}枚を反映"):
            for f in new_fs:
                img = Image.open(f).convert("RGBA")
                resized = img.resize((int(img.width * (350 / max(img.size))), int(img.height * (350 / max(img.size)))), Image.LANCZOS)
                photo_id = f"photo_{f.name}"
                info = {"src": pil_to_b64(resized), "w": resized.width, "h": resized.height, "_id": photo_id}
                S["photo_store"].append(info)
                S["canvas_objects"].append({"type": "image", "src": info["src"], "left": 100, "top": 100, "scaleX": 1.0, "scaleY": 1.0, "_id": photo_id})
                S["processed_files"].add(f.name)
            S["canvas_key"] += 1
            st.rerun()

    st.header("✍️ 文字・色設定")
    msg = st.text_area("メッセージ", height=80)
    S["color_mode"] = st.radio("色の選び方", ["代表的な色", "オリジナル"], horizontal=True)
    if S["color_mode"] == "代表的な色":
        t_preset = st.selectbox("色リスト", list(PRESET_TEXT_COLORS.keys()))
        final_color = PRESET_TEXT_COLORS[t_preset]
        st.markdown(f'<div style="width:30px;height:30px;background-color:{final_color};border:1px solid #ccc;border-radius:5px;"></div>', unsafe_allow_html=True)
    else:
        final_color = st.color_picker("オリジナル色選択", S["custom_color"])
        S["custom_color"] = final_color

    font_size_input = st.slider("基準サイズ", 16, 60, 32, 2)
    if st.button("文字を追加"):
        if msg:
            text_id = f"text_{len(S['text_defs'])}"
            t_obj = {"type": "i-text", "text": msg, "fill": final_color, "fontSize": font_size_input, "fontFamily": "ゴシック体", "textAlign": "center", "width": W_val - 100, "_id": text_id}
            S["canvas_objects"].append(t_obj)
            S["text_defs"].append(t_obj)
            S["canvas_key"] += 1
            st.rerun()

    # ──────────────────────────────────────────
    # 【新機能：個別削除メニュー】
    # ──────────────────────────────────────────
    if S["text_defs"] or S["photo_store"]:
        st.divider()
        st.subheader("🗑️ 素材の個別削除")
        
        # 文字の削除
        for i, t in enumerate(S["text_defs"]):
            col1, col2 = st.columns([4, 1])
            col1.caption(f"✍️: {t['text'][:10]}...")
            if col2.button("❌", key=f"del_txt_{i}"):
                # 削除処理
                target_id = t.get("_id")
                S["text_defs"].pop(i)
                S["canvas_objects"] = [obj for obj in S["canvas_objects"] if obj.get("_id") != target_id]
                S["canvas_key"] += 1
                st.rerun()
        
        # 写真の削除
        for i, p in enumerate(S["photo_store"]):
            col1, col2 = st.columns([4, 1])
            col1.caption(f"📷: 写真 {i+1}")
            if col2.button("❌", key=f"del_img_{i}"):
                target_id = p.get("_id")
                S["photo_store"].pop(i)
                S["canvas_objects"] = [obj for obj in S["canvas_objects"] if obj.get("_id") != target_id]
                # 処理済みファイル名からも削除
                file_to_remove = next((name for name, pid in zip(list(S["processed_files"]), [p.get("_id") for p in S["photo_store"]]) if pid == target_id), None)
                if file_to_remove: S["processed_files"].discard(file_to_remove)
                S["canvas_key"] += 1
                st.rerun()

    st.divider()
    mode = st.radio("レイアウト", ["手動", "AI自動レイアウト"])
    if mode == "AI自動レイアウト" and st.button("🤖 AI自動配置を実行", type="primary"):
        S["canvas_objects"] = auto_layout(S["photo_store"], S["text_defs"], W_val, H_val)
        S["canvas_key"] += 1
        st.rerun()

    if st.button("🔄 全リセット"):
        for k in ["canvas_objects", "photo_store", "text_defs"]: S[k] = []
        S["processed_files"] = set()
        S["canvas_key"] += 1
        st.rerun()

# --- 🖼️ キャンバス ---
bg_cache_key = f"{S['design']}_{selected_size}"
if S.get("bg_cache_key") != bg_cache_key:
    bg_pil = make_bg_image(S["design"], selected_size)
    S["bg_b64"] = pil_to_b64(bg_pil)
    S["bg_cache_key"] = bg_cache_key

st.subheader("2. 写真・文字を配置してください")
bg_obj = {"type": "image", "src": S["bg_b64"], "left": 0, "top": 0, "selectable": False, "evented": False}
all_objects = [bg_obj] + S["canvas_objects"]

canvas_result = st_canvas(
    fill_color="rgba(0,0,0,0)", background_color="#ffffff", initial_drawing={"objects": all_objects},
    height=H_val, width=W_val, drawing_mode="transform", key=f"canvas_v15_{S['canvas_key']}_{S['design']}"
)

# --- 📥 保存 ---
st.divider()
if st.button("✅ 完成画像を確定する", type="primary", use_container_width=True):
    if canvas_result.image_data is not None:
        rgba = Image.fromarray(canvas_result.image_data.astype(np.uint8), "RGBA")
        white_bg = Image.new("RGB", (W_val, H_val), (255, 255, 255))
        white_bg.paste(rgba.convert("RGB"), mask=rgba.split()[3])
        final = white_bg
        st.success("プレビュー生成完了！")
        col1, col2 = st.columns(2)
        with col1: st.image(final, use_container_width=True)
        with col2:
            buf_j = io.BytesIO(); final.save(buf_j, format="JPEG", quality=95)
            st.download_button("📥 JPEGで保存", buf_j.getvalue(), "memorial.jpg", "image/jpeg", use_container_width=True)
            buf_p = io.BytesIO(); final.save(buf_p, format="PDF", resolution=100.0)
            st.download_button("📥 PDFで保存", buf_p.getvalue(), "memorial.pdf", "application/pdf", use_container_width=True)