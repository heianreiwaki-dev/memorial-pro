import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image, ImageDraw, ImageFont, ImageOps
import base64
import os
import io
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
# 定数・設定
# ==========================================
CARD_W = 560
PADDING = 80
CANVAS_W = CARD_W + PADDING * 2
PHOTO_MAX_PX = 350
CARD_INNER_PAD = 36 # デザイン枠の太さ（目安）
GAP = 12
FONT_PATH = "msgothic.ttc"
CARDS_DIR = "cards"
os.makedirs(CARDS_DIR, exist_ok=True)

# 🎨 代表的な文字色プリセット
COLOR_PRESETS = {
    "漆黒 (標準)": "#000000",
    "濃いグレー": "#333333",
    "墨色": "#444444",
    "白 (背景が濃い時)": "#FFFFFF",
    "濃紺": "#000080",
    "ダークブラウン": "#3D2B1F",
    "ゴールド風": "#B8860B"
}

def load_designs():
    exts = (".jpg", ".jpeg", ".png")
    files = sorted([f for f in os.listdir(CARDS_DIR) if f.lower().endswith(exts)])
    if not files: return {"（デフォルト）": None}
    return {os.path.splitext(f)[0]: os.path.join(CARDS_DIR, f) for f in files}

DESIGNS = load_designs()

# ==========================================
# ユーティリティ
# ==========================================
def resize_pil(img, max_px):
    w, h = img.size
    r = max_px / max(w, h)
    return img.resize((int(w*r), int(h*r)), Image.LANCZOS)

def pil_to_b64(img):
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def make_bg(design_name):
    path = DESIGNS.get(design_name)
    if path and os.path.exists(path):
        bg = Image.open(path).convert("RGBA")
    else:
        bg = Image.new("RGBA", (CARD_W, 400), (245, 245, 240, 255))
    card_h = int(CARD_W * bg.height / bg.width)
    canvas_h = card_h + PADDING * 2
    # 背景の土台
    canvas = Image.new("RGBA", (CANVAS_W, canvas_h), (210, 205, 200, 255))
    # カード画像を中央に貼り付け（完成品用ベース）
    canvas.paste(bg.resize((CARD_W, card_h)), (PADDING, PADDING))
    return canvas, card_h, canvas_h

# ==========================================
# 🤖 自動レイアウトロジック
# ==========================================
def auto_layout(photo_infos, text_defs, card_w, card_h):
    n = len(photo_infos)
    objects = []
    # 💡 枠の内側のSafe Areaを計算 (auto_layout調整用margin)
    margin = CARD_INNER_PAD + 15 
    x0, y0 = PADDING + margin, PADDING + margin
    aw, ah = card_w - margin * 2, card_h - margin * 2
    
    # テキストエリアを下部に確保
    text_zone_h = int(ah * 0.28) if text_defs else 0
    ph_area_h = ah - text_zone_h - (GAP if text_defs else 0)
    
    rects = []
    if n == 1: rects = [(x0, y0, aw, ph_area_h)]
    elif n >= 2:
        cols = 2 if n <= 4 else 3
        rows = (n + cols - 1) // cols
        pw, ph = (aw - GAP*(cols-1))//cols, (ph_area_h - GAP*(rows-1))//rows
        for i in range(n): rects.append((x0 + (i%cols)*(pw+GAP), y0 + (i//cols)*(ph+GAP), pw, ph))
        
    for info, (rx, ry, rw, rh) in zip(photo_infos, rects):
        scale = min(rw / info["canvas_w"], rh / info["canvas_h"])
        objects.append({
            "type": "image", "src": info["canvas_b64"], 
            "left": int(rx + (rw - info["canvas_w"]*scale)//2), 
            "top": int(ry + (rh - info["canvas_h"]*scale)//2), 
            "scaleX": scale, "scaleY": scale,
            "originX": "left", "originY": "top"
        })
        
    if text_defs:
        ty = y0 + ph_area_h + GAP
        for t in text_defs:
            obj = dict(t); obj["left"], obj["top"] = x0 + 10, ty
            objects.append(obj); ty += t.get("fontSize", 30) + 10
    return objects

# ==========================================
# メイン UI
# ==========================================
st.set_page_config(page_title="プロ・メモリアルカード", layout="wide")
st.title("🕯️ プロ・メモリアルカード (AI自動レイアウト版)")

if "canvas_objects" not in st.session_state:
    st.session_state.update({
        "canvas_objects": [], "photo_store": [], "canvas_key": 0, 
        "design": list(DESIGNS.keys())[0], "text_defs": [], "processed_files": set(), "mode": "手動"
    })

with st.sidebar:
    st.header("🖼️ 背景デザイン")
    design_names = list(DESIGNS.keys())
    st.session_state.design = st.selectbox("デザイン切替", design_names, index=design_names.index(st.session_state.design))
    
    st.divider()
    st.header("📸 写真追加")
    uploaded = st.file_uploader("写真を選択", accept_multiple_files=True)
    if uploaded:
        new_fs = [f for f in uploaded if f.name not in st.session_state.processed_files]
        if new_fs and st.button(f"{len(new_fs)}枚を反映"):
            for f in new_fs:
                img = Image.open(f).convert("RGBA")
                resized = resize_pil(img, PHOTO_MAX_PX)
                info = {"canvas_b64": pil_to_b64(resized), "canvas_w": resized.width, "canvas_h": resized.height}
                st.session_state.photo_store.append(info)
                # 手動用：中央付近に配置
                st.session_state.canvas_objects.append({
                    "type": "image", "src": info["canvas_b64"], 
                    "left": CANVAS_W//2 - resized.width//2, "top": CANVAS_W//2 - resized.height//2, 
                    "scaleX": 1.0, "scaleY": 1.0
                })
                st.session_state.processed_files.add(f.name)
            st.session_state.canvas_key += 1
            st.rerun()

    st.divider()
    st.header("✍️ コメント・色設定")
    msg = st.text_input("カードに入れる言葉")
    
    # 💡 文字色選択機能の強化
    col1, col2 = st.columns(2)
    with col1:
        color_type = st.radio("色選択モード", ["代表的な色", "オリジナル"])
    with col2:
        if color_type == "代表的な色":
            selected_preset = st.selectbox("色リスト", list(COLOR_PRESETS.keys()))
            final_text_color = COLOR_PRESETS[selected_preset]
            # プレビュー表示
            st.markdown(f'<div style="width:30px;height:30px;background-color:{final_text_color};border:1px solid #ccc;border-radius:5px;"></div>', unsafe_allow_stdio=True)
        else:
            final_text_color = st.color_picker("カスタム色", "#333333")

    if st.button("文字を追加"):
        if msg:
            t_obj = {
                "type": "i-text", "text": msg, 
                "fill": final_text_color, # 💡 決定した色を適用
                "fontSize": 36, "fontFamily": "ゴシック体",
                "originX": "left", "originY": "top"
            }
            # 手動用：下部に配置
            _, card_h_tmp, _ = make_bg(st.session_state.design)
            t_obj["left"], t_obj["top"] = PADDING + CARD_INNER_PAD + 20, PADDING + int(card_h_tmp * 0.7)
            
            st.session_state.canvas_objects.append(t_obj)
            st.session_state.text_defs.append(t_obj)
            st.session_state.canvas_key += 1
            st.rerun()

    st.divider()
    st.header("🤖 レイアウト設定")
    st.session_state.mode = st.radio("配置モード", ["手動 (自由配置)", "自動レイアウト (AI)"])
    if st.session_state.mode == "自動レイアウト (AI)":
        if st.button("🤖 自動配置を実行", type="primary", use_container_width=True):
            if not st.session_state.photo_store and not st.session_state.text_defs:
                st.warning("写真または文字を追加してください。")
            else:
                _, card_h_tmp, _ = make_bg(st.session_state.design)
                st.session_state.canvas_objects = auto_layout(
                    st.session_state.photo_store, st.session_state.text_defs, CARD_W, card_h_tmp
                )
                st.session_state.canvas_key += 1
                st.rerun()

    st.divider()
    if st.button("🔄 全リセット"):
        for k in ["canvas_objects", "photo_store", "text_defs", "processed_files"]:
            st.session_state[k] = [] if isinstance(st.session_state[k], list) else set()
        st.session_state.canvas_key += 1; st.rerun()

# ==========================================
# キャンバス (デザイン上での枠表示対応)
# ==========================================
bg_img_base, card_h, canvas_h = make_bg(st.session_state.design)

# 💡 編集画面用に、土台画像に「赤いSafe Area枠（点線）」を描画する
canvas_bg_gui = bg_img_base.copy()
draw = ImageDraw.Draw(canvas_bg_gui)

# Safe Areaの計算 (auto_layoutのmarginと同じ)
guide_margin = CARD_INNER_PAD + 15
x0_guide, y0_guide = PADDING + guide_margin, PADDING + guide_margin
x1_guide, y1_guide = PADDING + CARD_W - guide_margin, PADDING + card_h - guide_margin

# 赤い点線（簡易的に細い線で代用）を描画
draw.rectangle([x0_guide, y0_guide, x1_guide, y1_guide], outline="red", width=2)

# ガイドテキスト（編集画面のみ）
try:
    guide_font = ImageFont.truetype(FONT_PATH, 16)
    draw.text((x0_guide + 5, y0_guide - 25), "↓ 内側Safe Area (写真はこの枠内に配置推奨) ↓", fill="red", font=guide_font)
except: pass


# キャンバス
st.subheader("2. 写真・文字を配置してください")
canvas_result = st_canvas(
    fill_color="rgba(0,0,0,0)",
    background_image=canvas_bg_gui, # 💡 ガイド枠付きの画像を背景に設定
    initial_drawing={"objects": st.session_state.canvas_objects},
    height=canvas_h, width=CANVAS_W,
    drawing_mode="transform",
    key=f"pro_v6_{st.session_state.canvas_key}_{st.session_state.design}",
)

# ==========================================
# 完成画像の確定・保存 (赤い枠は含まない)
# ==========================================
st.divider()
if st.button("✅ 完成画像を確定する", type="primary", use_container_width=True):
    if canvas_result.json_data is not None:
        # 1. ユーザーが配置したオブジェクトのレイヤーを取得
        arr = canvas_result.image_data.astype(np.uint8)
        obj_layer = Image.fromarray(arr, "RGBA")
        
        # 2. 【最重要】赤い枠を含まない「真っ白な背景ベース」に重ねる
        final_merged = Image.alpha_composite(bg_img_base.convert("RGBA"), obj_layer)
        
        # 3. カード部分だけ切り抜く
        final_card = final_merged.crop((PADDING, PADDING, PADDING + CARD_W, PADDING + card_h)).convert("RGB")
        
        st.session_state.confirmed_img = final_card
        st.success("完成プレビューを生成しました。下から保存してください。")
        st.rerun()


# ダウンロードエリア
if "confirmed_img" in st.session_state and st.session_state.confirmed_img:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.image(st.session_state.confirmed_img, caption="完成プレビュー (保存用)", use_container_width=True)
    with col2:
        st.write("### 💾 保存")
        buf = io.BytesIO()
        st.session_state.confirmed_img.save(buf, format="JPEG", quality=95)
        st.download_button(
            "📥 JPEG画像をダウンロード", buf.getvalue(), 
            "memorial_card.jpg", "image/jpeg", use_container_width=True
        )