# ================================================================================
# Gradio: プレビュー用ライトボックス（LIGHTBOX_CSS + lightbox.js を demo.load で注入）。
# ================================================================================

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence, Union

# 本モジュールと同じディレクトリ（lightbox.js 既定パスの基準）
_PACKAGE_DIR = Path(__file__).resolve().parent
# インライン注入するフロント用スクリプトの既定パス
DEFAULT_SCRIPT_PATH = _PACKAGE_DIR / "lightbox.js"

# gr.Blocks(css=...) へそのまま渡すモーダル・ツールバー・ナビ用スタイル
LIGHTBOX_CSS = """
#paperspaceLightboxModal {
    display: none;
    position: fixed;
    z-index: 10001;
    left: 0;
    top: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
    background-color: rgba(20, 20, 20, 0.95);
    align-items: center;
    justify-content: center;
    box-sizing: border-box;
}
.paperspace-lightbox-inner {
    position: relative;
    max-width: 100%;
    max-height: 100%;
    margin: auto;
    padding: 2rem;
    box-sizing: border-box;
}
.paperspace-lightbox-toolbar {
    position: absolute;
    top: 0.5rem;
    left: 0.5rem;
    display: flex;
    align-items: center;
    gap: 0.35rem;
    z-index: 2;
    color: #fff;
    text-shadow: 0 0 0.25rem #000;
    font-size: 14px;
}
.paperspace-lightbox-toolbar button {
    border: 1px solid rgba(255,255,255,0.35);
    background: rgba(0,0,0,0.35);
    color: #fff;
    border-radius: 4px;
    width: 2rem;
    height: 2rem;
    cursor: pointer;
    font-size: 1.1rem;
    line-height: 1;
    padding: 0;
}
.paperspace-lightbox-toolbar button:hover {
    background: rgba(0,0,0,0.55);
}
#paperspaceLightboxZoomLabel {
    min-width: 3.2rem;
    text-align: center;
    user-select: none;
}
.paperspace-lightbox-panwrap {
    display: block;
    width: max-content;
    max-width: 100%;
    margin: 0 auto;
    transform: translate(0, 0);
    transition: transform 0.08s ease-out;
    -webkit-user-select: none;
    user-select: none;
}
.paperspace-lightbox-panwrap.paperspace-lightbox-dragging {
    transition: none;
}
#paperspaceLightboxImage {
    display: block;
    max-width: 100%;
    max-height: calc(100vh - 4rem);
    width: auto;
    height: auto;
    object-fit: contain;
    margin: 0 auto;
    cursor: default;
    transform: scale(1);
    transform-origin: center center;
    transition: transform 0.08s ease-out;
}
.paperspace-lightbox-close {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    border: none;
    background: transparent;
    color: #fff;
    font-size: 2rem;
    line-height: 1;
    cursor: pointer;
    text-shadow: 0 0 0.25rem #000;
    z-index: 2;
}
.paperspace-lightbox-close:hover {
    color: #ccc;
}
.paperspace-lightbox-nav {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    z-index: 3;
    padding: 0.75rem 0.5rem;
    border: none;
    color: #fff;
    font-size: 1.35rem;
    font-weight: bold;
    cursor: pointer;
    user-select: none;
    background: rgba(0, 0, 0, 0.35);
    text-shadow: 0 0 0.25rem #000;
    line-height: 1;
}
.paperspace-lightbox-nav:hover {
    background: rgba(0, 0, 0, 0.55);
}
.paperspace-lightbox-nav:disabled {
    opacity: 0.25;
    cursor: default;
    pointer-events: none;
}
.paperspace-lightbox-prev {
    left: 0.35rem;
    border-radius: 0 6px 6px 0;
}
.paperspace-lightbox-next {
    right: 0.35rem;
    border-radius: 6px 0 0 6px;
}
.paperspace-lightbox-counter {
    font-size: 12px;
    min-width: 3.5rem;
    text-align: center;
    user-select: none;
    opacity: 0.95;
}
"""


# ================================================================================
# 関数の概要: ライトボックス用 CSS 文字列を返す。
# 引数: なし。
# 戻り値: LIGHTBOX_CSS と同じ CSS 文字列。
# ================================================================================
def lightbox_css() -> str:
    return LIGHTBOX_CSS


# ================================================================================
# 関数の概要: elem_id 入力を list[str] へ正規化する。
# 引数: root_elem_ids（単一の elem_id または複数 id のシーケンス）。
# 戻り値: 正規化された id リスト（順序は入力を維持）。
# ================================================================================
def _normalize_root_ids(root_elem_ids: Union[str, Sequence[str]]) -> list[str]:
    if isinstance(root_elem_ids, str):
        return [root_elem_ids]
    return list(root_elem_ids)


# ================================================================================
# 関数の概要: Gradio の demo.load(..., _js=...) に渡す注入用 JavaScript を生成する。
# 引数: root_elem_ids（監視対象 elem_id）、script_path（注入対象 JS パス、未指定時は既定）。
# 戻り値: 即時実行関数形式の JavaScript 文字列。
# ================================================================================
def build_lightbox_inject_js(
    root_elem_ids: Union[str, Sequence[str]],
    *,
    script_path: Path | None = None,
) -> str:
    path = script_path if script_path is not None else DEFAULT_SCRIPT_PATH
    code = path.read_text(encoding="utf-8")
    code_literal = json.dumps(code)
    ids_literal = json.dumps(_normalize_root_ids(root_elem_ids))
    return f"""() => {{
    if (window.__grLightboxLoader) return [];
    window.__grLightboxLoader = true;
    window.__grLightboxRootIds = {ids_literal};
    var s = document.createElement('script');
    s.textContent = {code_literal};
    document.head.appendChild(s);
    return [];
}}"""


# ================================================================================
# 関数の概要: Gradio Blocks の load イベントへライトボックス初期化スクリプトを登録する。
# 引数: demo（gr.Blocks 相当オブジェクト）、root_elem_ids（監視対象 elem_id）、script_path（任意）。
# 戻り値: なし。
# ================================================================================
def attach_lightbox(
    demo: Any,
    root_elem_ids: Union[str, Sequence[str]],
    *,
    script_path: Path | None = None,
) -> None:
    demo.load(
        None,
        inputs=None,
        outputs=None,
        _js=build_lightbox_inject_js(root_elem_ids, script_path=script_path),
    )


__all__ = [
    "DEFAULT_SCRIPT_PATH",
    "LIGHTBOX_CSS",
    "attach_lightbox",
    "build_lightbox_inject_js",
    "lightbox_css",
]
