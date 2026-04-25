# ================================================================================
# Gradio Image Viewer: フォルダ選択・ページング対応の画像ギャラリー（クリックで全画面表示）。
# pip install -r requirements.txt && python app.py
# ================================================================================

from __future__ import annotations

from pathlib import Path

from lightbox import attach_lightbox, lightbox_css

import gradio as gr

_DIR = Path(__file__).resolve().parent

_IMAGE_SUFFIXES = frozenset(
    x.lower() for x in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif")
)
_PARENT_DIR_OPTION = ".."
_DEFAULT_PAGE_SIZE = 10
_SCROLLBAR_RESERVE_PX = 28
_INITIAL_INTRO = "フォルダを選択して表示ボタンを押してください。"

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
# 関数の概要: 指定ページのギャラリー表示更新情報を生成する。
# 引数: image_files（全画像パス）、page（表示ページ）、page_size（1ページ件数）。
# 戻り値: ギャラリー更新、ページラベル、前/次ボタン更新、補正後ページ。
# ================================================================================
def _build_page_updates(
    image_files: list[str], page: int, page_size: int | float
) -> tuple[dict, str, dict, dict, int]:
    paged_files, normalized_page, max_page = _paginate_image_files(
        image_files, page, page_size
    )
    return (
        gr.update(value=paged_files, columns=max(len(paged_files), 1)),
        _build_page_label(normalized_page, max_page),
        gr.update(interactive=normalized_page > 1),
        gr.update(interactive=normalized_page < max_page),
        normalized_page,
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
# 引数: selected_folder（選択値）、current_directory_str（現在ディレクトリ文字列）。
# 戻り値: ドロップダウン更新、現在ディレクトリ文字列。
# ================================================================================
def _on_folder_change(
    selected_folder: str | None, current_directory_str: str
) -> tuple[dict, str]:
    current_directory = Path(current_directory_str)
    next_directory = _resolve_next_directory(selected_folder, current_directory)

    next_choices = _build_folder_choices(next_directory)

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
) -> tuple[str, dict, list[str], str, dict, dict, int]:
    current_directory = Path(current_directory_str)
    gallery_files = _list_image_paths(current_directory)
    gallery_count = len(gallery_files)
    (
        gallery_update,
        page_label,
        prev_button_update,
        next_button_update,
        current_page,
    ) = _build_page_updates(gallery_files, page=1, page_size=page_size)
    return (
        _build_intro_markdown(gallery_count),
        gallery_update,
        gallery_files,
        page_label,
        prev_button_update,
        next_button_update,
        current_page,
    )


# ================================================================================
# 関数の概要: 前ページへ移動するための UI 更新情報を返す。
# 引数: image_files（全画像パス）、current_page（現在ページ）、page_size（1ページ件数）。
# 戻り値: ギャラリー、ページ表示、前/次ボタン、現在ページ。
# ================================================================================
def _on_prev_page(
    image_files: list[str], current_page: int, page_size: int | float
) -> tuple[dict, str, dict, dict, int]:
    return _build_page_updates(image_files, page=current_page - 1, page_size=page_size)


# ================================================================================
# 関数の概要: 次ページへ移動するための UI 更新情報を返す。
# 引数: image_files（全画像パス）、current_page（現在ページ）、page_size（1ページ件数）。
# 戻り値: ギャラリー、ページ表示、前/次ボタン、現在ページ。
# ================================================================================
def _on_next_page(
    image_files: list[str], current_page: int, page_size: int | float
) -> tuple[dict, str, dict, dict, int]:
    return _build_page_updates(image_files, page=current_page + 1, page_size=page_size)


# ================================================================================
# 関数の概要: 表示件数変更時にページを先頭へ戻して UI を更新する。
# 引数: page_size（1ページ件数）、image_files（全画像パス）。
# 戻り値: ギャラリー、ページ表示、前/次ボタン、現在ページ。
# ================================================================================
def _on_page_size_change(
    page_size: int | float, image_files: list[str]
) -> tuple[dict, str, dict, dict, int]:
    return _build_page_updates(image_files, page=1, page_size=page_size)


_gallery_files = _list_image_paths(_DIR)
_gallery_count = len(_gallery_files)
_folder_options = _build_folder_choices(_DIR)
_MD_INTRO = _INITIAL_INTRO
(
    _initial_gallery_update,
    _initial_page_label,
    _initial_prev_update,
    _initial_next_update,
    _initial_current_page,
) = _build_page_updates(_gallery_files, page=1, page_size=_DEFAULT_PAGE_SIZE)

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
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow-x: auto;
    overflow-y: auto;
}}
#gradio_image_viewer .grid-wrap {{
    flex: 1;
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
    align-items: flex-start;
    flex-wrap: nowrap !important;
    overflow-y: visible;
    height: auto;
    max-height: none;
    padding: 0 0 {_SCROLLBAR_RESERVE_PX}px 0;
    box-sizing: border-box;
}}
#gradio_image_viewer button.thumbnail-item.thumbnail-lg {{
    min-height: 0;
    width: auto;
    height: auto;
    aspect-ratio: 1;
    max-height: calc({_THUMB_MAX_CSS} - {_SCROLLBAR_RESERVE_PX}px);
    max-width: {_THUMB_MAX_CSS};
    flex-shrink: 0;
    overflow: hidden;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 4px;
}}
#gradio_image_viewer button.thumbnail-item.thumbnail-lg img {{
    flex: 0 1 auto;
    max-width: 100%;
    max-height: 100%;
    width: auto !important;
    height: auto !important;
    object-fit: contain !important;
}}
#gradio_image_viewer_page_label p {{
    font-size: 1.3rem !important;
    font-weight: 700;
    margin: 0;
}}
"""

with gr.Blocks(title="Gradio Image Viewer", css=lightbox_css() + _GALLERY_GRID_CSS) as demo:
    with gr.Column(elem_id="gradio_image_viewer_layout"):
        gr.Markdown("# Gradio Image Viewer")
        gr.Markdown("### フォルダを選択")
        _current_directory = gr.State(str(_DIR))
        _all_gallery_files = gr.State(_gallery_files)
        _current_page = gr.State(_initial_current_page)
        _folder_dropdown = gr.Dropdown(
            choices=_folder_options,
            value=str(_DIR),
            label="フォルダ選択",
            allow_custom_value=True,
            interactive=True,
        )
        with gr.Row():
            _page_size = gr.Number(
                value=_DEFAULT_PAGE_SIZE,
                label="表示件数",
                precision=0,
                minimum=1,
            )
            _show_button = gr.Button("表示")
        _intro_markdown = gr.Markdown(_MD_INTRO)
        with gr.Row():
            _prev_page_button = gr.Button(
                "前ページ", interactive=_initial_prev_update["interactive"]
            )
            _page_label = gr.Markdown(
                f"**{_initial_page_label}**", elem_id="gradio_image_viewer_page_label"
            )
            _next_page_button = gr.Button(
                "次ページ", interactive=_initial_next_update["interactive"]
            )
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
        inputs=[_folder_dropdown, _current_directory],
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
        ],
    )
    _prev_page_button.click(
        _on_prev_page,
        inputs=[_all_gallery_files, _current_page, _page_size],
        outputs=[_gallery, _page_label, _prev_page_button, _next_page_button, _current_page],
    )
    _next_page_button.click(
        _on_next_page,
        inputs=[_all_gallery_files, _current_page, _page_size],
        outputs=[_gallery, _page_label, _prev_page_button, _next_page_button, _current_page],
    )
    _page_size.change(
        _on_page_size_change,
        inputs=[_page_size, _all_gallery_files],
        outputs=[_gallery, _page_label, _prev_page_button, _next_page_button, _current_page],
    )
    demo.load(
        None,
        inputs=None,
        outputs=None,
        _js="""
() => {
  const RESERVE = 16;
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

  const applyGalleryHeight = () => {
    const top = galleryArea.getBoundingClientRect().top;
    const bottomLimit = getBottomLimit();
    const nextHeight = Math.max(
      bottomLimit - top - RESERVE,
      120
    );
    galleryArea.style.setProperty("--image-viewer-gallery-height", `${nextHeight}px`);
  };

  applyGalleryHeight();
  window.addEventListener("resize", applyGalleryHeight);
  const obs = new MutationObserver(applyGalleryHeight);
  obs.observe(layout, { childList: true, subtree: true, attributes: true });
  return [];
}
""",
    )
    attach_lightbox(demo, "gradio_image_viewer")

if __name__ == "__main__":
    demo.launch(share=True)
