/**
 * ================================================================================
 * Gradio プレビュー用全画面ライトボックス。
 * サムネイル src に #orig=<encoded_url> が付与されている場合は元画像 URL を優先表示する。
 * Python は lightbox.py が __grLightboxRootIds をセットしてから注入。CSS は LIGHTBOX_CSS と id を合わせる。
 * ================================================================================
 */
(function () {
    /** 既定の要素 id（lightbox.py の LIGHTBOX_CSS と一致させること） */
    var DEFAULT_ELEMENT_IDS = {
        modal: "paperspaceLightboxModal",
        panWrap: "paperspaceLightboxPanWrap",
        image: "paperspaceLightboxImage",
        zoomLabel: "paperspaceLightboxZoomLabel",
        counter: "paperspaceLightboxCounter",
        prev: "paperspaceLightboxPrev",
        next: "paperspaceLightboxNext",
    };

    class GradioImageLightbox {
        /**
         * ================================================================================
         * 関数の概要: ライトボックスのインスタンス状態と設定値を初期化する。
         * 引数: @param {object} [options], @param {object} [options.ids], @param {string[]} [options.fallbackRootIds]
         * 戻り値: なし（コンストラクタ）。
         * ================================================================================
         */
        constructor(options) {
            options = options || {};
            this.ids = Object.assign({}, DEFAULT_ELEMENT_IDS, options.ids || {});
            this.fallbackRootIds = options.fallbackRootIds || ["gradio_image_viewer"];
            this.currentIndex = -1;

            this.lightboxZoom = 1;
            this.panX = 0;
            this.panY = 0;

            this.dragActive = false;
            this.dragStartX = 0;
            this.dragStartY = 0;
            this.dragStartPanX = 0;
            this.dragStartPanY = 0;
        }

        /**
         * ================================================================================
         * 関数の概要: プレビュー画像URLからライトボックスで開く元画像URLを抽出する。
         * 引数: @param {HTMLImageElement} img
         * 戻り値: @returns {string}
         * ================================================================================
         */
        getFullImageSrc(img) {
            if (!img || !img.src) return "";
            var previews = this.getOrderedPreviewImages();
            var idx = previews.indexOf(img);
            if (idx < 0) return img.src;
            var originals = this.getCurrentPageOriginals();
            if (idx >= originals.length) return img.src;
            return this.toFileUrl(originals[idx], img.src);
        }

        /**
         * ================================================================================
         * 関数の概要: hidden テキストから現在ページの元画像パス配列を取得する。
         * 引数: なし。
         * 戻り値: @returns {string[]}
         * ================================================================================
         */
        getCurrentPageOriginals() {
            var holder = document.getElementById("gradio_image_viewer_originals");
            if (!holder) return [];
            var raw = "";
            var input =
                holder.matches("input,textarea")
                    ? holder
                    : holder.querySelector("input,textarea");
            if (input && typeof input.value === "string" && input.value) {
                raw = input.value;
            } else if (typeof holder.textContent === "string" && holder.textContent) {
                raw = holder.textContent;
            }
            if (!raw) return [];
            try {
                var parsed = JSON.parse(raw);
                if (!Array.isArray(parsed)) return [];
                return parsed.filter(function (x) {
                    return typeof x === "string" && x.length > 0;
                });
            } catch (err) {
                return [];
            }
        }

        /**
         * ================================================================================
         * 関数の概要: ローカルパスを Gradio の /file= URL へ変換する。
         * 引数: @param {string} source, @param {string} fallback
         * 戻り値: @returns {string}
         * ================================================================================
         */
        toFileUrl(source, fallback) {
            if (!source) return fallback || "";
            if (
                source.startsWith("/file=") ||
                source.startsWith("http://") ||
                source.startsWith("https://") ||
                source.startsWith("blob:") ||
                source.startsWith("data:")
            ) {
                return source;
            }
            return "/file=" + encodeURIComponent(source);
        }

        /**
         * ================================================================================
         * 関数の概要: ids キーに対応する DOM 要素を取得する内部ヘルパー。
         * 引数: @param {string} key - ids のプロパティ名。
         * 戻り値: @returns {HTMLElement | null}
         * ================================================================================
         */
        _byId(key) {
            return document.getElementById(this.ids[key]);
        }

        /**
         * ================================================================================
         * 関数の概要: 監視対象ルート要素の id 配列を返す。
         * 引数: なし。
         * 戻り値: @returns {string[]}
         * ================================================================================
         */
        rootIds() {
            var ids = window.__grLightboxRootIds;
            if (ids && ids.length) return ids;
            return this.fallbackRootIds;
        }

        /**
         * ================================================================================
         * 関数の概要: 存在するルート要素に対してコールバックを順番に実行する。
         * 引数: @param {(root: HTMLElement) => void} fn
         * 戻り値: なし。
         * ================================================================================
         */
        forEachRoot(fn) {
            this.rootIds().forEach(function (id) {
                var el = document.getElementById(id);
                if (el) fn(el);
            });
        }

        /**
         * ================================================================================
         * 関数の概要: 全ルート配下の img を順序付きで収集する。
         * 引数: なし。
         * 戻り値: @returns {HTMLImageElement[]}
         * ================================================================================
         */
        getOrderedPreviewImages() {
            var list = [];
            this.forEachRoot(function (root) {
                root
                    .querySelectorAll("button.thumbnail-item.thumbnail-lg img")
                    .forEach(function (el) {
                    if (el.src) list.push(el);
                });
            });
            return list;
        }

        /**
         * ================================================================================
         * 関数の概要: ナビゲーションボタン状態と画像カウンター表示を更新する。
         * 引数: なし。
         * 戻り値: なし。
         * ================================================================================
         */
        refreshNavState() {
            var imgs = this.getOrderedPreviewImages();
            var n = imgs.length;
            var big = this._byId("image");
            var prev = this._byId("prev");
            var next = this._byId("next");
            var counter = this._byId("counter");
            if (!big || !prev || !next) return;
            if (this.currentIndex < 0 || this.currentIndex >= n) this.currentIndex = -1;

            var multi = n > 1;
            prev.style.display = multi ? "" : "none";
            next.style.display = multi ? "" : "none";
            prev.disabled = !multi;
            next.disabled = !multi;

            if (counter) {
                if (multi && this.currentIndex >= 0) {
                    counter.textContent = this.currentIndex + 1 + " / " + n;
                    counter.style.display = "";
                } else if (multi) {
                    counter.textContent = "— / " + n;
                    counter.style.display = "";
                } else {
                    counter.textContent = "";
                    counter.style.display = "none";
                }
            }
        }

        /**
         * ================================================================================
         * 関数の概要: 現在画像から相対移動して表示画像を切り替える。
         * 引数: @param {number} delta -1 で前、+1 で次。
         * 戻り値: なし。
         * ================================================================================
         */
        navigateRelative(delta) {
            var imgs = this.getOrderedPreviewImages();
            if (imgs.length === 0) return;
            var big = this._byId("image");
            if (!big) return;
            if (this.currentIndex < 0 || this.currentIndex >= imgs.length) {
                this.currentIndex = 0;
            } else {
                this.currentIndex = (this.currentIndex + delta + imgs.length) % imgs.length;
            }

            this.resetZoom();
            big.src = this.getFullImageSrc(imgs[this.currentIndex]);
            this.refreshNavState();
        }

        /**
         * ================================================================================
         * 関数の概要: パン位置とズーム倍率を DOM 表示へ反映する。
         * 引数: なし。
         * 戻り値: なし。
         * ================================================================================
         */
        applyTransform() {
            var wrap = this._byId("panWrap");
            var big = this._byId("image");
            if (wrap) {
                wrap.style.transform = "translate(" + this.panX + "px," + this.panY + "px)";
                wrap.style.touchAction = this.lightboxZoom > 1 ? "none" : "auto";
                wrap.style.cursor = this.lightboxZoom > 1 ? "grab" : "";
            }
            if (big) {
                big.style.transform = "scale(" + this.lightboxZoom + ")";
            }
            var label = this._byId("zoomLabel");
            if (label) {
                label.textContent = Math.round(this.lightboxZoom * 100) + "%";
            }
        }

        /**
         * ================================================================================
         * 関数の概要: 指定倍率を範囲内に補正して適用する。
         * 引数: @param {number} scale
         * 戻り値: なし。
         * ================================================================================
         */
        applyZoom(scale) {
            var C = GradioImageLightbox;
            this.lightboxZoom = Math.max(C.ZOOM_MIN, Math.min(C.ZOOM_MAX, scale));
            if (this.lightboxZoom === 1) {
                this.panX = 0;
                this.panY = 0;
            }
            this.applyTransform();
        }

        /**
         * ================================================================================
         * 関数の概要: 表示倍率を 100% に戻しパン位置を初期化する。
         * 引数: なし。
         * 戻り値: なし。
         * ================================================================================
         */
        resetZoom() {
            this.applyZoom(1);
        }

        /**
         * ================================================================================
         * 関数の概要: 現在倍率に差分を加算してズームする。
         * 引数: @param {number} delta
         * 戻り値: なし。
         * ================================================================================
         */
        zoomBy(delta) {
            this.applyZoom(this.lightboxZoom + delta);
        }

        /**
         * ================================================================================
         * 関数の概要: ドラッグ中の見た目（クラス・カーソル）を切り替える。
         * 引数: @param {boolean} on
         * 戻り値: なし。
         * ================================================================================
         */
        setDraggingStyle(on) {
            var wrap = this._byId("panWrap");
            if (!wrap) return;
            wrap.classList.toggle("paperspace-lightbox-dragging", on);
            if (this.lightboxZoom > 1) {
                wrap.style.cursor = on ? "grabbing" : "grab";
            }
        }

        /**
         * ================================================================================
         * 関数の概要: モーダル DOM を生成してイベントを設定し、既存時は再利用する。
         * 引数: なし。
         * 戻り値: @returns {HTMLElement}
         * ================================================================================
         */
        ensureModal() {
            var self = this;
            var ex = this._byId("modal");
            if (ex) return ex;

            var C = GradioImageLightbox;
            var modal = document.createElement("div");
            modal.id = this.ids.modal;
            modal.tabIndex = 0;
            modal.setAttribute("role", "dialog");
            modal.style.display = "none";

            var inner = document.createElement("div");
            inner.className = "paperspace-lightbox-inner";

            /**
             * ================================================================================
             * 関数の概要: 内側エリアでのホイール操作時にズームを実行する。
             * 引数: @param {WheelEvent} e
             * 戻り値: なし。
             * ================================================================================
             */
            inner.addEventListener(
                "wheel",
                function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    var delta = e.deltaY > 0 ? -C.ZOOM_STEP_WHEEL : C.ZOOM_STEP_WHEEL;
                    self.zoomBy(delta);
                },
                { passive: false }
            );

            var toolbar = document.createElement("div");
            toolbar.className = "paperspace-lightbox-toolbar";

            /**
             * ================================================================================
             * 関数の概要: ツールバー用ボタン要素を生成する。
             * 引数: html（表示文字列）、title（ツールチップ）、fn（クリック時処理）。
             * 戻り値: 生成した button 要素。
             * ================================================================================
             */
            function _toolBtn(html, title, fn) {
                var b = document.createElement("button");
                b.type = "button";
                b.innerHTML = html;
                b.title = title;
                b.addEventListener("click", function (e) {
                    e.stopPropagation();
                    fn();
                });
                return b;
            }

            toolbar.appendChild(
                _toolBtn("&minus;", "縮小", function () {
                    self.zoomBy(-C.ZOOM_STEP_BUTTON);
                })
            );
            var zlabel = document.createElement("span");
            zlabel.id = this.ids.zoomLabel;
            zlabel.textContent = "100%";
            toolbar.appendChild(zlabel);
            toolbar.appendChild(
                _toolBtn("+", "拡大", function () {
                    self.zoomBy(C.ZOOM_STEP_BUTTON);
                })
            );
            toolbar.appendChild(
                _toolBtn("1:1", "100%・位置リセット", function () {
                    self.resetZoom();
                })
            );
            var counter = document.createElement("span");
            counter.id = this.ids.counter;
            counter.className = "paperspace-lightbox-counter";
            counter.style.display = "none";
            toolbar.appendChild(counter);

            var closeBtn = document.createElement("button");
            closeBtn.type = "button";
            closeBtn.className = "paperspace-lightbox-close";
            closeBtn.innerHTML = "&times;";
            closeBtn.title = "閉じる";
            closeBtn.addEventListener("click", function (e) {
                e.stopPropagation();
                self.closeModal();
            });

            var btnPrev = document.createElement("button");
            btnPrev.type = "button";
            btnPrev.id = this.ids.prev;
            btnPrev.className = "paperspace-lightbox-nav paperspace-lightbox-prev";
            btnPrev.innerHTML = "&#10094;";
            btnPrev.title = "前の画像";
            btnPrev.addEventListener("click", function (e) {
                e.stopPropagation();
                self.navigateRelative(-1);
            });

            var btnNext = document.createElement("button");
            btnNext.type = "button";
            btnNext.id = this.ids.next;
            btnNext.className = "paperspace-lightbox-nav paperspace-lightbox-next";
            btnNext.innerHTML = "&#10095;";
            btnNext.title = "次の画像";
            btnNext.addEventListener("click", function (e) {
                e.stopPropagation();
                self.navigateRelative(1);
            });

            var panWrap = document.createElement("div");
            panWrap.id = this.ids.panWrap;
            panWrap.className = "paperspace-lightbox-panwrap";

            var img = document.createElement("img");
            img.id = this.ids.image;
            img.alt = "Full size preview";
            img.draggable = false;

            /**
             * ================================================================================
             * 関数の概要: 拡大時のみパン操作を開始する。
             * 引数: @param {PointerEvent} e
             * 戻り値: なし。
             * ================================================================================
             */
            function _onPointerDown(e) {
                if (self.lightboxZoom <= 1) return;
                if (e.button !== undefined && e.button !== 0) return;
                self.dragActive = true;
                self.dragStartX = e.clientX;
                self.dragStartY = e.clientY;
                self.dragStartPanX = self.panX;
                self.dragStartPanY = self.panY;
                self.setDraggingStyle(true);
                try {
                    panWrap.setPointerCapture(e.pointerId);
                } catch (err) {
                    /* ignore */
                }
            }

            /**
             * ================================================================================
             * 関数の概要: ポインタ移動中にパン位置を更新する。
             * 引数: @param {PointerEvent} e
             * 戻り値: なし。
             * ================================================================================
             */
            function _onPointerMove(e) {
                if (!self.dragActive) return;
                var dx = e.clientX - self.dragStartX;
                var dy = e.clientY - self.dragStartY;
                self.panX = self.dragStartPanX + dx;
                self.panY = self.dragStartPanY + dy;
                self.applyTransform();
            }

            /**
             * ================================================================================
             * 関数の概要: パン操作を終了して pointer capture を解放する。
             * 引数: @param {PointerEvent} e
             * 戻り値: なし。
             * ================================================================================
             */
            function _onPointerUp(e) {
                if (!self.dragActive) return;
                self.dragActive = false;
                self.setDraggingStyle(false);
                try {
                    panWrap.releasePointerCapture(e.pointerId);
                } catch (err) {
                    /* ignore */
                }
            }

            panWrap.addEventListener("pointerdown", _onPointerDown);
            panWrap.addEventListener("pointermove", _onPointerMove);
            panWrap.addEventListener("pointerup", _onPointerUp);
            panWrap.addEventListener("pointercancel", _onPointerUp);

            panWrap.appendChild(img);

            inner.appendChild(toolbar);
            inner.appendChild(closeBtn);
            inner.appendChild(btnPrev);
            inner.appendChild(btnNext);
            inner.appendChild(panWrap);
            modal.appendChild(inner);

            /**
             * ================================================================================
             * 関数の概要: モーダルフォーカス時のキーボード操作を処理する。
             * 引数: @param {KeyboardEvent} e
             * 戻り値: なし。
             * ================================================================================
             */
            modal.addEventListener("keydown", function (e) {
                if (e.key === "Escape") self.closeModal();
                if (e.key === "ArrowLeft") {
                    e.preventDefault();
                    self.navigateRelative(-1);
                }
                if (e.key === "ArrowRight") {
                    e.preventDefault();
                    self.navigateRelative(1);
                }
                if (e.key === "+" || e.key === "=") {
                    e.preventDefault();
                    self.zoomBy(C.ZOOM_STEP_BUTTON);
                }
                if (e.key === "-" || e.key === "_") {
                    e.preventDefault();
                    self.zoomBy(-C.ZOOM_STEP_BUTTON);
                }
                if (e.key === "0") {
                    e.preventDefault();
                    self.resetZoom();
                }
            });

            document.body.appendChild(modal);
            return modal;
        }

        /**
         * ================================================================================
         * 関数の概要: モーダルを非表示にする。
         * 引数: なし。
         * 戻り値: なし。
         * ================================================================================
         */
        closeModal() {
            var m = this._byId("modal");
            if (m) m.style.display = "none";
            this.currentIndex = -1;
        }

        /**
         * ================================================================================
         * 関数の概要: クリックされた画像をモーダル表示する。
         * 引数: @param {HTMLImageElement} clickedImg
         * 戻り値: なし。
         * ================================================================================
         */
        openLightboxForImage(clickedImg) {
            var imgs = this.getOrderedPreviewImages();
            var idx = imgs.indexOf(clickedImg);
            var modal = this.ensureModal();
            var big = this._byId("image");
            this.resetZoom();
            this.currentIndex = idx;
            big.src = idx < 0 ? this.getFullImageSrc(clickedImg) : this.getFullImageSrc(imgs[idx]);
            modal.style.display = "flex";
            modal.focus();
            this.refreshNavState();
        }

        /**
         * ================================================================================
         * 関数の概要: 画像要素にライトボックス起動ハンドラをバインドする。
         * 引数: @param {HTMLImageElement} img
         * 戻り値: なし。
         * ================================================================================
         */
        bindPreview(img) {
            var self = this;
            if (!img || img.dataset.paperspaceLbBound) return;
            img.dataset.paperspaceLbBound = "1";
            img.style.cursor = "pointer";
            img.addEventListener("click", function (evt) {
                evt.preventDefault();
                evt.stopPropagation();
                self.openLightboxForImage(img);
            });
        }

        /**
         * ================================================================================
         * 関数の概要: 全ルートの画像を走査して未バインド要素へイベントを設定する。
         * 引数: なし。
         * 戻り値: なし。
         * ================================================================================
         */
        scan() {
            var self = this;
            this.forEachRoot(function (root) {
                root
                    .querySelectorAll("button.thumbnail-item.thumbnail-lg img")
                    .forEach(function (el) {
                        self.bindPreview(el);
                    });
            });
        }

        /**
         * ================================================================================
         * 関数の概要: 初回スキャンと MutationObserver 登録を実行する。
         * 引数: なし。
         * 戻り値: なし。
         * ================================================================================
         */
        start() {
            var self = this;
            this.scan();
            this.forEachRoot(function (root) {
                if (root.dataset.grLightboxObs) return;
                root.dataset.grLightboxObs = "1";
                var obs = new MutationObserver(function () {
                    self.scan();
                });
                obs.observe(root, { childList: true, subtree: true, attributes: true });
            });
        }
    }

    /** ズーム下限・上限・ホイール／ボタン 1 ステップ量（静的）。 */
    GradioImageLightbox.ZOOM_MIN = 0.25;
    GradioImageLightbox.ZOOM_MAX = 4;
    GradioImageLightbox.ZOOM_STEP_WHEEL = 0.12;
    GradioImageLightbox.ZOOM_STEP_BUTTON = 0.25;

    window.GradioImageLightbox = GradioImageLightbox;

    /**
     * ================================================================================
     * 関数の概要: 既定設定のライトボックスを起動するエントリポイント。
     * 引数: なし。
     * 戻り値: なし。
     * ================================================================================
     */
    function _bootDefault() {
        new GradioImageLightbox().start();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", _bootDefault);
    } else {
        _bootDefault();
    }
})();
