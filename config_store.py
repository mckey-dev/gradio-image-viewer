from __future__ import annotations

# ================================================================================
# Gradio Image Viewer: config.json のロード／セーブを担当する設定ストアモジュール。
# ================================================================================

import json
from dataclasses import dataclass
from pathlib import Path


# ================================================================================
# 関数の概要: ビューア設定の値オブジェクトを保持する。
# 引数: last_folder_path（前回フォルダ絶対パス）、last_page_size（前回表示件数）。
# 戻り値: なし（データクラス定義）。
# ================================================================================
@dataclass(frozen=True)
class ViewerConfig:
    last_folder_path: str
    last_page_size: int


# ================================================================================
# 関数の概要: config.json への設定ロード／セーブを担当する。
# 引数: config_path（設定ファイルパス）、default_directory（既定フォルダ）、
#       default_page_size（既定表示件数）。
# 戻り値: なし（クラス定義）。
# ================================================================================
class ViewerConfigStore:
    """Load/save viewer settings from config.json."""

    # ================================================================================
    # 関数の概要: 設定ストアの初期値と保存先を初期化する。
    # 引数: config_path（設定ファイルパス）、default_directory（既定フォルダ）、
    #       default_page_size（既定表示件数）。
    # 戻り値: なし。
    # ================================================================================
    def __init__(
        self,
        config_path: Path,
        *,
        default_directory: Path,
        default_page_size: int,
    ) -> None:
        self._config_path = config_path
        self._default_directory = default_directory.resolve()
        self._default_page_size = max(int(default_page_size), 1)

    # ================================================================================
    # 関数の概要: 表示件数の値を1以上の整数に正規化する。
    # 引数: value（外部入力値）。
    # 戻り値: 正規化済み表示件数。
    # ================================================================================
    def _normalize_page_size(self, value: object) -> int:
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return self._default_page_size

    # ================================================================================
    # 関数の概要: フォルダパス文字列を存在する絶対ディレクトリへ正規化する。
    # 引数: value（外部入力値）。
    # 戻り値: 正規化済みディレクトリパス。
    # ================================================================================
    def _normalize_directory(self, value: object) -> Path:
        if not isinstance(value, str) or not value:
            return self._default_directory
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self._default_directory / candidate
        try:
            candidate = candidate.resolve()
        except OSError:
            return self._default_directory
        return candidate if candidate.is_dir() else self._default_directory

    # ================================================================================
    # 関数の概要: config.json から設定を読み込み、利用可能な値へ補正して返す。
    # 引数: なし。
    # 戻り値: ViewerConfig（前回フォルダパス・前回表示件数）。
    # ================================================================================
    def load(self) -> ViewerConfig:
        if not self._config_path.is_file():
            return ViewerConfig(
                last_folder_path=str(self._default_directory),
                last_page_size=self._default_page_size,
            )
        try:
            payload = json.loads(self._config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ViewerConfig(
                last_folder_path=str(self._default_directory),
                last_page_size=self._default_page_size,
            )

        folder = self._normalize_directory(payload.get("last_folder_path"))
        page_size = self._normalize_page_size(payload.get("last_page_size"))
        return ViewerConfig(last_folder_path=str(folder), last_page_size=page_size)

    # ================================================================================
    # 関数の概要: 指定された設定値を正規化して config.json に保存する。
    # 引数: last_folder_path（保存対象フォルダパス）、last_page_size（保存対象表示件数）。
    # 戻り値: なし。
    # ================================================================================
    def save(self, *, last_folder_path: str, last_page_size: object) -> None:
        folder = self._normalize_directory(last_folder_path)
        page_size = self._normalize_page_size(last_page_size)
        payload = {
            "last_folder_path": str(folder),
            "last_page_size": page_size,
        }
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            # 設定保存に失敗しても UI 動作は継続する。
            return

