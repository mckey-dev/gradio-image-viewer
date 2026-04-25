# ================================================================================
# Gradio Image Viewer: フォルダ選択・ページング対応の画像ギャラリー（クリックで全画面表示）。
# pip install -r requirements.txt && python app.py
# ================================================================================

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from config_store import ViewerConfigStore
from lightbox import attach_lightbox, lightbox_css

import gradio as gr
from PIL import Image, UnidentifiedImageError

_DIR = Path(__file__).resolve().parent

_IMAGE_SUFFIXES = frozenset(
    x.lower() for x in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif")
)
_PARENT_DIR_OPTION = ".."
_DEFAULT_PAGE_SIZE = 10
_SCROLLBAR_RESERVE_PX = 28
_INITIAL_INTRO = "フォルダを選択して表示ボタンを押してください。"
_THUMB_SIZE_PX = 128
_THUMB_JPEG_QUALITY = 82
_THUMB_CACHE_DIR = Path(tempfile.gettempdir()) / "gradio-image-viewer-thumbs"
# config.json の保存先（アプリ配置ディレクトリ直下）。
_CONFIG_PATH = _DIR / "config.json"
_CONFIG_STORE = ViewerConfigStore(
    _CONFIG_PATH,
    default_directory=_DIR,
    default_page_size=_DEFAULT_PAGE_SIZE,
)
# 起動時に前回設定を読み込む。
_INITIAL_CONFIG = _CONFIG_STORE.load()

# ================================================================================
# 関数の概要: ディレクトリ直下のサブフォルダ名を名前順で列挙する（UI のフォルダ選択用）。
# 引数: directory（探索対象ディレクトリ）。
# 戻り値: サブフォルダ名のリスト（名前順）。
# ================================================================================
def _list_subdirectories(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    out: list[Path] = []
    for p in directory.iterdir():
        if not p.is_dir() or p.name.startswith("."):
            continue
        out.append(p)
    return [x.name for x in sorted(out, key=lambda x: x.name.lower())]


# ================================================================================
# 関数の概要: ディレクトリ直下の画像ファイルを名前順で列挙する（固定ファイル名に依存しない）。
# 引数: directory（探索対象ディレクトリ）。
# 戻り値: 画像ファイルの絶対パス文字列リスト（名前順）。
# ================================================================================
def _list_image_paths(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    out: list[Path] = []
    for p in directory.iterdir():
        if not p.is_file() or p.name.startswith("."):
            continue
        if p.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        out.append(p)
    return [str(x.resolve()) for x in sorted(out, key=lambda x: x.name.lower())]


# ================================================================================
# 関数の概要: フォルダ選択ドロップダウンの選択肢を生成する（先頭に ".." を付与）。
# 引数: directory（基準ディレクトリ）。
# 戻り値: ドロップダウン選択肢のリスト。
# ================================================================================
def _build_folder_choices(directory: Path) -> list[str]:
    return [_PARENT_DIR_OPTION, *_list_subdirectories(directory)]


# ================================================================================
# 関数の概要: 画像有無に応じた説明文を生成する。
# 引数: image_count（画像数）。
# 戻り値: 表示用 Markdown 文字列。
# ================================================================================
def _build_intro_markdown(image_count: int) -> str:
    return (
        "サムネイルをクリックすると全画面ビューアが開きます。閉じるは × または Escape。"
        if image_count > 0
        else " **カレントフォルダに画像ファイルは存在しません。**"
    )


# ================================================================================
# 関数の概要: ドロップダウン選択に応じて移動先フォルダを解決し、UI 更新情報を返す。
# 引数: image_files（全画像パス）、page（現在ページ）、page_size（1ページ件数）。
# 戻り値: ページング後画像リスト、補正後ページ、最大ページ。
# ================================================================================
def _paginate_image_files(
    image_files: list[str], page: int, page_size: int | float
) -> tuple[list[str], int, int]:
    normalized_page_size = _normalize_page_size(page_size)
    image_count = len(image_files)
    max_page = max((image_count - 1) // normalized_page_size + 1, 1)
    normalized_page = min(max(page, 1), max_page)
    start = (normalized_page - 1) * normalized_page_size
    end = start + normalized_page_size
    return image_files[start:end], normalized_page, max_page


# ================================================================================
# 関数の概要: 表示件数入力を安全に整数化する。
# 引数: page_size（入力された表示件数）。
# 戻り値: 1 以上の正規化済みページ件数。
# ================================================================================
def _normalize_page_size(page_size: int | float | None) -> int:
    try:
        if page_size is None:
            return _DEFAULT_PAGE_SIZE
        return max(int(page_size), 1)
    except (TypeError, ValueError):
        return _DEFAULT_PAGE_SIZE


# ================================================================================
# 関数の概要: ページ表示ラベル文字列を生成する。
# 引数: current_page（現在ページ）、max_page（最大ページ）。
# 戻り値: "現在ページ / 最大ページ" 形式の文字列。
# ================================================================================
def _build_page_label(current_page: int, max_page: int) -> str:
    return f"{current_page} / {max_page}"


# ================================================================================
# 関数の概要: 画像ファイルに対応するサムネイルキャッシュパスを生成する。
# 引数: source_image_path（元画像パス）。
# 戻り値: サムネイル保存先パス。
# ================================================================================
def _build_thumbnail_path(source_image_path: Path) -> Path:
    source_stat = source_image_path.stat()
    cache_key = (
        f"{source_image_path.resolve()}|{source_stat.st_mtime_ns}|"
        f"{source_stat.st_size}|{_THUMB_SIZE_PX}|{_THUMB_JPEG_QUALITY}"
    )
    file_hash = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()
    return _THUMB_CACHE_DIR / f"{file_hash}.jpg"


# ================================================================================
# 関数の概要: 画像1枚ぶんの軽量サムネイルを生成し、表示用パスを返す。
# 引数: source_image_path（元画像パス文字列）。
# 戻り値: サムネイル画像パス（失敗時は元画像パス）。
# ================================================================================
def _get_thumbnail_path(source_image_path: str) -> str:
    source_path = Path(source_image_path)
    if not source_path.is_file():
        return source_image_path

    try:
        _THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        thumbnail_path = _build_thumbnail_path(source_path)
    except OSError:
        return source_image_path

    if thumbnail_path.is_file():
        return str(thumbnail_path)

    try:
        with Image.open(source_path) as img:
            if img.mode in ("RGBA", "LA") or (
                img.mode == "P" and "transparency" in img.info
            ):
                # 透過 PNG は白背景へ合成して JPEG 化する。
                rgba = img.convert("RGBA")
                background = Image.new("RGB", rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.getchannel("A"))
                thumbnail = background
            else:
                thumbnail = img.convert("RGB")

            thumbnail.thumbnail((_THUMB_SIZE_PX, _THUMB_SIZE_PX), Image.LANCZOS)
            thumbnail.save(
                thumbnail_path,
                format="JPEG",
                quality=_THUMB_JPEG_QUALITY,
                optimize=True,
            )
        return str(thumbnail_path)
    except (OSError, UnidentifiedImageError, ValueError):
        return source_image_path


# ================================================================================
# 関数の概要: ページ表示する画像一覧をサムネイル化して返す。
# 引数: image_paths（元画像パス一覧）。
# 戻り値: 表示用サムネイルのファイルパス一覧。
# ================================================================================
def _build_gallery_thumbnail_paths(image_paths: list[str]) -> list[str]:
    thumbnail_paths: list[str] = []
    for image_path in image_paths:
        thumbnail_path = _get_thumbnail_path(image_path)
        thumbnail_paths.append(thumbnail_path)
    return thumbnail_paths


# ================================================================================
# 関数の概要: 指定ページのギャラリー表示更新情報を生成する。
# 引数: image_files（全画像パス）、page（表示ページ）、page_size（1ページ件数）。
# 戻り値: ギャラリー更新、ページラベル、前/次ボタン更新、補正後ページ。
# ================================================================================
def _build_page_updates(
    image_files: list[str], page: int, page_size: int | float
) -> tuple[dict, str, dict, dict, int, str]:
    paged_files, normalized_page, max_page = _paginate_image_files(
        image_files, page, page_size
    )
    paged_thumbnail_files = _build_gallery_thumbnail_paths(paged_files)
    return (
        gr.update(value=paged_thumbnail_files, columns=max(_DEFAULT_PAGE_SIZE, 1)),
        _build_page_label(normalized_page, max_page),
        gr.update(interactive=normalized_page > 1),
        gr.update(interactive=normalized_page < max_page),
        normalized_page,
        json.dumps(paged_files, ensure_ascii=False),
    )


# ================================================================================
# 関数の概要: ドロップダウン選択に応じて移動先ディレクトリを解決する。
# 引数: selected_folder（選択値）、current_directory（現在ディレクトリ）。
# 戻り値: 解決後ディレクトリ。
# ================================================================================
def _resolve_next_directory(selected_folder: str | None, current_directory: Path) -> Path:
    if selected_folder == _PARENT_DIR_OPTION:
        return current_directory.parent
    if selected_folder:
        selected_path = Path(selected_folder).expanduser()
        candidate = (
            selected_path if selected_path.is_absolute() else current_directory / selected_path
        )
        if candidate.is_dir():
            return candidate.resolve()
    return current_directory


# ================================================================================
# 関数の概要: ドロップダウン選択に応じて移動先フォルダを解決し、UI 更新情報を返す。
# 引数: selected_folder（選択値）、current_directory_str（現在ディレクトリ文字列）、
#       page_size（現在の表示件数）。
# 戻り値: ドロップダウン更新、現在ディレクトリ文字列。
# ================================================================================
def _on_folder_change(
    selected_folder: str | None, current_directory_str: str, page_size: int | float
) -> tuple[dict, str]:
    current_directory = Path(current_directory_str)
    next_directory = _resolve_next_directory(selected_folder, current_directory)

    next_choices = _build_folder_choices(next_directory)
    _CONFIG_STORE.save(
        last_folder_path=str(next_directory),
        last_page_size=_normalize_page_size(page_size),
    )

    return (
        gr.update(choices=next_choices, value=str(next_directory)),
        str(next_directory),
    )


# ================================================================================
# 関数の概要: 表示ボタン押下時に現在フォルダからギャラリー表示を更新する。
# 引数: current_directory_str（現在ディレクトリ文字列）、page_size（1ページ件数）。
# 戻り値: 説明文、ギャラリー、全画像、ページ表示、前/次ボタン、現在ページ。
# ================================================================================
def _on_show_gallery(
    current_directory_str: str, page_size: int | float
) -> tuple[str, dict, list[str], str, dict, dict, int, str]:
    current_directory = Path(current_directory_str)
    normalized_page_size = _normalize_page_size(page_size)
    gallery_files = _list_image_paths(current_directory)
    gallery_count = len(gallery_files)
    (
        gallery_update,
        page_label,
        prev_button_update,
        next_button_update,
        current_page,
        paged_originals_json,
    ) = _build_page_updates(gallery_files, page=1, page_size=normalized_page_size)
    _CONFIG_STORE.save(
        last_folder_path=str(current_directory),
        last_page_size=normalized_page_size,
    )
    return (
        _build_intro_markdown(gallery_count),
        gallery_update,
        gallery_files,
        page_label,
        prev_button_update,
        next_button_update,
        current_page,
        paged_originals_json,
    )


# ================================================================================
# 関数の概要: 前ページへ移動するための UI 更新情報を返す。
# 引数: image_files（全画像パス）、current_page（現在ページ）、page_size（1ページ件数）。
# 戻り値: ギャラリー、ページ表示、前/次ボタン、現在ページ。
# ================================================================================
def _on_prev_page(
    image_files: list[str], current_page: int, page_size: int | float
) -> tuple[dict, str, dict, dict, int, str]:
    return _build_page_updates(image_files, page=current_page - 1, page_size=page_size)


# ================================================================================
# 関数の概要: 次ページへ移動するための UI 更新情報を返す。
# 引数: image_files（全画像パス）、current_page（現在ページ）、page_size（1ページ件数）。
# 戻り値: ギャラリー、ページ表示、前/次ボタン、現在ページ。
# ================================================================================
def _on_next_page(
    image_files: list[str], current_page: int, page_size: int | float
) -> tuple[dict, str, dict, dict, int, str]:
    return _build_page_updates(image_files, page=current_page + 1, page_size=page_size)


# ================================================================================
# 関数の概要: 表示件数変更時にページを先頭へ戻して UI を更新する。
# 引数: page_size（1ページ件数）、image_files（全画像パス）、
#       current_directory_str（現在ディレクトリ文字列）。
# 戻り値: ギャラリー、ページ表示、前/次ボタン、現在ページ。
# ================================================================================
def _on_page_size_change(
    page_size: int | float, image_files: list[str], current_directory_str: str
) -> tuple[dict, str, dict, dict, int, str]:
    normalized_page_size = _normalize_page_size(page_size)
    _CONFIG_STORE.save(
        last_folder_path=current_directory_str,
        last_page_size=normalized_page_size,
    )
    return _build_page_updates(image_files, page=1, page_size=normalized_page_size)


_initial_directory = Path(_INITIAL_CONFIG.last_folder_path)
_initial_page_size = _normalize_page_size(_INITIAL_CONFIG.last_page_size)
_gallery_files = _list_image_paths(_initial_directory)
_gallery_count = len(_gallery_files)
_folder_options = _build_folder_choices(_initial_directory)
_MD_INTRO = _INITIAL_INTRO
_INITIAL_PAGE_LABEL_DISPLAY = ""
(
    _initial_gallery_update,
    _initial_page_label,
    _initial_prev_update,
    _initial_next_update,
    _initial_current_page,
    _initial_page_originals_json,
) = _build_page_updates(_gallery_files, page=1, page_size=_initial_page_size)

# ギャラリー枠の高さ（レイアウト内で可変）。
_GALLERY_HEIGHT_CSS = "100%"
# 1 マス内 img の縦上限（ギャラリー内に収める）。
_THUMB_MAX_CSS = "100%"

# Gradio 3.41 Gallery（allow_preview=False）: .grid-container 内が button.thumbnail-item.thumbnail-lg > img。
# 縦長画像でセルが伸びてサムネ内スクロールが出るのを防ぎ、枠内に全体を縮小表示する。
_GALLERY_GRID_CSS = f"""
#gradio_image_viewer_layout {{
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: visible;
}}
#gradio_image_viewer_gallery_area {{
    flex: 0 0 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    height: var(--image-viewer-gallery-height, auto);
}}
#gradio_image_viewer {{
    flex: 0 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow-x: auto;
    overflow-y: auto;
}}
#gradio_image_viewer .grid-wrap {{
    flex: 0 1 auto;
    min-height: 0;
    overflow-x: auto;
    overflow-y: auto;
    scrollbar-gutter: stable both-edges;
    scrollbar-width: thin;
    height: auto;
    max-height: none;
    padding: 0 0 {_SCROLLBAR_RESERVE_PX}px 0;
    box-sizing: border-box;
}}
#gradio_image_viewer .grid-container {{
    display: flex !important;
    flex-wrap: wrap !important;
    justify-content: flex-start;
    align-items: flex-start;
    column-gap: 0.5rem;
    row-gap: 0;
    overflow-y: visible;
    height: auto;
    max-height: none;
    padding: 0.35rem 0;
    margin: 0 !important;
    box-sizing: border-box;
}}
#gradio_image_viewer button.thumbnail-item.thumbnail-lg {{
    min-height: {_THUMB_SIZE_PX}px;
    width: {_THUMB_SIZE_PX}px;
    height: {_THUMB_SIZE_PX}px;
    min-width: {_THUMB_SIZE_PX}px;
    max-width: {_THUMB_SIZE_PX}px;
    max-height: {_THUMB_SIZE_PX}px;
    flex: 0 0 {_THUMB_SIZE_PX}px;
    aspect-ratio: 1;
    flex-shrink: 0;
    overflow: hidden;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    margin: 0 !important;
}}
#gradio_image_viewer button.thumbnail-item.thumbnail-lg img {{
    flex: 0 1 auto;
    max-width: 100%;
    max-height: 100%;
    width: auto !important;
    height: auto !important;
    object-fit: contain !important;
}}
#gradio_image_viewer_controls_row {{
    align-items: center;
    flex-wrap: nowrap !important;
    justify-content: flex-start;
    gap: 0.5rem;
    overflow-x: auto;
}}
#gradio_image_viewer_page_label {{
    width: 10ch;
    min-width: 10ch;
    max-width: 10ch;
}}
#gradio_image_viewer_page_label input {{
    text-align: center;
    font-weight: 700;
}}
#gradio_image_viewer_nav_frame {{
    flex: 0 0 auto !important;
    width: 28rem;
    min-width: 28rem;
    border: 1px solid var(--border-color-primary, #d9d9e3);
    border-radius: 8px;
    padding: 0.25rem 0.4rem;
    background: var(--block-background-fill, transparent);
}}
#gradio_image_viewer_nav_inner {{
    display: flex !important;
    flex-wrap: nowrap !important;
    align-items: center;
    justify-content: center;
    gap: 0.4rem;
}}
#gradio_image_viewer_page_size,
#gradio_image_viewer_show_button {{
    flex: 0 0 auto !important;
}}
"""

with gr.Blocks(title="Gradio Image Viewer", css=lightbox_css() + _GALLERY_GRID_CSS) as demo:
    with gr.Column(elem_id="gradio_image_viewer_layout"):
        gr.Markdown("# Gradio Image Viewer")
        _current_directory = gr.State(str(_initial_directory))
        _all_gallery_files = gr.State(_gallery_files)
        _current_page = gr.State(_initial_current_page)
        _page_originals_json = gr.Textbox(
            value=_initial_page_originals_json,
            visible=False,
            elem_id="gradio_image_viewer_originals",
        )
        _folder_dropdown = gr.Dropdown(
            choices=_folder_options,
            value=str(_initial_directory),
            label="フォルダ選択",
            allow_custom_value=True,
            interactive=True,
        )
        with gr.Row(elem_id="gradio_image_viewer_controls_row"):
            _page_size = gr.Number(
                value=_initial_page_size,
                label="表示件数",
                precision=0,
                minimum=1,
                scale=0,
                min_width=120,
                elem_id="gradio_image_viewer_page_size",
            )
            _show_button = gr.Button(
                "表示",
                elem_id="gradio_image_viewer_show_button",
                scale=0,
                min_width=120,
            )
            with gr.Group(elem_id="gradio_image_viewer_nav_frame"):
                with gr.Row(elem_id="gradio_image_viewer_nav_inner"):
                    _prev_page_button = gr.Button(
                        "前ページ",
                        interactive=_initial_prev_update["interactive"],
                        scale=0,
                        min_width=100,
                    )
                    _page_label = gr.Textbox(
                        value=_INITIAL_PAGE_LABEL_DISPLAY,
                        elem_id="gradio_image_viewer_page_label",
                        show_label=False,
                        scale=0,
                        min_width=90,
                        interactive=False,
                        max_lines=1,
                    )
                    _next_page_button = gr.Button(
                        "次ページ",
                        interactive=_initial_next_update["interactive"],
                        scale=0,
                        min_width=100,
                    )
        _intro_markdown = gr.Markdown(_MD_INTRO)
        with gr.Column(elem_id="gradio_image_viewer_gallery_area"):
            _gallery = gr.Gallery(
                value=[],
                label="ギャラリー",
                show_label=False,
                elem_id="gradio_image_viewer",
                columns=max(_DEFAULT_PAGE_SIZE, 1),
                height=_GALLERY_HEIGHT_CSS,
                # マス内に全体が収まるよう縮小（はみ出しはレターボックス）。 cover なら枠を埋めてトリミング。
                object_fit="contain",
                allow_preview=False,
                show_download_button=True,
            )
    _folder_dropdown.change(
        _on_folder_change,
        inputs=[_folder_dropdown, _current_directory, _page_size],
        outputs=[_folder_dropdown, _current_directory],
    )
    _show_button.click(
        _on_show_gallery,
        inputs=[_current_directory, _page_size],
        outputs=[
            _intro_markdown,
            _gallery,
            _all_gallery_files,
            _page_label,
            _prev_page_button,
            _next_page_button,
            _current_page,
            _page_originals_json,
        ],
    )
    _prev_page_button.click(
        _on_prev_page,
        inputs=[_all_gallery_files, _current_page, _page_size],
        outputs=[
            _gallery,
            _page_label,
            _prev_page_button,
            _next_page_button,
            _current_page,
            _page_originals_json,
        ],
    )
    _next_page_button.click(
        _on_next_page,
        inputs=[_all_gallery_files, _current_page, _page_size],
        outputs=[
            _gallery,
            _page_label,
            _prev_page_button,
            _next_page_button,
            _current_page,
            _page_originals_json,
        ],
    )
    _page_size.change(
        _on_page_size_change,
        inputs=[_page_size, _all_gallery_files, _current_directory],
        outputs=[
            _gallery,
            _page_label,
            _prev_page_button,
            _next_page_button,
            _current_page,
            _page_originals_json,
        ],
    )
    demo.load(
        None,
        inputs=None,
        outputs=None,
        _js="""
() => {
  const RESERVE = 16;
  const MIN_HEIGHT = 120;
  const layout = document.getElementById("gradio_image_viewer_layout");
  const galleryArea = document.getElementById("gradio_image_viewer_gallery_area");
  if (!layout || !galleryArea) return [];

  const getBottomLimit = () => {
    const footer =
      document.querySelector("footer") ||
      document.querySelector(".footer") ||
      document.querySelector(".gradio-footer");
    if (!footer) return window.innerHeight;
    const rect = footer.getBoundingClientRect();
    if (rect.top <= 0) return window.innerHeight;
    return Math.min(rect.top, window.innerHeight);
  };

  const getGalleryRoot = () => document.getElementById("gradio_image_viewer");
  const getGridWrap = () => {
    const root = getGalleryRoot();
    if (!root) return null;
    return root.querySelector(".grid-wrap");
  };

  const applyGalleryHeight = () => {
    const top = galleryArea.getBoundingClientRect().top;
    const bottomLimit = getBottomLimit();
    const maxHeight = Math.max(bottomLimit - top - RESERVE, MIN_HEIGHT);

    const gridWrap = getGridWrap();
    let contentHeight = MIN_HEIGHT;
    if (gridWrap) {
      const style = window.getComputedStyle(gridWrap);
      const padTop = parseFloat(style.paddingTop || "0") || 0;
      const padBottom = parseFloat(style.paddingBottom || "0") || 0;
      contentHeight = Math.ceil(gridWrap.scrollHeight + padTop + padBottom);
    }

    const nextHeight = Math.min(Math.max(contentHeight, MIN_HEIGHT), maxHeight);
    galleryArea.style.setProperty("--image-viewer-gallery-height", `${nextHeight}px`);
  };

  let scheduled = false;
  const scheduleApply = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      applyGalleryHeight();
    });
  };

  applyGalleryHeight();
  window.addEventListener("resize", scheduleApply);
  const obs = new MutationObserver(scheduleApply);
  obs.observe(layout, { childList: true, subtree: true, attributes: true });

  const root = getGalleryRoot();
  if (root) {
    const rootObs = new MutationObserver(scheduleApply);
    rootObs.observe(root, { childList: true, subtree: true, attributes: true });
  }

  const gridWrap = getGridWrap();
  if (gridWrap && typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(scheduleApply);
    ro.observe(gridWrap);
  }

  return [];
}
""",
    )
    attach_lightbox(demo, "gradio_image_viewer")

if __name__ == "__main__":
    # share 公開時に /file=absolute_path を使うため、参照元ディレクトリを許可する。
    # 画像フォルダは運用上さまざまな絶対パスを取りうるため、ルート配下を許可する。
    demo.launch(share=True, allowed_paths=["/"])
