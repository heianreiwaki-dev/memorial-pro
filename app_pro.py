import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
import os
import base64
import numpy as np

# --- Streamlit用パッチ ---
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
PAPER_SIZES = {"2L版 (127x178mm)": (600, 840), "L版 (89x127mm)": (420, 600), "ハガキ (100x148mm)": (472, 700), "A4 (210x297mm)": (700, 990)}
PRESET_TEXT_COLORS = {"漆黒 ⚫": "#000000", "濃いグレー 🔘": "#333333", "墨色 🔘": "#444444", "ホワイト ⚪": "#FFFFFF", "ダークブラウン 🪵": "#3D2B1F", "ゴールド風 🟡": "#B8860B"}
FONT_PATH = "msgothic.ttc"
CARD_INNER_PAD = 36 # 枠の太さ目安
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
    if not files: return {"（デフォルト背景）": None}
    return {os.path.splitext(f)[0]: os.path.join(cards_dir, f) for f in files}

DESIGNS = load_designs()

def make_bg_image(design_name, size_key):
    """背景（枠）をキャンバスサイズにピッタリ合わせて作成"""
    W, H = PAPER_SIZES[size_key]
    path = DESIGNS.get(design_name)
    if path and os.path.exists(path):
        bg = Image.open(path).convert("RGBA")
    else:
        bg = Image.new("RGBA", (W, H), (245, 245, 240, 255))
    return bg.resize((W, H), Image.LANCZOS)

def pil_to_b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

# --- 🤖 自動レイアウト (最大化ロジック) ---
def auto_layout(photo_infos, text_defs, card_w, card_h):
    n = len(photo_infos)
    objects = []
    margin = CARD_INNER_PAD + 20
    x0, y0 = margin, margin
    aw, ah = card_w - margin * 2, card_h - margin * 2

    full_text = "\n".join([t.get("text", "") for t in text_defs])
    text_zone_h = int(ah * 0.3) if full_text else 0
    ph_area_h = ah - text_zone_h - (GAP if full_text else 0)

    rects = []
    if n == 1: rects = [(x0, y0, aw, ph_area_h)]
    elif n == 2:
        pw = (aw - GAP) // 2
        rects = [(x0, y0, pw, ph_area_h), (x0 + pw + GAP, y0, pw, ph_area_h)]
    elif n == 3:
        pw_l = int(aw * 0.55) - GAP//2
        pw_r = aw - pw_l - GAP
        ph_r = (ph_area_h - GAP) // 2
        rects = [(x0, y0, pw_l, ph_area_h), (x0+pw_l+GAP, y0, pw_r, ph_r), (x0+pw_l+GAP, y0+ph_r+GAP, pw_r, ph_r)]
    elif n >= 4:
        cols = 2 if n <= 4 else 3
        rows = (n + cols - 1) // cols
        pw, ph = (aw - GAP*(cols-1))//cols, (ph_area_h - GAP*(rows-1))//rows
        for i in range(n): rects.append((x0 + (i%cols)*(pw+GAP), y0 + (i//cols)*(ph+GAP), pw, ph))

    for info, (rx, ry, rw, rh) in zip(photo_infos, rects):
        ow, oh = info["w"], info["h"]
        scale = min(rw / ow, rh / oh)
        objects.append({
            "type": "image", "src": info["src"],
            "left": int(rx + (rw - ow*scale)//2), "top": int(ry + (rh - oh*scale)//2),
            "scaleX": scale, "scaleY": scale, "originX": "left", "originY": "top"
        })
    
    if full_text:
        ty = y0 + ph_area_h + GAP
        for t in text_defs:
            obj = dict(t); obj["left"], obj["top"] = x0 + aw//2, ty
            obj["originX"] = "center"
            objects.append(obj)
            ty += t.get("fontSize", 30) + 10
    return objects

# ==========================================
# メインセッション
# ==========================================
if "S" not in st.session_state:
    st.session_state.S = {
        "canvas_objects": [], "photo_store": [], "canvas_key": 0,
        "design": list(DESIGNS.keys())[0], "text_defs": [], "processed_files": set(),
        "color_mode": "代表的な色", "custom_color": "#333333"
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
                resized = img.resize((int(img.width * (350/max(img.size))), int(img.height * (350/max(img.size)))), Image.LANCZOS)
                info = {"src": pil_to_b64(resized), "w": resized.width, "h": resized.height}
                S["photo_store"].append(info)
                S["canvas_objects"].append({"type": "image", "src": info["src"], "left": 100, "top": 100, "scaleX": 1.0, "scaleY": 1.0})
                S["processed_files"].add(f.name)
            S["canvas_key"] += 1; st.rerun()

    st.header("✍️ 文字・色設定")
    msg = st.text_input("メッセージ")
    
    # 💡 文字色選択の改善
    S["color_mode"] = st.radio("色の選び方", ["代表的な色", "オリジナル"], horizontal=True)
    if S["color_mode"] == "代表的な色":
        t_preset = st.selectbox("色リスト", list(PRESET_TEXT_COLORS.keys()))
        final_color = PRESET_TEXT_COLORS[t_preset]
        st.markdown(f'<div style="width:30px;height:30px;background-color:{final_color};border:1px solid #ccc;border-radius:5px;"></div>', unsafe_allow_html=True)
    else:
        final_color = st.color_picker("オリジナル色選択", S["custom_color"])
        S["custom_color"] = final_color

    if st.button("文字を追加"):
        if msg:
            t_obj = {"type": "i-text", "text": msg, "fill": final_color, "fontSize": 36, "fontFamily": "ゴシック体"}
            S["canvas_objects"].append(t_obj); S["text_defs"].append(t_obj)
            S["canvas_key"] += 1; st.rerun()

    st.divider()
    mode = st.radio("レイアウト", ["手動", "AI自動レイアウト"])
    if mode == "AI自動レイアウト" and st.button("🤖 AI自動配置を実行", type="primary"):
        S["canvas_objects"] = auto_layout(S["photo_store"], S["text_defs"], W_val, H_val)
        S["canvas_key"] += 1; st.rerun()

    if st.button("🔄 全リセット"):
        for k in ["canvas_objects", "photo_store", "text_defs", "processed_files"]: S[k] = [] if k != "processed_files" else set()
        S["canvas_key"] += 1; st.rerun()

# --- 🖼️ デザイン画面 (キャンバス) ---
bg_img = make_bg_image(S["design"], selected_size)

st.subheader("2. 写真・文字を配置してください")
# 💡 keyにすべての変動要素を含めることで、背景を確実に強制リフレッシュします
c_key = f"canvas_v10_{S['design']}_{S['canvas_key']}_{selected_size}"

canvas_result = st_canvas(
    fill_color="rgba(0,0,0,0)",
    background_image=bg_img, # PIL画像をそのまま渡す
    initial_drawing={"objects": S["canvas_objects"]},
    height=H_val, width=W_val,
    drawing_mode="transform",
    key=c_key,
)

# --- 📥 保存 ---
st.divider()
if st.button("✅ 完成画像を確定する", type="primary", use_container_width=True):
    if canvas_result.image_data is not None:
        rgba = Image.fromarray(canvas_result.image_data.astype(np.uint8), "RGBA")
        final = Image.alpha_composite(bg_img.convert("RGBA"), rgba).convert("RGB")
        
        st.success("プレビュー生成完了！")
        col1, col2 = st.columns(2)
        with col1: st.image(final, caption="完成見本", use_container_width=True)
        with col2:
            buf_j = io.BytesIO(); final.save(buf_j, format="JPEG", quality=95)
            st.download_button("📥 JPEGで保存", buf_j.getvalue(), "memorial.jpg", "image/jpeg", use_container_width=True)
            buf_p = io.BytesIO(); final.save(buf_p, format="PDF", resolution=100.0)
            st.download_button("📥 PDFで保存", buf_p.getvalue(), "memorial.pdf", "application/pdf", use_container_width=True)