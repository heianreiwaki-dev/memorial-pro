import streamlit as st
from streamlit_drawable_canvas import st_canvas
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps, ImageFilter
import io
import os
import base64
import numpy as np

# ==========================================
# 🚨 ネット公開用エラー回避パッチ
# ==========================================
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
FRAME_FILES = {"枠なし": None, "枠1 (シンプル)": "waku.png", "枠2 (装飾)": "waku2.png"}
PRESET_BG_COLORS = {"ホワイト ⚪": "#FFFFFF", "アイボリー 🍦": "#F5F5F0", "薄いグレー 🔘": "#F0F0F0", "セピア 📜": "#E0D0B0", "ブラック ⚫": "#000000"}
PRESET_TEXT_COLORS = {"漆黒 ⚫": "#000000", "濃いグレー 🔘": "#333333", "墨色 🔘": "#444444", "ホワイト ⚪": "#FFFFFF", "ダークブラウン 🪵": "#3D2B1F", "ゴールド風 🟡": "#B8860B"}
FONTS = {"ゴシック体 (現代的)": "msgothic.ttc", "明朝体 (厳か)": "msmincho.ttc"}

# デザイン上の Safe Area 定数 (カードの内側)
PADDING = 80 # 周囲の余白
CARD_INNER_PAD = 36 # デザイン枠の太さ目安
GAP = 12 # 自動レイアウトの余白

st.set_page_config(page_title="次世代メモリアル・エディタ", layout="wide")

# ==========================================
# 便利関数
# ==========================================
def get_image_base64_url(img):
    """💡 ネット環境で背景を表示させるため、Base64のURLに変換します"""
    buffered = io.BytesIO()
    # 透過がない背景台紙はJPEGにして軽量化します
    img.convert("RGB").save(buffered, format="JPEG", quality=90)
    encoded = base64.b64encode(buffered.getvalue()).decode()
    return f"data:image/jpeg;base64,{encoded}"

def prepare_text_image(text, size, color, target_w, f_path):
    """自動配置用のテキスト画像を作成"""
    font_full_path = os.path.join(os.path.dirname(__file__), f_path)
    try:
        font = ImageFont.truetype(font_full_path, size) if os.path.exists(font_full_path) else ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    # 測定用ダミー
    dummy_img = Image.new("RGBA", (int(target_w), 500))
    dummy_draw = ImageDraw.Draw(dummy_img)
    bbox = dummy_draw.multiline_textbbox((0, 0), text, font=font, align="center")
    tw, th = int(bbox[2] - bbox[0] + 10), int(bbox[3] - bbox[1] + 10)
    # 本番用透過画像
    txt_img = Image.new("RGBA", (max(tw, 10), max(th, 10)), (0, 0, 0, 0))
    txt_draw = ImageDraw.Draw(txt_img)
    txt_draw.multiline_text((tw//2, th//2), text, font=font, fill=color, anchor="mm", align="center")
    # Base64PNG (Canvasに画像として配置)
    buf = io.BytesIO()
    txt_img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), txt_img.width, txt_img.height

# --- 🤖 自動レイアウトロジック (重ならない・最大化実装版) ---
def auto_layout(photo_infos, text_defs, card_w, card_h):
    """
    💡 写真を重ならない範囲で極力大きく配置する「次世代自動レイアウト」
    """
    n = len(photo_infos)
    has_text = len(text_defs) > 0
    objects = []

    # ── 有効エリア（カード枠内側）──────────────────────────
    # デザイン枠目安(CARD_INNER_PAD=36px)の少し内側（+15px）を Safe Area と定義
    margin = CARD_INNER_PAD + 15 
    x0, y0 = PADDING + margin, PADDING + margin
    aw, ah = card_w - margin * 2, card_h - margin * 2

    # ── テキストエリアを下部に確保 ────────────────────────
    if has_text:
        # 文字数から高さを推定（フォントサイズx行数+余白）
        # ただし、最大 ah の30%までに制限。
        max_fs = max(t.get("fontSize", 30) for t in text_defs)
        text_lines = sum(t.get("text", "").count("\n") + 1 for t in text_objs)
        text_zone = (max_fs + 10) * text_lines + GAP * 2
        text_zone = min(text_zone, int(ah * 0.3))
    else:
        text_zone = 0

    # 写真エリア（上部）
    ph_area_h = ah - text_zone - (GAP if has_text else 0)
    
    # ── 写真の分割矩形を計算（タイミー風配置パターン） ──────────────────チ
    def split_grid(cols, rows, area_w, area_h, base_x, base_y):
        pw = (area_w - GAP * (cols - 1)) // cols
        ph = (area_h - GAP * (rows - 1)) // rows
        rects = []
        for r in range(rows):
            for c in range(cols):
                rects.append((base_x + c*(pw+GAP), base_y + r*(ph+GAP), pw, ph))
        return rects

    if n == 0:
        photo_rects = []
    elif n == 1:
        photo_rects = [(x0, y0, aw, ph_area_h)] # 全体
    elif n == 2:
        photo_rects = split_grid(2, 1, aw, ph_area_h, x0, y0) # 左右
    elif n == 3:
        # 左に大きく1枚、右に縦2枚 (重ならない範囲で最大化)
        pw_l = int(aw * 0.55) - GAP//2
        pw_r = aw - pw_l - GAP
        ph_r = (ph_area_h - GAP) // 2
        photo_rects = [
            (x0, y0, pw_l, ph_area_h),
            (x0+pw_l+GAP, y0, pw_r, ph_r),
            (x0+pw_l+GAP, y0+ph_r+GAP, pw_r, ph_r)
        ]
    elif n == 4:
        photo_rects = split_grid(2, 2, aw, ph_area_h, x0, y0) # 2x2
    else:
        # それ以上はグリッド配置 (極力大きくするため横3列固定)
        cols = 3
        rows = (n + cols - 1) // cols
        photo_rects = split_grid(cols, rows, aw, ph_area_h, x0, y0)
        
    # ── 写真オブジェクトを追加 ────────────────────
    for info, (rx, ry, rw, rh) in zip(photo_infos, photo_rects):
        p_img = info["pil"]
        ow, oh = p_img.size
        
        # 枠内で最大化（アスペクト比維持）
        scale = min(rw / ow, rh / oh)
        
        # 中央配置
        dw, dh = int(ow * scale), int(oh * scale)
        cx = rx + (rw - dw) // 2
        cy = ry + (rh - dh) // 2
        
        # キャンバスBase64は既に process_upload で作成済み（350pxサイズ）
        objects.append({
            "type": "image",
            "src": info["canvas_b64"],
            "left": cx, "top": cy,
            "width": ow, "height": oh,
            "scaleX": scale, "scaleY": scale,
            "angle": 0, "selectable": True, "lockUniScaling": False,
            "originX": "left", "originY": "top"
        })

    # ── テキストオブジェクトを追加（下部エリアの中央に配置）──────────────────────────
    if has_text:
        text_area_y = y0 + ph_area_h + GAP # テキストエリア開始Y
        # 自動配置ではテキスト全体を中央寄せに計算
        for t in text_defs:
            fs = t.get("fontSize", 30)
            obj = dict(t)
            # Safe Area内に収める
            obj["left"] = x0 + (aw - t.get("objWidth", 100))//2
            obj["top"] = text_area_y + GAP
            objects.append(obj)
            text_area_y += fs + 10 # 簡易的な行間

    return objects

# ==========================================
# セッション初期化
# ==========================================
st.set_page_config(page_title="次世代メモリアル・エディタ", layout="wide")

# セッション状態をひとまとめに管理
if "app_state" not in st.session_state:
    st.session_state.app_state = {
        "canvas_objects": [],
        "photo_store": [],
        "canvas_key": 0,
        "mode": "手動",
        "text_objs": [],
        "processed_files": set(),
        "confirmed_img": None
    }
S = st.session_state.app_state

# pending → canvas_objects へ反映
if "pending_photos" in st.session_state and st.session_state.pending_photos:
    S["canvas_objects"].extend(st.session_state.pending_photos)
    st.session_state.pending_photos = []
    S["canvas_key"] += 1

# ==========================================
# 1. サイドバー設定
# ==========================================
with st.sidebar:
    st.header("📋 基本設定")
    selected_size = st.selectbox("出力サイズ", list(PAPER_SIZES.keys()))
    W, H = PAPER_SIZES[selected_size]
    
    selected_frame_key = st.radio("装飾枠の選択", list(FRAME_FILES.keys()))
    frame_path = FRAME_FILES[selected_frame_key]
    
    # セピアを選んだ時にプレビューで確認できるようにします
    bg_preset = st.selectbox("背景色", list(PRESET_BG_COLORS.keys()), index=3 if "app_state" not in st.session_state else 3)
    bg_color = PRESET_BG_COLORS[bg_preset]

    st.header("📸 写真の設定")
    uploaded_files = st.file_uploader("写真をアップロード (複数可)", accept_multiple_files=True)
    if uploaded_files:
        new_files = [f for f in uploaded_files if f.name not in S["processed_files"]]
        if new_fs_len := len(new_files):
            if st.button(f"🖼️ {new_fs_len}枚を追加"):
                pending = []
                for file in new_files:
                    pil = Image.open(file).convert("RGBA")
                    pid = f"photo_{len(S['processed_files'])}"
                    # 測定用高解像度
                    pil_h = resize_pil(pil, 1200)
                    # Canvas表示用軽量
                    pil_c = resize_pil(pil, 350)
                    buffered = io.BytesIO()
                    pil_c.save(buffered, format="PNG")
                    b64 = "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()
                    
                    S["photo_store"].append({"pil": pil_h, "canvas_b64": b64, "pid": pid})
                    
                    pending.append({
                        "type": "image", "src": b64,
                        "left": W//2, "top": H//2, "angle": 0, "scaleX": 1.0, "scaleY": 1.0,
                        "lockUniScaling": False, "_photo_id": pid
                    })
                    S["processed_files"].add(file.name)
                
                # AI自動配置モードなら、そのままロジックへ
                if S["mode"] == "AIで自動レイアウト":
                    _, card_h_tmp, _ = make_bg(bg_color, selected_size, frame_path)
                    new_objs = auto_layout(S["photo_store"], S["text_objs"], W, card_h_tmp)
                    S["canvas_objects"] = new_objs
                else:
                    S["canvas_objects"].extend(pending)
                    
                S["canvas_key"] += 1
                st.rerun()

    st.header("✍️ 文字の設定")
    user_text = st.text_input("本文", value="想い出をありがとう。")
    t_preset = st.selectbox("文字色プリセット", list(PRESET_TEXT_COLORS.keys()), index=1)
    t_color = PRESET_TEXT_COLORS[t_preset]

    if st.button("文字を追加"):
        if user_text:
            t_obj = {
                "type": "i-text", "text": user_text, "fill": t_color, "fontSize": 36, "fontFamily": "ゴシック体",
                "left": W//2, "top": H//2 + 200, "angle": 0, "scaleX": 1.0, "scaleY": 1.0,
            }
            if S["mode"] == "AIで自動レイアウト":
                 # AIモードでは text_objs に登録してAIに配置させる
                S["text_objs"].append(t_obj)
                _, card_h_tmp, _ = make_bg(bg_color, selected_size, frame_path)
                new_objs = auto_layout(S["photo_store"], S["text_objs"], W, card_h_tmp)
                S["canvas_objects"] = new_objs
            else:
                S["canvas_objects"].append(t_obj)
            
            S["canvas_key"] += 1
            st.rerun()

    st.divider()
    # 手動・自動の切り替え
    S["mode"] = st.radio("レイアウトモード", ["手動 (自由配置)", "AIで自動レイアウト"])
    if S["mode"] == "AIで自動レイアウト":
        if st.button("🤖 AI自動配置を実行", type="primary"):
            if not S["photo_store"] and not S["text_objs"]:
                st.warning("写真または文字を追加してください。")
            else:
                _, card_h_tmp, _ = make_bg(bg_color, selected_size, frame_path)
                new_objs = auto_layout(S["photo_store"], S["text_objs"], W, card_h_tmp)
                S["canvas_objects"] = new_objs
                S["canvas_key"] += 1
                st.rerun()

    if st.button("🔄 全部リセット", type="secondary"):
        for k in ["canvas_objects", "photo_store", "text_objs", "processed_files"]: S[k] = set() if k == "processed_files" else []
        S["canvas_key"] += 1
        S["confirmed_img"] = None
        st.rerun()

# ==========================================
# 2. メイン画面 (背景表示・合成)
# ==========================================
def make_bg(color, size_key, f_path):
    """背景と枠を合成した画像を作成します。"""
    W, H = PAPER_SIZES[size_key]
    base_paper = Image.new("RGBA", (int(W), int(H)), color)
    if f_path:
        waku_path = os.path.join(os.path.dirname(__file__), f_path)
        if os.path.exists(waku_path):
            waku = Image.open(waku_path).convert("RGBA").resize((int(W), int(H)))
            base_paper = Image.alpha_composite(base_paper, waku)
    return base_paper, int(H), int(W)

# 背景台紙を作成
bg_img, canvas_h, canvas_w = make_bg(bg_color, selected_size, frame_path)

st.subheader("2. 写真・文字を配置してください")
if S["mode"] == "手動 (自由配置)":
    st.caption("💡 ドラッグ: 移動　□: 拡大縮小　○: 回転　ダブルクリック: テキスト編集")
else:
    st.caption("💡 自動レイアウト適用後、手動で微調整できます")

# --- キャンバス表示 (不具合修正・Base64URLによる背景表示) ---
canvas_result = st_canvas(
    fill_color="rgba(0,0,0,0)",
    background_image=get_image_base64_url(bg_img), # 💡 修正箇所：Base64URLに変換して渡す
    initial_drawing={"objects": S["canvas_objects"]},
    update_streamlit=True,
    height=canvas_h, width=canvas_w,
    drawing_mode="transform",
    key=f"pro_final_v6_{selected_size}_{S['canvas_key']}", # 💡 keyで更新を強制
)

# ==========================================
# 3. 完成確定・保存 (PDF対応版)
# ==========================================
st.divider()
if st.button("✨ デザインを確定する", type="primary", use_container_width=True):
    if canvas_result.image_data is not None:
        # 手動調整後の配置を保存
        if canvas_result.json_data:
            objs = canvas_result.json_data.get("objects", [])
            S["canvas_objects"] = objs # 確定後の配置を保存
            S["canvas_key"] += 1

        # PIL画像へ変換
        arr = canvas_result.image_data.astype('uint8')
        final_layer = Image.fromarray(arr, 'RGBA')
        
        # 背景（bg_img）とユーザー配置（final_layer）を合成
        complete_page = Image.alpha_composite(bg_img.convert("RGBA"), final_layer)
        S["confirmed_img"] = complete_page.convert("RGB") # 完成画像を保存
        st.success("プレビューを生成しました。下から保存してください。")
        st.rerun()

# 確定後エリア
if S["confirmed_img"]:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.image(S["confirmed_img"], caption="完成プレビュー", use_container_width=True)
    with col2:
        st.write("#### 💾 保存")
        
        # JPEG保存
        buf_j = io.BytesIO()
        S["confirmed_img"].save(buf_j, format="JPEG", quality=95)
        st.download_button("📥 通常保存 (JPEG)", buf_j.getvalue(), "memorial.jpg", "image/jpeg", use_container_width=True)
        
        # 💡 PDF保存機能を追加
        buf_p = io.BytesIO()
        # PILはRGB画像をそのままPDFとして保存可能。解像度を100に指定して高画質に。
        S["confirmed_img"].save(buf_p, format="PDF", resolution=100.0)
        st.download_button("📥 高画質保存 (PDF)", buf_p.getvalue(), "memorial.pdf", "application/pdf", use_container_width=True)

else:
    st.info("「✨ デザインを確定する」を押すと、ここにプレビューと保存ボタンが表示されます。")