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

# 🎨 文字色プリセット
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

def prepare_text_image_fitting(text, initial_size, color, target_w, target_h, f_path):
    """
    💡 文字がターゲットの矩形に収まるまで、フォントサイズを縮小してレンダリングする
    """
    font_full_path = f_path
    font_size = initial_size
    min_size = 10
    
    while font_size >= min_size:
        # フォントを作成
        try: font = ImageFont.truetype(font_full_path, font_size)
        except: font = ImageFont.load_default()
        
        # テキストのサイズを測定（レンダリングせず）
        dummy_img = Image.new("RGBA", (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        bbox = dummy_draw.multiline_textbbox((0, 0), text, font=font, align="center")
        tw, th = int(bbox[2] - bbox[0] + 10), int(bbox[3] - bbox[1] + 10)
        
        # ターゲットエリアに収まるか確認
        if tw <= target_w and th <= target_h:
            # 収まる！レンダリングして返す
            txt_img = Image.new("RGBA", (max(tw, 1), max(th, 1)), (0, 0, 0, 0))
            txt_draw = ImageDraw.Draw(txt_img)
            # 中央配置
            txt_draw.multiline_text((tw//2, th//2), text, font=font, fill=color, anchor="mm", align="center")
            return txt_img, font_size
        
        # 収まらない！フォントサイズを縮小
        font_size -= 2
        
    # 最小フォントサイズでも収まらない！最小サイズでレンダリング（はみ出す）
    try: font = ImageFont.truetype(font_full_path, min_size)
    except: font = ImageFont.load_default()
    dummy_img = Image.new("RGBA", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    bbox = dummy_draw.multiline_textbbox((0, 0), text, font=font, align="center")
    tw, th = int(bbox[2] - bbox[0] + 10), int(bbox[3] - bbox[1] + 10)
    txt_img = Image.new("RGBA", (max(tw, 1), max(th, 1)), (0, 0, 0, 0))
    txt_draw = ImageDraw.Draw(txt_img)
    txt_draw.multiline_text((tw//2, th//2), text, font=font, fill=color, anchor="mm", align="center")
    return txt_img, min_size

def make_bg(design_name):
    path = DESIGNS.get(design_name)
    if path and os.path.exists(path):
        bg = Image.open(path).convert("RGBA")
    else:
        bg = Image.new("RGBA", (CARD_W, 400), (245, 245, 240, 255))
    card_h = int(CARD_W * bg.height / bg.width)
    canvas_h = card_h + PADDING * 2
    canvas = Image.new("RGBA", (CANVAS_W, canvas_h), (210, 205, 200, 255))
    canvas.paste(bg.resize((CARD_W, card_h)), (PADDING, PADDING))
    return canvas, card_h, canvas_h

# ==========================================
# 🤖 自動レイアウトロジック (完全統合版)
# ==========================================
def auto_layout(photo_infos, text_defs, card_w, card_h):
    n = len(photo_infos)
    objects = []
    margin = CARD_INNER_PAD + 15 
    x0, y0 = PADDING + margin, PADDING + margin
    aw, ah = card_w - margin * 2, card_h - margin * 2

    # テキストエリアを下部に確保
    full_text = "\n".join([t.get("text", "") for t in text_defs])
    if full_text:
        # テキストエリアの高さの決定ロジックを柔軟に
        _, card_h_tmp, _ = make_bg(st.session_state.design)
        text_zone_ratio = max(0.28, min(0.60, len(full_text) / 200 * 0.28)) # 文字数に応じて最大60%まで確保
        text_zone_h = int(ah * text_zone_ratio)
        ph_area_h = ah - text_zone_h - GAP
        # 最小限の写真エリアを確保
        ph_area_h = max(ph_area_h, int(ah * 0.4))
    else:
        text_zone_h = 0
        ph_area_h = ah

    # 写真枠の分割
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
            "scaleX": scale, "scaleY": scale, "originX": "left", "originY": "top"
        })
        
    # テキストの自動サイズ調整と配置
    if full_text:
        ty = y0 + (ah - text_zone_h)
        # 💡 ここが新しい自動レイアウトロジックです。単一のマルチラインテキストとして扱う
        color = text_defs[0].get("fill", "#333333") if text_defs else "#333333"
        txt_img, fitted_size = prepare_text_image_fitting(
            full_text, 36, color, aw, text_zone_h, FONT_PATH
        )
        t_obj = {
            "type": "image", "src": f"data:image/png;base64,{pil_to_b64(txt_img)[22:]}",
            "originX": "left", "originY": "top"
        }
        # 中央配置
        t_obj["left"] = x0 + (aw - txt_img.width)//2
        # テキストエリアの下部中央付近に
        t_obj["top"] = ty + (text_zone_h - txt_img.height)//2
        
        objects.append(t_obj)
        st.info(f"🤖 自動レイアウト：文字全体がSafe Areaに収まるように、フォントサイズを {fitted_size}px に縮小しました。")
        
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
    selected_design = st.selectbox("デザイン切替", design_names, index=design_names.index(st.session_state.design))
    if selected_design != st.session_state.design:
        st.session_state.design = selected_design
        st.session_state.canvas_key += 1
        st.rerun()
    
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
                    "left": 150, "top": 150, "scaleX": 1.0, "scaleY": 1.0
                })
                st.session_state.processed_files.add(f.name)
            st.session_state.canvas_key += 1
            st.rerun()

    st.divider()
    st.header("✍️ コメント・色設定")
    # コメント入力：マルチラインテキストエリアに統合。長文に対応。
    msg = st.text_area("カードに入れる言葉（長文可）", "想い出をありがとう。")
    
    col1, col2 = st.columns(2)
    with col1:
        color_type = st.radio("色選択モード", ["代表的な色", "オリジナル"])
    with col2:
        if color_type == "代表的な色":
            selected_preset = st.selectbox("色リスト", list(COLOR_PRESETS.keys()))
            final_text_color = COLOR_PRESETS[selected_preset]
            st.markdown(f'<div style="width:30px;height:30px;background-color:{final_text_color};border:1px solid #ccc;border-radius:5px;"></div>', unsafe_allow_html=True)
        else:
            final_text_color = st.color_picker("カスタム色", "#333333")

    if st.button("文字を追加"):
        if msg:
            t_obj = {
                "type": "i-text", "text": msg, 
                "fill": final_text_color,
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

# --- キャンバス表示 (背景の枠を確実に表示) ---
bg_img, card_h, canvas_h = make_bg(st.session_state.design)

st.subheader("2. 写真・文字を配置してください")
# 💡 keyにcanvas_keyを含めることで、デザイン変更時にキャンバスを新品に交換し、背景を確実に更新します
canvas_result = st_canvas(
    fill_color="rgba(0,0,0,0)", background_image=bg_img,
    initial_drawing={"objects": st.session_state.canvas_objects},
    height=canvas_h, width=CANVAS_W, drawing_mode="transform",
    key=f"pro_final_v1_{st.session_state.canvas_key}",
)

# --- 保存 ---
st.divider()
if st.button("✅ 完成画像を確定する", type="primary", use_container_width=True):
    if canvas_result.image_data is not None:
        rgba = Image.fromarray(canvas_result.image_data.astype(np.uint8), "RGBA")
        merged = Image.alpha_composite(bg_img.convert("RGBA"), rgba)
        final_card = merged.crop((PADDING, PADDING, PADDING + CARD_W, PADDING + card_h)).convert("RGB")
        st.session_state.confirmed_img = final_card
        st.success("プレビューを生成しました。下から保存してください。")
        st.rerun()

if "confirmed_img" in st.session_state and st.session_state.confirmed_img:
    col1, col2 = st.columns([3, 1])
    with col1: st.image(st.session_state.confirmed_img, use_container_width=True)
    with col2:
        buf = io.BytesIO(); st.session_state.confirmed_img.save(buf, format="JPEG", quality=95)
        st.download_button("📥 JPEG保存", buf.getvalue(), "memorial_card.jpg", "image/jpeg", use_container_width=True)