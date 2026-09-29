
        let advts = [];
        let advtCategories = [];

        // Global canvas/layout state
        window.customColumnCount = 2;   // 1 or 2 columns

        window.canvasZoom = 1.0;        // preview zoom factor (0.25 / 0.50 / 1.0)

        /* ─── Zoom Control ─────────────────────────────────────────────────── */
        function _updateZoomButtons(zoom) {
            ['zoom25Btn', 'zoom50Btn', 'zoom100Btn'].forEach(id => {
                const btn = document.getElementById(id);
                if (!btn) return;
                btn.classList.remove('bg-slate-700', 'text-white');
                btn.classList.add('text-slate-600', 'hover:bg-slate-200');
            });
            const activeId = zoom === 0.25 ? 'zoom25Btn' : (zoom === 0.50 ? 'zoom50Btn' : 'zoom100Btn');
            const ab = document.getElementById(activeId);
            if (ab) { ab.classList.add('bg-slate-700', 'text-white'); ab.classList.remove('text-slate-600', 'hover:bg-slate-200'); }
        }

        function setCanvasZoom(zoom) {
            window.canvasZoom = zoom;
            _updateZoomButtons(zoom);
            // Re-render at new size — NOT CSS transform (transform doesn't affect scroll bounds)
            if (fabricCanvas) applyCanvasZoom();
        }

        /**
         * Resize Fabric.js canvas for the current zoom level.
         * Uses fabricCanvas.setZoom() so all drawn objects scale correctly.
         * Crisp rendering: Fabric.js already accounts for devicePixelRatio internally.
         */
        function applyCanvasZoom() {
            if (!fabricCanvas) return;
            const zoom = window.canvasZoom || 1.0;

            // Store the original logical size once (at zoom=1, 96 PPI)
            if (!fabricCanvas._logW) fabricCanvas._logW = fabricCanvas.getWidth();
            if (!fabricCanvas._logH) fabricCanvas._logH = fabricCanvas.getHeight();

            const logW = fabricCanvas._logW;
            const logH = fabricCanvas._logH;

            const cssWidth = logW * zoom;
            const cssHeight = logH * zoom;

            // 1. Set Fabric canvas logical size
            fabricCanvas.setWidth(cssWidth);
            fabricCanvas.setHeight(cssHeight);

            // 2. Override DOM canvas element for crisp high-DPI rendering
            const dpr = Math.max(window.devicePixelRatio || 1, 2);
            
            const htmlPreview = document.getElementById('htmlAdPreview');
            if (htmlPreview) {
                htmlPreview.style.transformOrigin = '0 0';
                htmlPreview.style.transform = 'scale(' + zoom + ')';
            }

            const lowerCanvas = fabricCanvas.lowerCanvasEl;

            const upperCanvas = fabricCanvas.upperCanvasEl;

            if (lowerCanvas && upperCanvas) {
                [lowerCanvas, upperCanvas].forEach(el => {
                    el.width = cssWidth * dpr;
                    el.height = cssHeight * dpr;
                    el.style.width = cssWidth + 'px';
                    el.style.height = cssHeight + 'px';
                });

                const ctx = fabricCanvas.getContext();
                ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
                ctx.imageSmoothingEnabled = true;
                ctx.imageSmoothingQuality = 'high';
            }

            fabricCanvas.setZoom(zoom);
            
                                fabricCanvas.renderAll();
                                updateHtmlPreview(); // Update HTML DOM view


            // Let scroll container know the real content size
            const inner = document.getElementById('canvasInner');
            if (inner) {
                inner.style.minWidth = (cssWidth + 48) + 'px';
                inner.style.minHeight = (cssHeight + 64) + 'px';
            }
        }

        // Keyboard Ctrl++ / Ctrl+- cycles zoom
        document.addEventListener('keydown', function (e) {
            if (!fabricCanvas) return;
            if (e.ctrlKey && (e.key === '+' || e.key === '=')) {
                e.preventDefault();
                const levels = [0.25, 0.50, 1.0];
                const idx = levels.indexOf(window.canvasZoom);
                setCanvasZoom(levels[Math.min(idx + 1, levels.length - 1)]);
            } else if (e.ctrlKey && e.key === '-') {
                e.preventDefault();
                const levels = [0.25, 0.50, 1.0];
                const idx = levels.indexOf(window.canvasZoom);
                setCanvasZoom(levels[Math.max(idx - 1, 0)]);
            }
        });

        /* ─── Column Count ─────────────────────────────────────────────────── */
        function setColumnCount(n) {
            window.customColumnCount = n;
            // Update toggle button styles
            const c1 = document.getElementById('col1Btn');
            const c2 = document.getElementById('col2Btn');
            if (c1 && c2) {
                if (n === 1) {
                    c1.classList.add('bg-brand-600', 'text-white');
                    c1.classList.remove('bg-white', 'text-brand-700');
                    c2.classList.remove('bg-brand-600', 'text-white');
                    c2.classList.add('bg-white', 'text-brand-700');
                } else {
                    c2.classList.add('bg-brand-600', 'text-white');
                    c2.classList.remove('bg-white', 'text-brand-700');
                    c1.classList.remove('bg-brand-600', 'text-white');
                    c1.classList.add('bg-white', 'text-brand-700');
                }
            }
            // Show/hide Balance Columns row (only meaningful in 2-col mode)
            const balRow = document.getElementById('balanceColumnsRow');
            if (balRow) balRow.style.display = (n === 2) ? 'flex' : 'none';
            // Reset stored border height so canvas auto-fits to new column layout
            window.customBorderHeight = null;
            updateCanvasFromText();
        }

        async function loadCategories() {
            try {
                const response = await fetch('/api/advt-categories/');
                if (!response.ok) throw new Error('Failed to load categories');
                advtCategories = await response.json();

                const select = document.getElementById('advtType');
                select.innerHTML = '<option value="" disabled selected>Select Category...</option>';

                advtCategories.forEach(cat => {
                    const option = document.createElement('option');
                    option.value = cat.name;
                    option.textContent = cat.name;
                    select.appendChild(option);
                });
            } catch (error) {
                console.error("Error loading categories:", error);
                const select = document.getElementById('advtType');
                select.innerHTML = '<option value="" disabled selected>Error loading categories</option>';
            }
        }

        async function loadAdvts() {
            try {
                const response = await fetch('/api/advt/');
                advts = await response.json();
                renderTable();
            } catch (error) {
                console.error("Error loading advts:", error);
                document.getElementById('advtTableBody').innerHTML = `<tr><td colspan="5" class="p-8 text-center text-red-500">Failed to load data</td></tr>`;
            }
        }

        function renderTable() {
            const tbody = document.getElementById('advtTableBody');
            if (advts.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" class="p-8 text-center text-slate-500">No advertisements found.</td></tr>`;
                return;
            }

            tbody.innerHTML = advts.map(advt => {
                const date = new Date(advt.created_at).toLocaleString();
                let typeIcon = '';
                if (advt.file_type.includes('pdf')) typeIcon = '📄 PDF';
                else if (advt.file_type.includes('image')) typeIcon = '🖼️ Image';
                else typeIcon = '📝 Word';

                return `
                <tr class="hover:bg-slate-50 transition-colors">
                    <td class="p-4 pl-6 font-medium text-slate-800">${advt.filename}</td>
                    <td class="p-4 text-slate-500">
                        <span class="px-2 py-1 bg-slate-100 rounded-md text-xs font-semibold">${typeIcon}</span>
                    </td>
                    <td class="p-4 text-slate-500 text-sm">${date}</td>
                    <td class="p-4">
                        <span class="px-2.5 py-1 rounded-full text-[11px] font-bold tracking-wide uppercase bg-green-100 text-green-700 border border-green-200">
                            ${advt.status}
                        </span>
                    </td>
                    <td class="p-4 pr-6 text-right">
                        <div class="flex items-center justify-end gap-3">
                            <button onclick="openEditModal('${advt._id}')" 
                                class="text-indigo-600 hover:text-indigo-800 font-bold text-[10px] uppercase tracking-wider px-3 py-1.5 rounded-lg border border-transparent hover:border-indigo-200 hover:bg-indigo-50 transition-all flex items-center gap-1.5">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                                </svg>
                                Edit
                            </button>
                            <button onclick="deleteAdvt('${advt._id}')" 
                                class="px-3 py-1.5 bg-red-50 text-red-600 rounded-lg text-[10px] font-bold uppercase tracking-wider hover:bg-red-600 hover:text-white border border-red-200 transition-all shadow-sm flex items-center gap-1.5">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                                </svg>
                                Delete
                            </button>
                        </div>
                    </td>
                </tr>
                `;
            }).join('');
        }

        function updateFileName(input) {
            const label = document.getElementById('selectedFileName');
            if (input.files && input.files[0]) {
                label.textContent = `Selected file: ${input.files[0].name}`;
                label.classList.remove('hidden');
            } else {
                label.classList.add('hidden');
            }
        }

        function updateBlankFileName(input) {
            const label = document.getElementById('selectedBlankFileName');
            if (input.files && input.files[0]) {
                label.textContent = `Selected template: ${input.files[0].name}`;
                label.classList.remove('hidden');
            } else {
                label.classList.add('hidden');
            }
        }

        async function ensureFontsLoaded() {
            try {
                await Promise.all([
                    document.fonts.load("20px 'BMA'"),
                    document.fonts.load("12px 'BGOT'"),
                    document.fonts.load("12px 'BGOTB'")
                ]);
                await document.fonts.ready;
            } catch (e) {
                console.warn("Font loading error:", e);
            }
        }

        let fabricCanvas = null;

        async function handleUpload(e) {
            e.preventDefault();
            const fileInput = document.getElementById('advtFile');
            if (!fileInput.files || fileInput.files.length === 0) {
                alert('Please select a creative file first.');
                return;
            }

            const file = fileInput.files[0];
            const formData = new FormData();
            formData.append('file', file);

            const blankFileInput = document.getElementById('advtBlankFile');
            if (blankFileInput && blankFileInput.files.length > 0) {
                formData.append('blank_file', blankFileInput.files[0]);
            }

            formData.append('advt_type', document.getElementById('advtType').value);

            let h = document.getElementById('advtHeight').value;
            let w = document.getElementById('advtWidth').value;
            formData.append('height', h ? h : "0");
            formData.append('width', w ? w : "0");
            formData.append('unit', document.getElementById('advtUnit').value || "cm");

            // Processing options
            formData.append('eng_to_guj', document.getElementById('optEngToGuj').checked);
            formData.append('add_keypoints', document.getElementById('optAddKeyPoints').checked);
            formData.append('legal_notice', document.getElementById('optLegalNotice').checked);

            document.getElementById('uploadBtn').disabled = true;
            document.getElementById('uploadProgress').classList.remove('hidden');

            try {
                const response = await fetch('/api/advt/upload', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.detail || 'Upload failed');
                }

                const resData = await response.json();

                closeUploadModal();
                await loadAdvts();

                // Automatically open the canvas to show the user what happened!
                if (resData && resData.data && resData.data._id) {
                    openEditModal(resData.data._id);
                }
            } catch (error) {
                alert(`Error: ${error.message}`);
            } finally {
                document.getElementById('uploadBtn').disabled = false;
                document.getElementById('uploadProgress').classList.add('hidden');
                fileInput.value = '';
                updateFileName(fileInput);
            }
        }

        function renderEditBlocks(jsonStr) {
            const container = document.getElementById('editBlocksContainer');
            container.innerHTML = '';

            if (!jsonStr) return;

            try {
                let parsedData = JSON.parse(jsonStr);
                let blocks = [];
                if (Array.isArray(parsedData)) {
                    blocks = parsedData;
                } else if (parsedData && Array.isArray(parsedData.gujarati_text)) {
                    blocks = parsedData.gujarati_text;
                }

                if (blocks.length > 0) {
                    blocks.forEach((block, index) => {
                        const div = document.createElement('div');
                        div.className = 'mb-4 relative';

                        const typeLabel = (block.type || 'Text Block').toUpperCase();
                        const textContent = block.text || '';
                        const lineCount = textContent.split('\n').length;
                        const estimatedRows = Math.max(lineCount, Math.ceil(textContent.length / 80));
                        const rows = Math.max(2, Math.min(20, estimatedRows));

                        let defaultSize = 11;
                        let defaultAlign = 'justify';
                        let defaultBold = false;
                        if (typeLabel === 'HEADING' || typeLabel === 'TITLE' || textContent.includes('જાહેર નોટિસ')) {
                            defaultSize = 20; defaultAlign = 'center'; defaultBold = true;
                        } else if (typeLabel === 'ADVOCATE') {
                            defaultSize = 12; defaultAlign = 'right'; defaultBold = true;
                        }

                        const fWeight = block.font_weight || (defaultBold ? 'bold' : 'normal');
                        const isBold = fWeight === 'bold' || fWeight === '900';
                        if (defaultSize === 11 && isBold) {
                            defaultSize = 12;
                        }
                        const fSize = block.font_size || defaultSize;
                        const fAlign = block.text_align || defaultAlign;
                        let fLayout = block.layout_position || ((typeLabel === 'HEADING' || typeLabel === 'TITLE') ? 'left' : 'full');

                        div.innerHTML = `
                            <div class="flex flex-wrap justify-between items-center mb-1 gap-2">
                                <label class="block text-xs font-bold text-slate-500 tracking-wider">${typeLabel}</label>
                                <div class="flex gap-1 items-center bg-white border border-slate-200 p-1 rounded-md shadow-sm">
                                    <span class="text-xs text-slate-500 font-medium px-1">Size:</span>
                                    <input type="number" step="0.5" class="block-format-size w-14 text-sm border border-slate-300 rounded px-1 text-center focus:ring-1 focus:ring-brand-500 outline-none" value="${fSize}">
                                    <div class="w-px h-4 bg-slate-300 mx-1"></div>
                                    <button type="button" class="block-format-bold p-1 rounded transition-colors ${isBold ? 'bg-slate-200 text-slate-800' : 'text-slate-500 hover:bg-slate-100'}" title="Bold">
                                        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M15.6 11.8c1-.7 1.6-1.8 1.6-3.1 0-2.4-1.9-4.3-4.3H7v15h6.3c2.6 0 4.7-2.1 4.7-4.7 0-1.7-.9-3.2-2.4-4.1zM9.5 6.4h3.4c1.3 0 2.3 1 2.3 2.3s-1 2.3-2.3 2.3H9.5V6.4zm3.9 11H9.5v-4.7h3.9c1.5 0 2.7 1.2 2.7 2.7s-1.2 2.7-2.7 2.7z"/></svg>
                                    </button>
                                    <div class="w-px h-4 bg-slate-300 mx-1"></div>
                                    <button type="button" data-align="left" class="block-format-align p-1 rounded transition-colors ${fAlign === 'left' ? 'bg-slate-200 text-slate-800' : 'text-slate-500 hover:bg-slate-100'}"><svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h10M4 18h16"></path></svg></button>
                                    <button type="button" data-align="center" class="block-format-align p-1 rounded transition-colors ${fAlign === 'center' ? 'bg-slate-200 text-slate-800' : 'text-slate-500 hover:bg-slate-100'}"><svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M7 12h10M4 18h16"></path></svg></button>
                                    <button type="button" data-align="right" class="block-format-align p-1 rounded transition-colors ${fAlign === 'right' ? 'bg-slate-200 text-slate-800' : 'text-slate-500 hover:bg-slate-100'}"><svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M10 12h10M4 18h16"></path></svg></button>
                                    <button type="button" data-align="justify" class="block-format-align p-1 rounded transition-colors ${fAlign === 'justify' ? 'bg-slate-200 text-slate-800' : 'text-slate-500 hover:bg-slate-100'}"><svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16"></path></svg></button>
                                    ${(typeLabel === 'HEADING' || typeLabel === 'TITLE') ? `
                                        <div class="w-px h-4 bg-slate-300 mx-1"></div>
                                        <button type="button" class="block-format-layout p-1 rounded transition-colors ${fLayout === 'left' ? 'bg-brand-100 text-brand-600' : 'text-slate-500 hover:bg-slate-100'}" title="Toggle Full Width / Left Column">
                                            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" d="M9 17V7m0 10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2m0 10a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 7a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2m3 9v-5m0 0V9m0 2h4m-4 0a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2a2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2Z"></path>
                                            </svg>
                                        </button>
                                        <div class="w-px h-4 bg-slate-300 mx-1"></div>
                                        <span class="text-xs text-slate-500 font-medium px-1" title="Black Background Height">Box H:</span>
                                        <input type="number" step="1" min="15" max="300" class="block-heading-height w-14 text-sm border border-slate-300 rounded px-1 text-center focus:ring-1 focus:ring-brand-500 outline-none" value="${block.bg_height || 35}" title="Black Background Height">
                                        <div class="w-px h-4 bg-slate-300 mx-1"></div>
                                        <span class="text-xs text-slate-500 font-medium px-1" title="Text Vertical Offset (Up/Down)">Text Y:</span>
                                        <input type="number" step="1" min="-50" max="150" class="block-heading-text-y w-14 text-sm border border-slate-300 rounded px-1 text-center focus:ring-1 focus:ring-brand-500 outline-none" value="${block.text_offset_y !== undefined ? block.text_offset_y : 0}" title="Text Vertical Position (Up/Down)">
                                    ` : ''}
                                </div>
                            </div>
                            <textarea class="block-editor-input w-full p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none text-slate-800 text-base leading-relaxed resize-y" rows="${rows}" data-index="${index}"></textarea>
                            <input type="hidden" class="block-format-bold-val" value="${fWeight}">
                            <input type="hidden" class="block-format-align-val" value="${fAlign}">
                            <input type="hidden" class="block-format-layout-val" value="${fLayout}">
                            <input type="hidden" class="block-heading-height-val" value="${block.bg_height || 35}">
                            <input type="hidden" class="block-heading-text-y-val" value="${block.text_offset_y !== undefined ? block.text_offset_y : 0}">
                        `;
                        div.querySelector('textarea').value = textContent;

                        div.querySelector('.block-format-bold').addEventListener('click', function (e) {
                            const textarea = div.querySelector('textarea');
                            if (textarea.selectionStart !== textarea.selectionEnd) {
                                let start = textarea.selectionStart;
                                let end = textarea.selectionEnd;
                                let val = textarea.value;
                                let selected = val.substring(start, end);
                                if (selected.startsWith('*') && selected.endsWith('*')) {
                                    textarea.value = val.substring(0, start) + selected.substring(1, selected.length - 1) + val.substring(end);
                                    textarea.selectionStart = start;
                                    textarea.selectionEnd = end - 2;
                                } else {
                                    textarea.value = val.substring(0, start) + '*' + selected + '*' + val.substring(end);
                                    textarea.selectionStart = start;
                                    textarea.selectionEnd = end + 2;
                                }
                                updateCanvasFromText();
                                return;
                            }

                            const hidden = div.querySelector('.block-format-bold-val');
                            const isCurrentlyBold = hidden.value === 'bold' || hidden.value === '900';
                            hidden.value = isCurrentlyBold ? 'normal' : 'bold';
                            if (isCurrentlyBold) {
                                this.classList.remove('bg-slate-200', 'text-slate-800');
                                this.classList.add('text-slate-500');
                            } else {
                                this.classList.add('bg-slate-200', 'text-slate-800');
                                this.classList.remove('text-slate-500');
                            }
                            updateCanvasFromText();
                        });

                        const layoutBtn = div.querySelector('.block-format-layout');
                        if (layoutBtn) {
                            layoutBtn.addEventListener('click', function () {
                                const hidden = div.querySelector('.block-format-layout-val');
                                const isLeft = hidden.value === 'left';
                                hidden.value = isLeft ? 'full' : 'left';
                                if (isLeft) {
                                    this.classList.remove('bg-brand-100', 'text-brand-600');
                                    this.classList.add('text-slate-500');
                                } else {
                                    this.classList.add('bg-brand-100', 'text-brand-600');
                                    this.classList.remove('text-slate-500');
                                }
                                updateCanvasFromText();
                            });
                        }

                        div.querySelectorAll('.block-format-align').forEach(btn => {
                            btn.addEventListener('click', function (e) {
                                const align = this.dataset.align;
                                div.querySelector('.block-format-align-val').value = align;
                                div.querySelectorAll('.block-format-align').forEach(b => {
                                    b.classList.remove('bg-slate-200', 'text-slate-800');
                                    b.classList.add('text-slate-500');
                                });
                                this.classList.add('bg-slate-200', 'text-slate-800');
                                this.classList.remove('text-slate-500');
                                updateCanvasFromText();
                            });
                        });

                        div.querySelector('.block-format-size').addEventListener('change', updateCanvasFromText);
                        const headingHeightEl = div.querySelector('.block-heading-height');
                        if (headingHeightEl) headingHeightEl.addEventListener('change', updateCanvasFromText);
                        const headingTextYEl = div.querySelector('.block-heading-text-y');
                        if (headingTextYEl) headingTextYEl.addEventListener('change', updateCanvasFromText);

                        container.appendChild(div);
                    });
                } else {
                    throw new Error("No array blocks found");
                }
            } catch (e) {
                // Fallback to a single textarea if JSON is invalid or not an array
                const ta = document.createElement('textarea');
                ta.className = 'block-editor-input w-full p-4 border border-slate-300 rounded-xl focus:ring-2 focus:ring-brand-500 outline-none resize-none font-medium text-slate-800 text-lg leading-relaxed';
                ta.value = jsonStr;
                ta.rows = 8;
                container.appendChild(ta);
            }
        }

        async function ensureFontsLoaded() {
            try {
                await Promise.all([
                    document.fonts.load('20px BMA'),
                    document.fonts.load('12px BGOT'),
                    document.fonts.load('12px BGOTB')
                ]);
                await document.fonts.ready;
            } catch (e) {
                console.warn("Font loading:", e);
            }
        }

        function openEditModal(id) {
            const advt = advts.find(a => a._id === id);
            if (advt) {
                document.getElementById('editAdvtId').value = id;
                document.getElementById('editTranslationText').value = advt.translated_text || '';
                renderEditBlocks(advt.translated_text || '');

                // Restore Layout Offset, Border Height, and Ad Width
                let parsedForOffset = null;
                try { parsedForOffset = JSON.parse(advt.translated_text); } catch (e) { }
                window.currentLayoutOffset = (parsedForOffset && parsedForOffset.layout_offset) ? parsedForOffset.layout_offset : 0;

                // Restore column count (default 2 for legal notice)
                if (parsedForOffset && parsedForOffset.column_count) {
                    window.customColumnCount = parsedForOffset.column_count;
                } else {
                    window.customColumnCount = 2;
                }
                window.customBorderHeight = (parsedForOffset && parsedForOffset.border_height) ? parsedForOffset.border_height : null;

                const isLegal = advt.advt_type && advt.advt_type.toLowerCase().includes('legal');
                const formIsLegal = document.getElementById('advtType') && document.getElementById('advtType').value.toLowerCase().includes('legal');

                if (parsedForOffset && parsedForOffset.ad_width) {
                    window.customAdWidth = parseFloat(parsedForOffset.ad_width);
                } else if (isLegal || formIsLegal) {
                    window.customAdWidth = 6.2;
                } else if (advt && advt.width > 0) {
                    window.customAdWidth = advt.unit === 'inch' ? advt.width * 2.54 : advt.width;
                } else {
                    window.customAdWidth = 6.2;
                }

                if (isLegal || formIsLegal) {
                    document.getElementById('legalLayoutControls').classList.remove('hidden');
                    document.getElementById('legalLayoutControls').classList.add('flex');
                    document.getElementById('layoutOffsetDisplay').innerText = window.currentLayoutOffset > 0 ? '+' + window.currentLayoutOffset : window.currentLayoutOffset;
                    const adWidthInput = document.getElementById('adWidthInput');
                    if (adWidthInput) adWidthInput.value = window.customAdWidth.toFixed(1);
                    // Sync column toggle buttons
                    const c1 = document.getElementById('col1Btn');
                    const c2 = document.getElementById('col2Btn');
                    const balRow = document.getElementById('balanceColumnsRow');
                    if (c1 && c2) {
                        if (window.customColumnCount === 1) {
                            c1.classList.add('bg-brand-600', 'text-white');
                            c1.classList.remove('bg-white', 'text-brand-700');
                            c2.classList.remove('bg-brand-600', 'text-white');
                            c2.classList.add('bg-white', 'text-brand-700');
                            if (balRow) balRow.style.display = 'none';
                        } else {
                            c2.classList.add('bg-brand-600', 'text-white');
                            c2.classList.remove('bg-white', 'text-brand-700');
                            c1.classList.remove('bg-brand-600', 'text-white');
                            c1.classList.add('bg-white', 'text-brand-700');
                            if (balRow) balRow.style.display = 'flex';
                        }
                    }
                } else {
                    document.getElementById('legalLayoutControls').classList.remove('flex');
                    document.getElementById('legalLayoutControls').classList.add('hidden');
                }

                const detailsContainer = document.getElementById('editAdvtDetails');
                detailsContainer.innerHTML = `
                    <div><strong>Type:</strong> ${advt.advt_type || 'N/A'}</div>
                    <div><strong>Size:</strong> ${advt.height || 0} x ${advt.width || 0} ${advt.unit || ''}</div>
                `;

                const imageContainer = document.getElementById('editImageContainer');

                if (advt.generated_image_url) {
                    imageContainer.style.display = 'block';
                    document.getElementById('editModal').style.display = "block";

                    setTimeout(async () => {
                        await ensureFontsLoaded();
                        if (!fabricCanvas) {
                            fabricCanvas = new fabric.Canvas('advtCanvas');
                            setupCanvasEvents();
                        }
                        fabricCanvas.clear();

                        fabric.Image.fromURL(advt.generated_image_url, function (img) {
                            // User wants it to look EXACTLY physical size on screen (e.g. 6.2cm = 2.44 inches). 
                            // Assuming standard 96 PPI screen.
                            let widthInCm = window.customAdWidth || 6.2;
                            let physicalScreenPx = (widthInCm / 2.54) * 96;

                            let scale = 1;
                            if (img.width > 0) {
                                scale = physicalScreenPx / img.width;
                            }

                            fabricCanvas.setWidth(img.width * scale);
                            fabricCanvas.setHeight(img.height * scale);

                            fabricCanvas.setBackgroundImage(img, fabricCanvas.renderAll.bind(fabricCanvas), {
                                scaleX: scale,
                                scaleY: scale
                            });

                            if (advt.translated_text) {
                                try {
                                    let parsedData = JSON.parse(advt.translated_text);
                                    let blocks = [];
                                    if (Array.isArray(parsedData)) {
                                        blocks = parsedData;
                                    } else if (parsedData && Array.isArray(parsedData.gujarati_text)) {
                                        blocks = parsedData.gujarati_text;
                                    }

                                    if (blocks.length > 0) {
                                        // Sort text blocks by their top Y-coordinate to process them top-to-bottom
                                        let sortedBlocks = [...blocks].sort((a, b) => (a.top_percent || 0) - (b.top_percent || 0));
                                        let textObjects = [];
                                        // Robust check for Legal Notice: either type matches, OR the AI output is missing 'top_percent' entirely
                                        const formAdvtTypeStr = document.getElementById('advtType') ? document.getElementById('advtType').value.toLowerCase() : '';
                                        const advtTypeStr = (advt.advt_type || '').toLowerCase();
                                        const isLegalType = advtTypeStr.includes('legal') || formAdvtTypeStr.includes('legal') || blocks.length > 0 && blocks.every(b => b.top_percent === undefined);

                                        if (isLegalType) {
                                            // Deterministic Sequential Layout Engine for Legal Notice
                                            const cWidth = img.width * scale;
                                            let cHeight = img.height * scale;

                                            if (window.customBorderHeight) {
                                                cHeight = window.customBorderHeight + 8;
                                            }

                                            // Draw outer border
                                            const borderRect = new fabric.Rect({
                                                left: 4,
                                                top: 4,
                                                width: cWidth - 8,
                                                height: cHeight - 8,
                                                fill: 'transparent',
                                                stroke: '#000000',
                                                strokeWidth: 2,
                                                selectable: true,
                                                strokeUniform: true,
                                                id: 'mainBorder'
                                            });
                                            borderRect.setControlsVisibility({
                                                mt: false, mb: true, ml: false, mr: true, bl: false, br: false, tl: false, tr: false, mtr: false
                                            });
                                            textObjects.push(borderRect);

                                            // Detect if we should use 2 columns based on canvas width (e.g., width > 600 corresponds to 15cm+)
                                            const isTwoColumn = true; // Always 2 columns for legal notice
                                            const padding = 10;

                                            let targetExportPx = 945; // default 8cm at 300 DPI
                                            if (advt && advt.width > 0) {
                                                targetExportPx = advt.unit === 'inch' ? advt.width * 300 : (advt.width / 2.54) * 300;
                                            }
                                            // ptToPx = 0.85 makes the font slightly smaller so it perfectly fits 4-5 words per line,
                                            // which naturally reduces the wide gaps caused by justification.
                                            const ptToPx = 0.85;

                                            // Draw center line
                                            const centerLine = new fabric.Line([cWidth / 2, 5, cWidth / 2, cHeight - 5], {
                                                stroke: '#000000',
                                                strokeWidth: 1,
                                                selectable: false,
                                                id: 'centerLine'
                                            });
                                            textObjects.push(centerLine);

                                            const colWidth = (cWidth / 2) - (padding * 1.5);
                                            let leftVals = [padding, (cWidth / 2) + (padding / 2)];

                                            // Separate blocks
                                            let headingBlock = blocks.find(b => (b.type || '').toLowerCase() === 'heading' || (b.text && b.text.includes('જાહેર નોટિસ')));
                                            let advocateBlocks = blocks.filter(b => (b.type || '').toLowerCase() === 'advocate');
                                            let contentBlocks = blocks.filter(b => b !== headingBlock && !advocateBlocks.includes(b));

                                            let col0_Y = padding;
                                            let col1_Y = padding;

                                            function parseInlineBold(text, defaultWeight, initialIsBold = false) {
                                                let cleanText = "";
                                                let isBold = initialIsBold;
                                                let styles = {};
                                                let pIdx = 0;
                                                let cIdx = 0;
                                                for (let i = 0; i < text.length; i++) {
                                                    if (text[i] === '*') {
                                                        isBold = !isBold;
                                                        continue;
                                                    }
                                                    cleanText += text[i];
                                                    if (text[i] === '\n') {
                                                        pIdx++;
                                                        cIdx = 0;
                                                    } else {
                                                        if (isBold && defaultWeight !== 'bold' && defaultWeight !== '900') {
                                                            if (!styles[pIdx]) styles[pIdx] = {};
                                                            styles[pIdx][cIdx] = { fontFamily: 'BGOTB' };
                                                        } else if (!isBold && (defaultWeight === 'bold' || defaultWeight === '900')) {
                                                            if (!styles[pIdx]) styles[pIdx] = {};
                                                            styles[pIdx][cIdx] = { fontFamily: 'BGOT' };
                                                        }
                                                        cIdx++;
                                                    }
                                                }
                                                return { cleanText, styles, finalIsBold: isBold };
                                            }

                                            // 1. Draw Heading
                                            if (headingBlock) {
                                                let isLeftLayout = headingBlock.layout_position ? headingBlock.layout_position === 'left' : true;
                                                let hLeft = 4;
                                                let hWidth = isLeftLayout ? (cWidth / 2) - 4 : cWidth - 8;

                                                let currentBgHeight = headingBlock.bg_height ? parseFloat(headingBlock.bg_height) : 35;

                                                // Background rect for heading to prevent font ascenders from bleeding
                                                const headingBg = new fabric.Rect({
                                                    left: hLeft,
                                                    top: 4,
                                                    width: hWidth,
                                                    height: currentBgHeight,
                                                    fill: '#000000',
                                                    selectable: true,
                                                    lockMovementX: true,
                                                    lockMovementY: true,
                                                    id: 'headingBg'
                                                });
                                                headingBg.setControlsVisibility({
                                                    mt: false, mb: true, ml: false, mr: false, bl: false, br: false, tl: false, tr: false, mtr: false
                                                });
                                                textObjects.push(headingBg);

                                                let defaultHWeight = headingBlock.font_weight || '900';
                                                let rawHText = headingBlock.text || 'જાહેર નોટિસ';
                                                let convertedH = (typeof unicodeToGopika === 'function') ? unicodeToGopika(rawHText) : rawHText;
                                                let parsedHeading = parseInlineBold(convertedH, defaultHWeight);

                                                let textOffsetY = headingBlock.text_offset_y !== undefined ? parseFloat(headingBlock.text_offset_y) : 0;
                                                let textTop = 4 + Math.max(0, (currentBgHeight - 25) / 2) + textOffsetY;

                                                const textObj = new fabric.Textbox(parsedHeading.cleanText, {
                                                    left: hLeft,
                                                    top: textTop,
                                                    width: hWidth,
                                                    fontSize: (headingBlock.font_size || 20) * ptToPx,
                                                    fill: '#FFFFFF',
                                                    fontWeight: 'normal',
                                                    fontFamily: 'BMA',
                                                    textAlign: headingBlock.text_align || 'center',
                                                    lineHeight: 1.15,
                                                    shadow: new fabric.Shadow({ color: 'rgba(0,0,0,0.65)', blur: 5, offsetX: 1, offsetY: 1 }),
                                                    styles: parsedHeading.styles,
                                                    selectable: true,
                                                    lockMovementX: true,
                                                    lockScalingX: true,
                                                    lockScalingY: true,
                                                    hasControls: false,
                                                    id: 'headingText'
                                                });
                                                if (typeof textObj.initDimensions === 'function') textObj.initDimensions();
                                                else if (typeof textObj._initDimensions === 'function') textObj._initDimensions();
                                                textObjects.push(textObj);

                                                if (!headingBlock.bg_height && textObj.height > 25) {
                                                    headingBg.set({ height: textObj.height + 10 });
                                                }

                                                let hOffset = headingBg.height;
                                                col0_Y = 5 + hOffset + 5;
                                                if (!isLeftLayout) {
                                                    col1_Y = 5 + hOffset + 5; // Also start right column below heading
                                                    centerLine.set({ y1: col0_Y - 5 }); // Push center line down
                                                } else {
                                                    col1_Y = 10;
                                                    centerLine.set({ y1: 4 });
                                                }
                                            }

                                            // Extract Place & Date ("સ્થળ"...) from the bottom of the content blocks so it stays on the left side
                                            let placeDateText = "";
                                            if (contentBlocks.length > 0) {
                                                let lastBlock = contentBlocks[contentBlocks.length - 1];
                                                if (lastBlock && lastBlock.text) {
                                                    let match = lastBlock.text.match(/(?:^|\n)\s*(સ્થળ[\s\S]*)$/);
                                                    if (match) {
                                                        placeDateText = match[1].trim();
                                                        lastBlock.text = lastBlock.text.substring(0, match.index).trim();
                                                    }
                                                }
                                            }

                                            // 2. Process Content Blocks (Support individual line alignment via multiple blocks)

                                            let advocateHeight = 0;
                                            if (advocateBlocks.length > 0) {
                                                advocateHeight += 10;
                                                advocateBlocks.forEach((b, idx) => {
                                                    let textLower = (b.text || '').trim().toLowerCase();
                                                    let isName = idx === 0 || textLower.includes('advocate') || textLower.includes('એડવોકેટ');
                                                    let defaultW = b.font_weight || (isName ? '900' : 'normal');
                                                    let advFont = (isName || defaultW === 'bold' || defaultW === '900') ? 'BGOTB' : 'BGOT';
                                                    let rawAdvText = (b.text || '').trim();
                                                    let convertedAdv = (typeof unicodeToGopika === 'function') ? unicodeToGopika(rawAdvText) : rawAdvText;
                                                    let parsedAdv = parseInlineBold(convertedAdv, defaultW);
                                                    let t = new fabric.Textbox(parsedAdv.cleanText, { width: colWidth, fontSize: (b.font_size || 12) * ptToPx, fontWeight: 'normal', fontFamily: advFont, textAlign: b.text_align || 'right', lineHeight: 1.1, styles: parsedAdv.styles });
                                                    if (typeof t.initDimensions === 'function') t.initDimensions(); else if (typeof t._initDimensions === 'function') t._initDimensions();
                                                    advocateHeight += t.height + 2;
                                                });
                                                advocateHeight += 12;
                                            }

                                            let placeDateHeight = 0;
                                            let cFontSizePD = 11;
                                            let cFontWeightPD = 'normal';
                                            if (contentBlocks.length > 0) {
                                                cFontSizePD = contentBlocks[0].font_size || cFontSizePD;
                                                cFontWeightPD = contentBlocks[0].font_weight || cFontWeightPD;
                                                if ((cFontWeightPD === 'bold' || cFontWeightPD === '900') && !contentBlocks[0].font_size) cFontSizePD = 12;
                                            }
                                            if (placeDateText) {
                                                let convertedPd = (typeof unicodeToGopika === 'function') ? unicodeToGopika(placeDateText) : placeDateText;
                                                let parsedPd = parseInlineBold(convertedPd, cFontWeightPD);
                                                let pdFont = (cFontWeightPD === 'bold' || cFontWeightPD === '900') ? 'BGOTB' : 'BGOT';
                                                let t = new fabric.Textbox(parsedPd.cleanText, { width: colWidth, fontSize: cFontSizePD * ptToPx, fontWeight: 'normal', fontFamily: pdFont, textAlign: 'left', lineHeight: 1.1, styles: parsedPd.styles });
                                                if (typeof t.initDimensions === 'function') t.initDimensions(); else if (typeof t._initDimensions === 'function') t._initDimensions();
                                                placeDateHeight = t.height + 15;
                                            }

                                            let contentTotalHeight = 0;
                                            let parsedContentBlocks = [];
                                            contentBlocks.forEach(b => {
                                                if (!b.text || !b.text.trim()) return;
                                                let tText = (b.text || '').trim().replace(/\n\n/g, '[PARAGRAPH]').replace(/\n/g, ' ').replace(/\[PARAGRAPH\]/g, '\n\n');
                                                let convertedText = (typeof unicodeToGopika === 'function') ? unicodeToGopika(tText) : tText;
                                                let bFontWeight = b.font_weight || 'normal';
                                                let bFontSize = b.font_size || 11;
                                                if ((bFontWeight === 'bold' || bFontWeight === '900') && !b.font_size) bFontSize = 12;
                                                let parsed = parseInlineBold(convertedText, bFontWeight);
                                                let bFontFamily = (bFontWeight === 'bold' || bFontWeight === '900') ? 'BGOTB' : 'BGOT';
                                                let bAlign = b.text_align || 'justify';
                                                if (bAlign === 'justify') bAlign = 'justify-left';

                                                let t = new fabric.Textbox(parsed.cleanText, { width: colWidth, fontSize: bFontSize * ptToPx, fontWeight: 'normal', fontFamily: bFontFamily, textAlign: bAlign, lineHeight: 1.1, styles: parsed.styles });
                                                if (typeof t.initDimensions === 'function') t.initDimensions(); else if (typeof t._initDimensions === 'function') t._initDimensions();

                                                contentTotalHeight += t.height + 8;
                                                let lines = t.textLines || (t._textLines ? t._textLines.map(l => l.join('')) : []);

                                                parsedContentBlocks.push({
                                                    origText: convertedText,
                                                    cleanText: parsed.cleanText,
                                                    lines: lines,
                                                    styles: parsed.styles,
                                                    fontSize: bFontSize,
                                                    fontFamily: bFontFamily,
                                                    align: bAlign,
                                                    fontWeight: bFontWeight,
                                                    height: t.height
                                                });
                                            });

                                            let leftColumnLimit = 99999;
                                            if (isTwoColumn) {
                                                let totalExtraPx = advocateHeight + placeDateHeight + (col1_Y - col0_Y);
                                                leftColumnLimit = (contentTotalHeight + totalExtraPx) / 2;
                                                leftColumnLimit += (window.currentLayoutOffset || 0) * (cFontSizePD * ptToPx * 1.1);
                                            }

                                            let currCol = 0;
                                            let currY = col0_Y;

                                            parsedContentBlocks.forEach(b => {
                                                if (!b.cleanText.trim()) return;

                                                if (currCol === 0 && isTwoColumn) {
                                                    if (currY + b.height <= col0_Y + leftColumnLimit + 20) {
                                                        let textObj = new fabric.Textbox(b.cleanText, { left: leftVals[0], top: currY, width: colWidth, fontSize: b.fontSize * ptToPx, fontWeight: 'normal', fill: '#000000', fontFamily: b.fontFamily, textAlign: b.align, lineHeight: 1.1, styles: b.styles });
                                                        if (typeof textObj.initDimensions === 'function') textObj.initDimensions(); else if (typeof textObj._initDimensions === 'function') textObj._initDimensions();
                                                        textObjects.push(textObj);
                                                        currY += textObj.height + 8;
                                                    } else {
                                                        let remainingHeight = (col0_Y + leftColumnLimit) - currY;
                                                        let lineHeightPx = b.fontSize * ptToPx * 1.1;
                                                        let linesThatFit = Math.ceil(remainingHeight / lineHeightPx);
                                                        if (linesThatFit > b.lines.length) linesThatFit = b.lines.length;
                                                        if (linesThatFit < 1) linesThatFit = 1;

                                                        let splitIdxInCleanText = 0;
                                                        let currentIdx = 0;
                                                        for (let i = 0; i < linesThatFit; i++) {
                                                            let lineStr = b.lines[i].trim();
                                                            if (!lineStr) continue;
                                                            let foundIdx = b.cleanText.indexOf(lineStr, currentIdx);
                                                            if (foundIdx !== -1) currentIdx = foundIdx + lineStr.length;
                                                        }
                                                        splitIdxInCleanText = currentIdx;

                                                        let cleanCount = 0;
                                                        let splitIndexInOriginal = b.origText.length;
                                                        for (let i = 0; i < b.origText.length; i++) {
                                                            if (cleanCount >= splitIdxInCleanText) {
                                                                while (i < b.origText.length && b.origText[i] === '*') i++;
                                                                splitIndexInOriginal = i;
                                                                break;
                                                            }
                                                            if (b.origText[i] !== '*') cleanCount++;
                                                        }

                                                        let leftOriginalText = b.origText.substring(0, splitIndexInOriginal).trim();
                                                        let rightOriginalText = b.origText.substring(splitIndexInOriginal).trim();

                                                        let isEndOfParagraph = b.origText.substring(Math.max(0, splitIndexInOriginal - 1), splitIndexInOriginal + 2).includes('\n');
                                                        let cAlignLeft = b.align;
                                                        if (cAlignLeft === 'justify-left' && !isEndOfParagraph) cAlignLeft = 'justify';

                                                        let leftParsed = parseInlineBold(leftOriginalText, b.fontWeight, false);
                                                        let rightParsed = parseInlineBold(rightOriginalText, b.fontWeight, leftParsed.finalIsBold);

                                                        if (leftParsed.cleanText) {
                                                            let textObjL = new fabric.Textbox(leftParsed.cleanText, { left: leftVals[0], top: currY, width: colWidth, fontSize: b.fontSize * ptToPx, fontWeight: 'normal', fill: '#000000', fontFamily: b.fontFamily, textAlign: cAlignLeft, lineHeight: 1.1, styles: leftParsed.styles });
                                                            if (typeof textObjL.initDimensions === 'function') textObjL.initDimensions(); else if (typeof textObjL._initDimensions === 'function') textObjL._initDimensions();
                                                            textObjects.push(textObjL);
                                                            col0_Y = currY + textObjL.height + 4;
                                                        } else {
                                                            col0_Y = currY;
                                                        }

                                                        currCol = 1;
                                                        currY = col1_Y;

                                                        if (rightParsed.cleanText) {
                                                            let textObjR = new fabric.Textbox(rightParsed.cleanText, { left: leftVals[1], top: currY, width: colWidth, fontSize: b.fontSize * ptToPx, fontWeight: 'normal', fill: '#000000', fontFamily: b.fontFamily, textAlign: b.align, lineHeight: 1.1, styles: rightParsed.styles });
                                                            if (typeof textObjR.initDimensions === 'function') textObjR.initDimensions(); else if (typeof textObjR._initDimensions === 'function') textObjR._initDimensions();
                                                            textObjects.push(textObjR);
                                                            currY += textObjR.height + 8;
                                                        }
                                                    }
                                                } else {
                                                    let cIdx = isTwoColumn ? 1 : 0;
                                                    let textObj = new fabric.Textbox(b.cleanText, { left: leftVals[cIdx], top: currY, width: colWidth, fontSize: b.fontSize * ptToPx, fontWeight: 'normal', fill: '#000000', fontFamily: b.fontFamily, textAlign: b.align, lineHeight: 1.1, styles: b.styles });
                                                    if (typeof textObj.initDimensions === 'function') textObj.initDimensions(); else if (typeof textObj._initDimensions === 'function') textObj._initDimensions();
                                                    textObjects.push(textObj);
                                                    currY += textObj.height + 8;
                                                }
                                            });

                                            if (isTwoColumn) {
                                                if (currCol === 0) col0_Y = currY;
                                                else col1_Y = currY;
                                            } else {
                                                col0_Y = currY;
                                            }

                                            // 3. Add to canvas
                                            textObjects.forEach(textObj => {
                                                fabricCanvas.add(textObj);
                                            });


                                        }
                                        } else {
                                            throw new Error("Parsed JSON is not an array");
                                        }
                                    } catch (e) {
                                        alert("CANVAS ERROR: " + e.message + "\n\n" + e.stack);
                                        console.error("Canvas rendering fallback:", e);
                                        const text = new fabric.Textbox("ERROR: " + e.message + "\n\n" + e.stack, {
                                            left: 20,
                                            top: 20,
                                            width: (img.width * scale) - 40,
                                            fontSize: 14,
                                            fill: 'red',
                                            fontFamily: 'monospace',
                                            textAlign: 'left'
                                        });
                                        fabricCanvas.add(text);
                                    }
                                    
                                fabricCanvas.renderAll();
                                updateHtmlPreview(); // Update HTML DOM view

                                    // Apply zoom after re-render (reset stored logical size so applyCanvasZoom recalculates)
                                    fabricCanvas._logW = null; fabricCanvas._logH = null;
                                    setTimeout(() => applyCanvasZoom(), 50);
                                }
                        });
                    }, 100);
                } else {
                    imageContainer.style.display = 'none';
                    document.getElementById('editModal').style.display = "block";
                }
            }
        }

        async function downloadCanvas(format) {
            if (!fabricCanvas) return;
            await ensureFontsLoaded();

            const id = document.getElementById('editAdvtId').value;
            const advt = advts.find(a => a._id === id);

            // Unselect objects so selection boxes don't appear in the exported image
            fabricCanvas.discardActiveObject();
            
                                fabricCanvas.renderAll();
                                updateHtmlPreview(); // Update HTML DOM view


            // Calculate EXACT multiplier to guarantee 300 DPI output width
            let targetPixels = (8 / 2.54) * 300; // default to 8cm
            if (window.customAdWidth && window.customAdWidth > 0) {
                targetPixels = (window.customAdWidth / 2.54) * 300;
            } else if (advt && advt.width > 0) {
                if (advt.unit === 'cm') targetPixels = (advt.width / 2.54) * 300;
                else if (advt.unit === 'inch') targetPixels = advt.width * 300;
            }
            let exactMultiplier = 1;
            if (fabricCanvas.width > 0) {
                exactMultiplier = targetPixels / fabricCanvas.width;
            }

            let exportOptions = { format: 'png', quality: 1, multiplier: exactMultiplier };
            let mainBorder = fabricCanvas.getObjects().find(o => o.id === 'mainBorder');

            let exportWidth = fabricCanvas.width;
            let exportHeight = fabricCanvas.height;

            if (mainBorder) {
                exportHeight = mainBorder.top + (mainBorder.height * mainBorder.scaleY) + 4;
                exportOptions.height = exportHeight;
            }

            let dataURL = fabricCanvas.toDataURL(exportOptions);

            // Helper function to inject exact 300 DPI metadata into PNG header (pHYs chunk)
            function changeDpiDataUrl(base64Image, dpi) {
                try {
                    let dataArray = new Uint8Array(atob(base64Image.split(',')[1]).split('').map(c => c.charCodeAt(0)));
                    const format = base64Image.split(',')[0];
                    let physChunk = new Uint8Array([0, 0, 0, 9, 112, 72, 89, 115, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0]);
                    let ppcX = Math.round(dpi * 39.3701);
                    physChunk[8] = physChunk[12] = (ppcX >> 24) & 0xff;
                    physChunk[9] = physChunk[13] = (ppcX >> 16) & 0xff;
                    physChunk[10] = physChunk[14] = (ppcX >> 8) & 0xff;
                    physChunk[11] = physChunk[15] = ppcX & 0xff;
                    let crcTable = [];
                    for (let n = 0; n < 256; n++) {
                        let c = n;
                        for (let k = 0; k < 8; k++) c = ((c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1));
                        crcTable[n] = c;
                    }
                    let crc = 0xffffffff;
                    for (let i = 4; i < 17; i++) crc = crcTable[(crc ^ physChunk[i]) & 0xff] ^ (crc >>> 8);
                    crc ^= 0xffffffff;
                    physChunk[17] = (crc >> 24) & 0xff; physChunk[18] = (crc >> 16) & 0xff; physChunk[19] = (crc >> 8) & 0xff; physChunk[20] = crc & 0xff;
                    let idatIdx = 0;
                    for (let i = 0; i < dataArray.length - 4; i++) {
                        if (dataArray[i] === 73 && dataArray[i + 1] === 68 && dataArray[i + 2] === 65 && dataArray[i + 3] === 84) { idatIdx = i - 4; break; }
                    }
                    if (idatIdx === 0) return base64Image;
                    let newArray = new Uint8Array(dataArray.length + 21);
                    newArray.set(dataArray.subarray(0, idatIdx), 0);
                    newArray.set(physChunk, idatIdx);
                    newArray.set(dataArray.subarray(idatIdx), idatIdx + 21);
                    let binary = '';
                    for (let i = 0; i < newArray.length; i++) binary += String.fromCharCode(newArray[i]);
                    return format + ',' + btoa(binary);
                } catch (e) { return base64Image; }
            }

            // Force 300 DPI metadata in the image header
            dataURL = changeDpiDataUrl(dataURL, 300);

            if (format === 'png') {
                const link = document.createElement('a');
                link.download = 'advertisement_300dpi.png';
                link.href = dataURL;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            } else if (format === 'pdf') {
                const { jsPDF } = window.jspdf;

                let pdfUnit = 'px';
                let pdfWidth = exportWidth;
                let pdfHeight = exportHeight;

                if (window.customAdWidth && window.customAdWidth > 0) {
                    pdfUnit = 'cm';
                    pdfWidth = window.customAdWidth;
                    pdfHeight = (exportHeight / exportWidth) * pdfWidth;
                } else if (advt && advt.width > 0) {
                    pdfUnit = (advt.unit || 'cm').toLowerCase();
                    pdfWidth = parseFloat(advt.width);

                    if (advt.height > 0) {
                        if (mainBorder) {
                            let ratio = exportHeight / fabricCanvas.height;
                            pdfHeight = parseFloat(advt.height) * ratio;
                        } else {
                            pdfHeight = parseFloat(advt.height);
                        }
                    } else {
                        pdfHeight = (exportHeight / exportWidth) * pdfWidth;
                    }
                }

                const pdf = new jsPDF({
                    orientation: pdfWidth > pdfHeight ? 'l' : 'p',
                    unit: pdfUnit,
                    format: [pdfWidth, pdfHeight]
                });

                pdf.addImage(dataURL, 'PNG', 0, 0, pdfWidth, pdfHeight);
                pdf.save('advertisement.pdf');
            } else if (format === 'tif') {
                const img = new Image();
                img.onload = function () {
                    const canvas = document.createElement('canvas');
                    canvas.width = img.width;
                    canvas.height = img.height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);

                    let ifd = {
                        t282: [300, 1], // XResolution
                        t283: [300, 1], // YResolution
                        t296: [2]       // ResolutionUnit (Inch)
                    };

                    let tiffBuffer;
                    try {
                        tiffBuffer = UTIF.encodeImage(imgData.data.buffer, canvas.width, canvas.height, ifd);
                    } catch (e) {
                        tiffBuffer = UTIF.encodeImage(imgData.data.buffer, canvas.width, canvas.height);
                    }

                    const blob = new Blob([tiffBuffer], { type: 'image/tiff' });
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.download = 'advertisement_300dpi.tif';
                    link.href = url;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    URL.revokeObjectURL(url);
                };
                img.src = dataURL;
            }
        }

        function setupCanvasEvents() {
            fabricCanvas.on('selection:created', handleSelection);
            fabricCanvas.on('selection:updated', handleSelection);
            fabricCanvas.on('text:selection:changed', handleSelection);
            fabricCanvas.on('selection:cleared', function () {
                const tb = document.getElementById('canvasToolbar');
                if (tb) {
                    tb.style.opacity = '0.5';
                    tb.style.pointerEvents = 'none';
                }
            });
            fabricCanvas.on('object:scaling', function (e) {
                if (e.target && e.target.id === 'mainBorder') {
                    const border = e.target;
                    if (border.scaleY !== 1) {
                        const newHeight = border.height * border.scaleY;
                        const centerLine = fabricCanvas.getObjects().find(o => o.id === 'centerLine');
                        if (centerLine) {
                            centerLine.set({ y2: border.top + newHeight });
                        }
                    }
                    if (border.scaleX !== 1) {
                        const newBorderWidth = border.width * border.scaleX;
                        const newWidthCm = Math.max(3.0, Math.min(20.0, Math.round(((newBorderWidth + 8) / 96 * 2.54) * 10) / 10));
                        const widthInput = document.getElementById('adWidthInput');
                        if (widthInput) widthInput.value = newWidthCm.toFixed(1);
                    }
                    
                                fabricCanvas.renderAll();
                                updateHtmlPreview(); // Update HTML DOM view

                } else if (e.target && e.target.id === 'headingBg') {
                    const bg = e.target;
                    const newHeight = Math.max(15, Math.round(bg.height * bg.scaleY));
                    const bgInput = document.querySelector('.block-heading-height');
                    if (bgInput) bgInput.value = newHeight;
                }
            });
            fabricCanvas.on('object:moving', function (e) {
                if (e.target && e.target.id === 'headingText') {
                    e.target.set({ left: 4 });
                }
            });
            fabricCanvas.on('object:modified', function (e) {
                if (e.target && e.target.id === 'mainBorder') {
                    const border = e.target;
                    let needsUpdate = false;
                    if (border.scaleY !== 1) {
                        window.customBorderHeight = Math.round(border.height * border.scaleY);
                        border.set({ height: window.customBorderHeight, scaleY: 1 });
                        needsUpdate = true;
                    }
                    if (border.scaleX !== 1) {
                        const newBorderWidth = border.width * border.scaleX;
                        window.customAdWidth = Math.max(3.0, Math.min(20.0, Math.round(((newBorderWidth + 8) / 96 * 2.54) * 10) / 10));
                        const widthInput = document.getElementById('adWidthInput');
                        if (widthInput) widthInput.value = window.customAdWidth.toFixed(1);
                        border.set({ scaleX: 1 });
                        needsUpdate = true;
                    }
                    if (needsUpdate) {
                        updateCanvasFromText();
                    }
                } else if (e.target && e.target.id === 'headingBg') {
                    const bg = e.target;
                    const newHeight = Math.max(15, Math.round(bg.height * bg.scaleY));
                    bg.set({ height: newHeight, scaleY: 1 });
                    const bgInput = document.querySelector('.block-heading-height');
                    if (bgInput) bgInput.value = newHeight;
                    const bgHidden = document.querySelector('.block-heading-height-val');
                    if (bgHidden) bgHidden.value = newHeight;
                    updateCanvasFromText();
                } else if (e.target && e.target.id === 'headingText') {
                    const textObj = e.target;
                    const bg = fabricCanvas.getObjects().find(o => o.id === 'headingBg');
                    if (bg) {
                        const baseTop = 4 + Math.max(0, (bg.height - 25) / 2);
                        const offset = Math.round(textObj.top - baseTop);
                        const yInput = document.querySelector('.block-heading-text-y');
                        if (yInput) yInput.value = offset;
                        const yHidden = document.querySelector('.block-heading-text-y-val');
                        if (yHidden) yHidden.value = offset;
                        updateCanvasFromText();
                    }
                }
            });
        }

        function handleSelection(e) {
            const obj = fabricCanvas.getActiveObject();
            if (!obj || obj.type !== 'textbox') return;
            const tb = document.getElementById('canvasToolbar');
            if (tb) {
                tb.style.opacity = '1';
                tb.style.pointerEvents = 'auto';

                let currentFontSize = obj.fontSize;
                let currentFontWeight = obj.fontWeight;

                if (obj.isEditing && obj.selectionStart !== obj.selectionEnd) {
                    const styles = obj.getSelectionStyles() || [];
                    if (styles.length > 0) {
                        if (styles[0].fontSize) currentFontSize = styles[0].fontSize;
                        if (styles[0].fontWeight) currentFontWeight = styles[0].fontWeight;
                    }
                }

                document.getElementById('tbFontSize').value = Math.round(currentFontSize);

                const btnBold = document.getElementById('tbBold');
                if (currentFontWeight === 'bold' || currentFontWeight === '900') {
                    btnBold.classList.add('bg-slate-200', 'border-slate-400');
                } else {
                    btnBold.classList.remove('bg-slate-200', 'border-slate-400');
                }
            }
        }

        function updateSelectedText(property, value) {
            if (!fabricCanvas) return;
            const obj = fabricCanvas.getActiveObject();
            if (!obj || obj.type !== 'textbox') return;

            if (property === 'fontSize' && obj.isEditing && obj.selectionStart !== obj.selectionEnd) {
                obj.setSelectionStyles({ fontSize: parseInt(value, 10) });
            } else {
                if (property === 'fontSize') {
                    obj.set('fontSize', parseInt(value, 10));
                } else if (property === 'textAlign') {
                    obj.set('textAlign', value);
                }
            }
            
                                fabricCanvas.renderAll();
                                updateHtmlPreview(); // Update HTML DOM view

        }

        function toggleBold() {
            if (!fabricCanvas) return;
            const obj = fabricCanvas.getActiveObject();
            if (!obj || obj.type !== 'textbox') return;

            const btnBold = document.getElementById('tbBold');

            if (obj.isEditing && obj.selectionStart !== obj.selectionEnd) {
                const styles = obj.getSelectionStyles() || [];
                let isBold = false;
                if (styles.length > 0 && (styles[0].fontWeight === 'bold' || styles[0].fontWeight === '900')) {
                    isBold = true;
                }

                obj.setSelectionStyles({ fontWeight: isBold ? 'normal' : 'bold' });

                if (!isBold) {
                    btnBold.classList.add('bg-slate-200', 'border-slate-400');
                } else {
                    btnBold.classList.remove('bg-slate-200', 'border-slate-400');
                }
            } else {
                const isBold = obj.fontWeight === 'bold' || obj.fontWeight === '900';
                obj.set('fontWeight', isBold ? 'normal' : 'bold');

                if (!isBold) {
                    btnBold.classList.add('bg-slate-200', 'border-slate-400');
                } else {
                    btnBold.classList.remove('bg-slate-200', 'border-slate-400');
                }
            }

            
                                fabricCanvas.renderAll();
                                updateHtmlPreview(); // Update HTML DOM view

        }

        function updateCanvasFromText() {
            const id = document.getElementById('editAdvtId').value;
            const advtIndex = advts.findIndex(a => a._id === id);
            if (advtIndex !== -1) {
                // Gather data from dynamic blocks and rebuild JSON
                const container = document.getElementById('editBlocksContainer');
                const inputs = container.querySelectorAll('.block-editor-input');
                let newJsonStr = advts[advtIndex].translated_text; // Default to existing

                try {
                    let parsedData = JSON.parse(advts[advtIndex].translated_text);
                    let isWrapped = false;
                    let blocks = [];
                    if (Array.isArray(parsedData)) {
                        blocks = parsedData;
                    } else if (parsedData && Array.isArray(parsedData.gujarati_text)) {
                        blocks = parsedData.gujarati_text;
                        isWrapped = true;
                    }

                    if (inputs.length === blocks.length) {
                        inputs.forEach((ta, idx) => {
                            blocks[idx].text = ta.value;
                            const parent = ta.parentElement;
                            const sizeInput = parent.querySelector('.block-format-size');
                            if (sizeInput) blocks[idx].font_size = parseFloat(sizeInput.value);
                            const boldInput = parent.querySelector('.block-format-bold-val');
                            if (boldInput) blocks[idx].font_weight = boldInput.value;
                            const alignInput = parent.querySelector('.block-format-align-val');
                            if (alignInput) blocks[idx].text_align = alignInput.value;
                            const layoutInput = parent.querySelector('.block-format-layout-val');
                            if (layoutInput) blocks[idx].layout_position = layoutInput.value;
                            const bgHeightInput = parent.querySelector('.block-heading-height') || parent.querySelector('.block-heading-height-val');
                            if (bgHeightInput && bgHeightInput.value) blocks[idx].bg_height = parseFloat(bgHeightInput.value);
                            const textYInput = parent.querySelector('.block-heading-text-y') || parent.querySelector('.block-heading-text-y-val');
                            if (textYInput && textYInput.value !== '') blocks[idx].text_offset_y = parseFloat(textYInput.value);
                        });
                        let newJson = blocks;
                        if (isWrapped || window.currentLayoutOffset !== 0 || window.customBorderHeight || window.customAdWidth) {
                            newJson = {
                                gujarati_text: blocks,
                                layout_offset: window.currentLayoutOffset || 0,
                                border_height: window.customBorderHeight || null,
                                ad_width: window.customAdWidth || null,
                                column_count: window.customColumnCount || 2
                            };
                        }
                        newJsonStr = JSON.stringify(newJson);
                    } else if (inputs.length === 1) {
                        newJsonStr = inputs[0].value;
                    }
                } catch (e) {
                    if (inputs.length === 1) {
                        newJsonStr = inputs[0].value;
                    }
                }

                // Update hidden textarea and local data
                document.getElementById('editTranslationText').value = newJsonStr;
                advts[advtIndex].translated_text = newJsonStr;

                // Auto-save to database instantly
                fetch(`/api/advt/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ translated_text: newJsonStr })
                }).catch(e => console.error("Auto-save failed", e));

                // Preserve scroll position of the modal
                const modal = document.getElementById('editModal');
                const scrollTop = modal.scrollTop;

                // Re-open modal to trigger redraw (this will also re-render blocks with new data)
                openEditModal(id);

                // Restore scroll after modal is fully re-initialized
                setTimeout(() => {
                    modal.scrollTop = scrollTop;
                }, 100);
            }
        }

        function adjustLayoutOffset(delta) {
            window.currentLayoutOffset = (window.currentLayoutOffset || 0) + delta;
            document.getElementById('layoutOffsetDisplay').innerText = window.currentLayoutOffset > 0 ? '+' + window.currentLayoutOffset : window.currentLayoutOffset;
            updateCanvasFromText();
        }

        function adjustAdWidth(delta) {
            let current = parseFloat(document.getElementById('adWidthInput').value) || window.customAdWidth || 6.2;
            current = Math.max(3.0, Math.min(20.0, Math.round((current + delta) * 10) / 10));
            setAdWidth(current);
        }

        function setAdWidth(val) {
            let num = parseFloat(val);
            if (isNaN(num) || num < 3.0) num = 6.2;
            window.customAdWidth = Math.max(3.0, Math.min(20.0, Math.round(num * 10) / 10));
            const widthInput = document.getElementById('adWidthInput');
            if (widthInput) widthInput.value = window.customAdWidth.toFixed(1);
            updateCanvasFromText();
        }

        async function saveTranslation() {
            const id = document.getElementById('editAdvtId').value;

            // Gather latest text from dynamic blocks before saving
            const container = document.getElementById('editBlocksContainer');
            const inputs = container.querySelectorAll('.block-editor-input');
            let textToSave = document.getElementById('editTranslationText').value;

            try {
                let parsedData = JSON.parse(textToSave);
                let isWrapped = false;
                let blocks = [];
                if (Array.isArray(parsedData)) {
                    blocks = parsedData;
                } else if (parsedData && Array.isArray(parsedData.gujarati_text)) {
                    blocks = parsedData.gujarati_text;
                    isWrapped = true;
                }

                if (inputs.length === blocks.length) {
                    inputs.forEach((ta, idx) => {
                        blocks[idx].text = ta.value;
                        const parent = ta.parentElement;
                        const sizeInput = parent.querySelector('.block-format-size');
                        if (sizeInput) blocks[idx].font_size = parseFloat(sizeInput.value);
                        const boldInput = parent.querySelector('.block-format-bold-val');
                        if (boldInput) blocks[idx].font_weight = boldInput.value;
                        const alignInput = parent.querySelector('.block-format-align-val');
                        if (alignInput) blocks[idx].text_align = alignInput.value;
                        const layoutInput = parent.querySelector('.block-format-layout-val');
                        if (layoutInput) blocks[idx].layout_position = layoutInput.value;
                        const bgHeightInput = parent.querySelector('.block-heading-height') || parent.querySelector('.block-heading-height-val');
                        if (bgHeightInput && bgHeightInput.value) blocks[idx].bg_height = parseFloat(bgHeightInput.value);
                        const textYInput = parent.querySelector('.block-heading-text-y') || parent.querySelector('.block-heading-text-y-val');
                        if (textYInput && textYInput.value !== '') blocks[idx].text_offset_y = parseFloat(textYInput.value);
                    });
                    let newJson = blocks;
                    if (isWrapped || window.currentLayoutOffset !== 0 || window.customBorderHeight || window.customAdWidth) {
                        newJson = {
                            gujarati_text: blocks,
                            layout_offset: window.currentLayoutOffset || 0,
                            border_height: window.customBorderHeight || null,
                            ad_width: window.customAdWidth || null,
                            column_count: window.customColumnCount || 2
                        };
                    }
                    textToSave = JSON.stringify(newJson);
                } else if (inputs.length === 1) {
                    textToSave = inputs[0].value;
                }
            } catch (e) {
                if (inputs.length === 1) {
                    textToSave = inputs[0].value;
                }
            }

            try {
                const response = await fetch(`/api/advt/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ translated_text: textToSave })
                });

                if (response.ok) {
                    closeEditModal();
                    loadAdvts();
                } else {
                    alert("Failed to save.");
                }
            } catch (e) {
                alert("Error: " + e.message);
            }
        }

        async function deleteAdvt(id) {
            if (confirm("Are you sure you want to delete this advertisement?")) {
                try {
                    const response = await fetch(`/api/advt/${id}`, { method: 'DELETE' });
                    if (response.ok) {
                        loadAdvts();
                    }
                } catch (e) {
                    alert("Error: " + e.message);
                }
            }
        }

        function toggleDimensions() {
            const unitContainer = document.getElementById('unitContainer');
            const heightContainer = document.getElementById('heightContainer');
            const widthContainer = document.getElementById('widthContainer');
            const heightInput = document.getElementById('advtHeight');
            const widthInput = document.getElementById('advtWidth');

            unitContainer.classList.remove('hidden');
            heightContainer.classList.remove('hidden');
            widthContainer.classList.remove('hidden');
            heightInput.removeAttribute('required');
            widthInput.removeAttribute('required');
        }

        // Modals logic
        function toggleLegalNoticeOption() {
            const select = document.getElementById('advtType');
            const legalNoticeContainer = document.getElementById('legalNoticeContainer');
            const processingOptionsContainer = document.getElementById('processingOptionsContainer');

            if (!select) return;
            const selectedText = select.options[select.selectedIndex]?.text || '';
            const selectedValue = select.value || '';
            const isNotice = selectedText.toLowerCase().trim() === 'notice' || selectedValue.toLowerCase().trim() === 'notice';
            const isLegalNotice = selectedText.toLowerCase().includes('legal notice') || selectedValue.toLowerCase().includes('legal notice');

            const blankTemplateContainer = document.getElementById('blankTemplateContainer');
            if (blankTemplateContainer) {
                if (isLegalNotice) {
                    blankTemplateContainer.classList.add('hidden');
                } else {
                    blankTemplateContainer.classList.remove('hidden');
                }
            }

            if (isNotice) {
                if (legalNoticeContainer) legalNoticeContainer.classList.remove('hidden');
                if (processingOptionsContainer) processingOptionsContainer.classList.remove('hidden');
            } else {
                if (legalNoticeContainer) {
                    legalNoticeContainer.classList.add('hidden');
                    document.getElementById('optLegalNotice').checked = false;
                }
                if (processingOptionsContainer) {
                    processingOptionsContainer.classList.add('hidden');
                }
            }
        }

        function openUploadModal() {
            document.getElementById('uploadModal').style.display = "block";
            toggleDimensions();
            toggleLegalNoticeOption();
        }
        function closeUploadModal() { document.getElementById('uploadModal').style.display = "none"; }
        function closeEditModal() { document.getElementById('editModal').style.display = "none"; }

        window.onclick = function (event) {
            if (event.target == document.getElementById('uploadModal')) closeUploadModal();
            if (event.target == document.getElementById('editModal')) closeEditModal();
        }

        // Init
        document.addEventListener('DOMContentLoaded', () => {
            loadAdvts();
            loadCategories();
            toggleDimensions();
        });
    