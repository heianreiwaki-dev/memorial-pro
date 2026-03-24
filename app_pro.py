import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image, ImageDraw, ImageFont, ImageOps
import base64
import os
import io
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
# 定数
# ==========================================
CARD_W = 560
PADDING = 80
CANVAS_W = CARD_W + PADDING * 2
PHOTO_MAX_PX = 350
PHOTO_HQ_PX = 1200

# 💡 ネット公開用フォント設定（リポジトリ内のファイルを指定）
FONT_PATH = "msgothic.ttc"
FONT_MAP = {
    "ゴシック体": FONT_PATH,
    "明朝体": FONT_PATH,
    "サンセリフ": FONT_PATH,
}

# フォルダ確認
CARDS_DIR = "cards"
os.makedirs(CARDS_DIR, exist_ok=True)

def load_designs():
    exts = (".jpg", ".jpeg", ".png")
    files = sorted([f for f in os.listdir(CARDS_DIR) if f.lower().endswith(exts)])
    if not files: return {"（デフォルト）": None}
    return {os.path.splitext(f)[0]: os.path.join(CARDS_DIR, f) for f in files}

DESIGNS = load_designs()

# ==========================================
# ユーティリティ (脇さんのロジックを継承)
# ==========================================
def resize_pil(img, max_px):
    w, h = img.size
    if max(w, h) <= max_px: return img
    r = max_px / max(w, h)
    return img.resize((int(w*r), int(h*r)), Image.LANCZOS)

def pil_to_b64(img, quality=85):
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def get_font(style, size):
    path = FONT_MAP.get(style, FONT_PATH)
    try:
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.load_default()

def process_upload(file):
    pil = Image.open(file).convert("RGBA")
    c = resize_pil(pil, PHOTO_MAX_PX)
    h = resize_pil(pil, PHOTO_HQ_PX)
    return {
        "canvas_b64": pil_to_b64(c),
        "canvas_w": c.width, "canvas_h": c.height,
        "pid": f"p_{np.random.randint(10000)}"
    }

def make_bg(design):
    path = DESIGNS.get(design)
    if path and os.path.exists(path):
        bg = Image.open(path).convert("RGBA")
    else:
        bg = Image.new("RGBA", (560, 400), (240, 235, 220, 255))
    card_h = int(CARD_W * bg.height / bg.width)
    canvas_h = card_h + PADDING * 2
    canvas = Image.new("RGBA", (CANVAS_W, canvas_h), (210, 205, 200, 255))
    canvas.paste(bg.resize((CARD_W, card_h)), (PADDING, PADDING))
    return canvas, card_h, canvas_h

# --- 自動レイアウト計算 (脇さんのロジックをそのまま使用) ---
CARD_INNER_PAD = 36
GAP = 10
def auto_layout(photo_infos, text_objs, card_w, card_h):
    # (脇さんの提供されたauto_layout関数の内容をここに配置してください)
    # ※メッセージ制限のため、中身は省略していますが、脇さんのコードをそのまま貼れば動きます。
    return [] 

# ==========================================
# セッション初期化
# ==========================================
st.set_page_config(page_title="プロ・メモリアルカード", layout="wide")
st.title("🕯️ プロ・メモリアルカード (AIレイアウト版)")

if "canvas_objects" not in st.session_state:
    st.session_state.canvas_objects = []
    st.session_state.processed = {}
    st.session_state.photo_store = {}
    st.session_state.canvas_key = 0
    st.session_state.design = list(DESIGNS.keys())[0]

# --- メイン処理 ---
with st.sidebar:
    st.header("🖼️ 背景デザイン")
    design_names = list(DESIGNS.keys())
    selected_design = st.selectbox("デザイン切替", design_names)
    if selected_design != st.session_state.design:
        st.session_state.design = selected_design
        st.session_state.canvas_key += 1
        st.rerun()

    st.header("📷 写真追加")
    uploaded_files = st.file_uploader("写真を選択", accept_multiple_files=True)
    if uploaded_files:
        if st.button(f"{len(uploaded_files)}枚を反映"):
            for f in uploaded_files:
                if f.name not in st.session_state.processed:
                    info = process_upload(f)
                    st.session_state.canvas_objects.append({
                        "type": "image", "src": info["canvas_b64"],
                        "left": 100, "top": 100, "width": info["canvas_w"], "height": info["canvas_h"],
                        "scaleX": 1.0, "scaleY": 1.0
                    })
                    st.session_state.processed[f.name] = True
            st.session_state.canvas_key += 1
            st.rerun()

# キャンバス表示
bg_img, card_h, canvas_h = make_bg(st.session_state.design)
st_canvas(
    fill_color="rgba(0,0,0,0)",
    background_image=bg_img,
    initial_drawing={"objects": st.session_state.canvas_objects},
    height=canvas_h, width=CANVAS_W,
    drawing_mode="transform",
    key=f"canvas_pro_{st.session_state.canvas_key}",
)