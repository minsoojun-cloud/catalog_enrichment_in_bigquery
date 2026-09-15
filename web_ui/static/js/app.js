// Frontend Application Logic for AI Commerce Search Catalog Mapper & Enricher (Japanese Edition)

let APP_STATE = {
    datasetId: null,
    filename: "",
    sourceColumns: [],
    previewRows: [],
    totalRows: 0,
    rawBigQuerySchema: [],
    mappableFields: [],
    enrichmentPresets: [],
    mappingConfig: {},
    enrichmentRules: [],
    activeSchemaGroup: 'ALL',
    editingRuleIndex: null,
    currentJobId: null,
    jobPollInterval: null,
    processedResults: [],
    // Full row count of the completed job. processedResults is capped at 20 by the
    // backend preview, so this is what the JSONL export size/count must be based on.
    totalProcessedRows: 0
};

document.addEventListener("DOMContentLoaded", async () => {
    setupDragAndDrop();
    await loadMetadata();
    await loadSampleData();
});

function setupDragAndDrop() {
    const dropzone = document.getElementById("dropzone");
    if (!dropzone) return;

    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("border-blue-600", "bg-blue-50/50");
    });
    dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("border-blue-600", "bg-blue-50/50");
    });
    dropzone.addEventListener("drop", async (e) => {
        e.preventDefault();
        dropzone.classList.remove("border-blue-600", "bg-blue-50/50");
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            await uploadFileObject(e.dataTransfer.files[0]);
        }
    });
}

async function loadMetadata() {
    try {
        const res = await fetch("/api/metadata");
        const data = await res.json();
        APP_STATE.rawBigQuerySchema = data.raw_bigquery_schema || [];
        APP_STATE.mappableFields = data.mappable_fields || [];
        APP_STATE.enrichmentPresets = data.enrichment_presets || [];

        if (data.project_id) {
            document.getElementById("globalProjectId").value = data.project_id;
            document.getElementById("bqLoadProject").value = data.project_id;
        }
        if (data.default_model) {
            const modelSelect = document.getElementById("globalModelName");
            const exists = Array.from(modelSelect.options).some((o) => o.value === data.default_model);
            if (!exists) {
                const opt = document.createElement("option");
                opt.value = data.default_model;
                opt.textContent = `${data.default_model} (推奨)`;
                modelSelect.insertBefore(opt, modelSelect.firstChild);
            }
            modelSelect.value = data.default_model;
        }
        if (data.default_dataset) {
            document.getElementById("bqLoadDataset").value = data.default_dataset;
        }
        if (data.default_table) {
            document.getElementById("bqLoadTable").value = data.default_table;
        }

        const presetSelect = document.getElementById("presetSelect");
        presetSelect.innerHTML = `<option value="" class="bg-slate-800">-- 推奨 Enrichment プリセットを選択 --</option>`;
        APP_STATE.enrichmentPresets.forEach((p) => {
            const opt = document.createElement("option");
            opt.value = p.id;
            opt.className = "bg-slate-800 text-white";
            opt.textContent = p.name;
            presetSelect.appendChild(opt);
        });

        if (APP_STATE.enrichmentRules.length === 0 && APP_STATE.enrichmentPresets.length >= 2) {
            const tagPreset = APP_STATE.enrichmentPresets[0];
            const descPreset = APP_STATE.enrichmentPresets[2];
            APP_STATE.enrichmentRules = [
                createRuleFromPreset(tagPreset),
                createRuleFromPreset(descPreset)
            ];
        }

        renderSchemaMappingTable();
        renderEnrichmentRulesTable();
    } catch (err) {
        console.error("Failed to load metadata:", err);
    }
}

function createRuleFromPreset(preset) {
    return {
        id: "rule_" + Math.random().toString(36).substring(2, 8),
        enabled: true,
        name: preset.name,
        source_fields: [...(preset.recommended_sources || ["title", "brands"])],
        use_google_search: preset.use_google_search !== false,
        enable_verification: true,
        target_field: preset.target_field || "tags",
        output_format: preset.output_format || "json_array",
        prompt: preset.prompt || ""
    };
}

// ============================================================================
// STEP 1: File Upload & Sample Data Loading
// ============================================================================

async function loadSampleData() {
    try {
        const res = await fetch("/api/sample", { method: "POST" });
        const data = await res.json();
        applyDatasetResponse(data);
    } catch (err) {
        alert("サンプルデータの読み込みに失敗しました: " + err.message);
    }
}

async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    await uploadFileObject(file);
}

async function uploadFileObject(file) {
    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch("/api/upload", {
            method: "POST",
            body: formData
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "ファイルアップロードエラー");
        }
        const data = await res.json();
        applyDatasetResponse(data);
    } catch (err) {
        alert("ファイルアップロードに失敗しました: " + err.message);
    }
}

function applyDatasetResponse(data) {
    APP_STATE.datasetId = data.dataset_id;
    APP_STATE.filename = data.filename;
    APP_STATE.sourceColumns = data.columns || [];
    APP_STATE.previewRows = data.preview_rows || [];
    APP_STATE.totalRows = data.total_rows || 0;

    if (data.auto_mapping) {
        APP_STATE.mappingConfig = data.auto_mapping;
    }

    document.getElementById("datasetInfoBar").classList.remove("hidden");
    document.getElementById("datasetFilename").textContent = APP_STATE.filename;
    document.getElementById("datasetRowCount").textContent = `${APP_STATE.totalRows.toLocaleString()} 件`;

    const colContainer = document.getElementById("datasetColumnsList");
    colContainer.innerHTML = `<span class="font-semibold text-slate-700 mr-1">検出されたカラム (${APP_STATE.sourceColumns.length}個):</span>`;
    APP_STATE.sourceColumns.forEach((col) => {
        const span = document.createElement("span");
        span.className = "bg-white border border-slate-300 px-2 py-0.5 rounded font-mono text-slate-700";
        span.textContent = col;
        colContainer.appendChild(span);
    });

    renderSourcePreviewTable();
    document.getElementById("sourcePreviewContainer").classList.remove("hidden");

    renderSchemaMappingTable();
    renderEnrichmentRulesTable();
}

function renderSourcePreviewTable() {
    const thead = document.getElementById("sourcePreviewHead");
    const tbody = document.getElementById("sourcePreviewBody");
    thead.innerHTML = "";
    tbody.innerHTML = "";

    if (!APP_STATE.sourceColumns.length) return;

    const trHead = document.createElement("tr");
    APP_STATE.sourceColumns.forEach((col) => {
        const th = document.createElement("th");
        th.className = "py-2 px-3 font-mono whitespace-nowrap border-r border-slate-200 last:border-none";
        th.textContent = col;
        trHead.appendChild(th);
    });
    thead.appendChild(trHead);

    APP_STATE.previewRows.slice(0, 5).forEach((row) => {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-50";
        APP_STATE.sourceColumns.forEach((col) => {
            const td = document.createElement("td");
            td.className = "py-2 px-3 border-r border-slate-200 last:border-none max-w-xs truncate";
            const val = row[col];
            td.textContent = val !== undefined && val !== null ? String(val) : "";
            td.title = val !== undefined && val !== null ? String(val) : "";
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
}

function togglePreviewTable() {
    const container = document.getElementById("sourcePreviewContainer");
    container.classList.toggle("hidden");
}


// ============================================================================
// STEP 2: BigQuery Schema Field Mapping UI
// ============================================================================

function toggleSchemaMappingSection() {
    const body = document.getElementById("schemaMappingSectionBody");
    const icon = document.getElementById("toggleSchemaSectionIcon");
    const text = document.getElementById("toggleSchemaSectionText");
    if (!body) return;

    const isHidden = body.classList.toggle("hidden");
    if (isHidden) {
        if (icon) icon.className = "fa-solid fa-chevron-down text-blue-600";
        if (text) text.textContent = "展開する";
    } else {
        if (icon) icon.className = "fa-solid fa-chevron-up text-slate-500";
        if (text) text.textContent = "折りたたむ";
    }
}

function updateSchemaMappingSummaryBadge(enrichedTargetMap) {
    const badge = document.getElementById("schemaMappingSummaryBadge");
    if (!badge) return;

    let mappedCount = 0;
    let idOk = false;
    let titleOk = false;

    APP_STATE.mappableFields.forEach((f) => {
        const cfg = APP_STATE.mappingConfig[f.id] || {};
        const hasCol = cfg.mode === "column" && cfg.source_column;
        const hasStatic = cfg.mode === "static" && cfg.default_value;
        const hasEnrich = enrichedTargetMap && enrichedTargetMap[f.id] && enrichedTargetMap[f.id].length > 0;

        if (hasCol || hasStatic || hasEnrich) {
            mappedCount++;
            if (f.id === "id") idOk = true;
            if (f.id === "title") titleOk = true;
        }
    });

    if (idOk && titleOk) {
        badge.className = "bg-emerald-100 text-emerald-800 border border-emerald-200 text-xs font-semibold px-2.5 py-0.5 rounded-full";
        badge.innerHTML = `<i class="fa-solid fa-check-circle mr-1"></i>設定済: ${mappedCount} 項目 (必須 id・title OK)`;
    } else {
        badge.className = "bg-amber-100 text-amber-800 border border-amber-200 text-xs font-semibold px-2.5 py-0.5 rounded-full";
        badge.innerHTML = `<i class="fa-solid fa-triangle-exclamation mr-1"></i>設定済: ${mappedCount} 項目 (必須 id・title 要確認)`;
    }
}

function filterSchemaGroup(groupName) {
    APP_STATE.activeSchemaGroup = groupName;
    document.querySelectorAll("#schemaGroupTabs .schema-tab").forEach((btn) => {
        if (btn.getAttribute("data-group") === groupName) {
            btn.className = "schema-tab active px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white transition";
        } else {
            btn.className = "schema-tab px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 transition";
        }
    });
    renderSchemaMappingTable();
}

async function autoSuggestMappings() {
    if (!APP_STATE.sourceColumns.length) {
        alert("先に CSV/JSONL ファイルをアップロードするか、サンプルデータを読み込んでください。");
        return;
    }
    try {
        const res = await fetch("/api/mapping/auto-suggest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ columns: APP_STATE.sourceColumns })
        });
        const data = await res.json();
        if (data.auto_mapping) {
            APP_STATE.mappingConfig = data.auto_mapping;
            renderSchemaMappingTable();
        }
    } catch (err) {
        console.error("Auto suggest error:", err);
    }
}

function renderSchemaMappingTable() {
    const tbody = document.getElementById("schemaMappingTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    const searchQuery = (document.getElementById("schemaSearchInput")?.value || "").toLowerCase().trim();

    const enrichedTargetMap = {};
    APP_STATE.enrichmentRules.forEach((rule) => {
        if (rule.enabled && rule.target_field) {
            if (!enrichedTargetMap[rule.target_field]) {
                enrichedTargetMap[rule.target_field] = [];
            }
            enrichedTargetMap[rule.target_field].push(rule.name);
        }
    });

    updateSchemaMappingSummaryBadge(enrichedTargetMap);

    const filteredFields = APP_STATE.mappableFields.filter((f) => {
        if (APP_STATE.activeSchemaGroup !== "ALL" && f.group !== APP_STATE.activeSchemaGroup) {
            return false;
        }
        if (searchQuery) {
            return f.id.toLowerCase().includes(searchQuery) ||
                   f.label.toLowerCase().includes(searchQuery) ||
                   (f.description && f.description.toLowerCase().includes(searchQuery));
        }
        return true;
    });

    filteredFields.forEach((field) => {
        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-50/80 transition";

        const currentMap = APP_STATE.mappingConfig[field.id] || {
            mode: field.default ? "static" : "none",
            source_column: "",
            default_value: field.default || ""
        };
        APP_STATE.mappingConfig[field.id] = currentMap;

        // 1. Field Name & Label
        const tdName = document.createElement("td");
        tdName.className = "py-3 px-4";
        const isRequired = field.mode === "REQUIRED";
        tdName.innerHTML = `
            <div class="flex items-center gap-1.5">
                <span class="font-mono font-bold text-slate-800">${field.id}</span>
                ${isRequired ? `<span class="text-[10px] font-bold px-1.5 py-0.2 rounded schema-badge-required">REQUIRED</span>` : ""}
            </div>
            <div class="text-slate-500 text-[11px] mt-0.5">${field.label}</div>
        `;

        // 2. Type & Mode Badges
        const tdType = document.createElement("td");
        tdType.className = "py-3 px-3";
        let modeBadgeClass = "schema-badge-nullable";
        if (field.mode === "REPEATED") modeBadgeClass = "schema-badge-repeated";
        if (field.type === "RECORD") modeBadgeClass = "schema-badge-record";

        tdType.innerHTML = `
            <div class="flex flex-col gap-1">
                <span class="font-mono text-[11px] font-semibold text-slate-700">${field.type}</span>
                <span class="text-[10px] font-semibold px-1.5 py-0.5 rounded w-fit ${modeBadgeClass}">${field.mode}</span>
            </div>
        `;

        // 3. Mapping Mode Selector
        const tdMode = document.createElement("td");
        tdMode.className = "py-3 px-3";
        const selectMode = document.createElement("select");
        selectMode.className = "w-full p-1.5 border border-slate-300 rounded-md bg-white text-xs font-medium focus:outline-none focus:border-blue-500";
        selectMode.innerHTML = `
            <option value="column" ${currentMap.mode === "column" ? "selected" : ""}>📥 入力カラムとマッチング</option>
            <option value="static" ${currentMap.mode === "static" ? "selected" : ""}>📌 固定デフォルト値を設定</option>
            <option value="none" ${currentMap.mode === "none" ? "selected" : ""}>⚪ マッピングなし (None)</option>
        `;
        selectMode.onchange = (e) => {
            APP_STATE.mappingConfig[field.id].mode = e.target.value;
            renderSchemaMappingTable();
        };
        tdMode.appendChild(selectMode);

        // 4. Value Selector
        const tdVal = document.createElement("td");
        tdVal.className = "py-3 px-4";

        if (currentMap.mode === "column") {
            const colSelect = document.createElement("select");
            colSelect.className = "w-full p-1.5 border border-blue-300 rounded-md bg-blue-50/30 text-xs font-mono text-blue-950 focus:outline-none focus:border-blue-600";
            let optionsHtml = `<option value="">-- 入力カラムを選択 --</option>`;
            APP_STATE.sourceColumns.forEach((col) => {
                const sel = currentMap.source_column === col ? "selected" : "";
                optionsHtml += `<option value="${col}" ${sel}>${col}</option>`;
            });
            colSelect.innerHTML = optionsHtml;
            colSelect.onchange = (e) => {
                APP_STATE.mappingConfig[field.id].source_column = e.target.value;
            };
            tdVal.appendChild(colSelect);
        } else if (currentMap.mode === "static") {
            const inputStatic = document.createElement("input");
            inputStatic.type = "text";
            inputStatic.value = currentMap.default_value || "";
            inputStatic.placeholder = "固定デフォルト値を入力 (例: ja, PRIMARY, IN_STOCK)";
            inputStatic.className = "w-full p-1.5 border border-slate-300 rounded-md bg-white text-xs font-mono focus:outline-none focus:border-blue-500";
            inputStatic.oninput = (e) => {
                APP_STATE.mappingConfig[field.id].default_value = e.target.value;
            };
            tdVal.appendChild(inputStatic);
        } else {
            tdVal.innerHTML = `<span class="text-slate-400 italic text-xs">未割当 (null または空配列)</span>`;
        }

        // 5. Enrichment Status & Description
        const tdEnrich = document.createElement("td");
        tdEnrich.className = "py-3 px-4";
        const enrichedBy = enrichedTargetMap[field.id];

        if (enrichedBy && enrichedBy.length > 0) {
            tdEnrich.innerHTML = `
                <div class="flex items-center gap-1.5 text-emerald-700 font-semibold text-xs bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-md w-fit">
                    <i class="fa-solid fa-wand-magic-sparkles text-emerald-600"></i>
                    <span>AI Enrichment 対象: ${enrichedBy.join(", ")}</span>
                </div>
                <div class="text-[11px] text-slate-400 mt-1">${field.description || ""}</div>
            `;
        } else {
            tdEnrich.innerHTML = `
                <div class="text-xs text-slate-500">${field.description || ""}</div>
            `;
        }

        tr.appendChild(tdName);
        tr.appendChild(tdType);
        tr.appendChild(tdMode);
        tr.appendChild(tdVal);
        tr.appendChild(tdEnrich);
        tbody.appendChild(tr);
    });
}


// ============================================================================
// STEP 3: Multi-Rule Google Search & Gemini Enrichment Table (画面下部テーブルリスト)
// ============================================================================

function addPresetRule() {
    const presetSelect = document.getElementById("presetSelect");
    const presetId = presetSelect.value;
    if (!presetId) {
        alert("追加する推奨 Enrichment プリセットを先に選択してください。");
        return;
    }
    const preset = APP_STATE.enrichmentPresets.find((p) => p.id === presetId);
    if (!preset) return;

    APP_STATE.enrichmentRules.push(createRuleFromPreset(preset));
    presetSelect.value = "";
    renderEnrichmentRulesTable();
    renderSchemaMappingTable();
}

function addBlankEnrichmentRule() {
    const newRule = {
        id: "rule_" + Math.random().toString(36).substring(2, 8),
        enabled: true,
        name: `カスタム Enrichment ルール #${APP_STATE.enrichmentRules.length + 1}`,
        source_fields: ["title", "brands"],
        use_google_search: true,
        enable_verification: true,
        target_field: "tags",
        output_format: "json_array",
        prompt: `# 役割\n入力された商品情報をもとに、Google Search および Gemini を活用して補強データを生成してください。\n\n# 入力情報\n- 商品名: {title}\n- ブランド: {brands}\n\n# 出力形式\n必ず以下の JSON 配列形式のみで回答してください:\n["キーワード1", "キーワード2"]`
    };
    APP_STATE.enrichmentRules.push(newRule);
    renderEnrichmentRulesTable();
    renderSchemaMappingTable();
}

function removeEnrichmentRule(index) {
    APP_STATE.enrichmentRules.splice(index, 1);
    renderEnrichmentRulesTable();
    renderSchemaMappingTable();
}

function getAvailableSourceFieldsForEnrichment() {
    const standard = ["title", "brands", "gtin", "categories", "description", "id"];
    const combined = [...standard];
    APP_STATE.sourceColumns.forEach((col) => {
        if (!combined.includes(col)) {
            combined.push(col);
        }
    });
    return combined;
}

function renderEnrichmentRulesTable() {
    const tbody = document.getElementById("enrichmentRulesTableBody");
    const emptyState = document.getElementById("emptyRulesState");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (APP_STATE.enrichmentRules.length === 0) {
        emptyState.classList.remove("hidden");
        return;
    }
    emptyState.classList.add("hidden");

    const availableSources = getAvailableSourceFieldsForEnrichment();

    APP_STATE.enrichmentRules.forEach((rule, idx) => {
        const tr = document.createElement("tr");
        tr.className = rule.enabled ? "hover:bg-blue-50/20 transition" : "bg-slate-50 opacity-60 transition";

        // 1. Enable Checkbox
        const tdEnable = document.createElement("td");
        tdEnable.className = "py-3.5 px-3 text-center";
        const chk = document.createElement("input");
        chk.type = "checkbox";
        chk.checked = rule.enabled !== false;
        chk.className = "w-4 h-4 text-blue-600 rounded cursor-pointer";
        chk.onchange = (e) => {
            rule.enabled = e.target.checked;
            renderEnrichmentRulesTable();
            renderSchemaMappingTable();
        };
        tdEnable.appendChild(chk);

        // 2. Rule Name Input
        const tdName = document.createElement("td");
        tdName.className = "py-3.5 px-3";
        const nameInput = document.createElement("input");
        nameInput.type = "text";
        nameInput.value = rule.name || "";
        nameInput.className = "w-full p-1.5 border border-slate-300 rounded-md font-bold text-slate-800 text-xs focus:outline-none focus:border-blue-600";
        nameInput.oninput = (e) => {
            rule.name = e.target.value;
            renderSchemaMappingTable();
        };
        tdName.appendChild(nameInput);

        // 3. Source Columns Multi-Selector
        const tdSources = document.createElement("td");
        tdSources.className = "py-3.5 px-3";
        const sourcesWrapper = document.createElement("div");
        sourcesWrapper.className = "space-y-1.5";

        const chipsContainer = document.createElement("div");
        chipsContainer.className = "flex flex-wrap gap-1";
        (rule.source_fields || []).forEach((sf) => {
            const chip = document.createElement("span");
            chip.className = "bg-indigo-50 text-indigo-800 border border-indigo-200 px-2 py-0.5 rounded-md font-mono text-[11px] flex items-center gap-1";
            chip.innerHTML = `
                <span>${sf}</span>
                <button type="button" class="text-indigo-400 hover:text-indigo-700 font-bold" title="削除">&times;</button>
            `;
            chip.querySelector("button").onclick = () => {
                rule.source_fields = rule.source_fields.filter((x) => x !== sf);
                renderEnrichmentRulesTable();
            };
            chipsContainer.appendChild(chip);
        });

        const addSourceSelect = document.createElement("select");
        addSourceSelect.className = "w-full p-1 border border-slate-300 rounded text-[11px] text-slate-600 bg-white focus:outline-none";
        let srcOpts = `<option value="">+ 参照する入力項目を追加...</option>`;
        availableSources.forEach((src) => {
            if (!(rule.source_fields || []).includes(src)) {
                srcOpts += `<option value="${src}">${src}</option>`;
            }
        });
        addSourceSelect.innerHTML = srcOpts;
        addSourceSelect.onchange = (e) => {
            const val = e.target.value;
            if (val && !rule.source_fields.includes(val)) {
                rule.source_fields.push(val);
                renderEnrichmentRulesTable();
            }
        };

        sourcesWrapper.appendChild(chipsContainer);
        sourcesWrapper.appendChild(addSourceSelect);
        tdSources.appendChild(sourcesWrapper);

        // 4. Google Search Grounding Toggle Switch + AI 検証トグル
        const tdSearch = document.createElement("td");
        tdSearch.className = "py-3.5 px-3 text-center";
        const toggleWrapper = document.createElement("div");
        toggleWrapper.className = "flex flex-col items-center gap-1.5";

        const searchBtn = document.createElement("button");
        searchBtn.type = "button";
        if (rule.use_google_search) {
            searchBtn.className = "bg-blue-600 text-white font-bold text-[11px] px-3 py-1.5 rounded-full shadow-sm flex items-center justify-center gap-1.5 mx-auto hover:bg-blue-700 transition w-[118px]";
            searchBtn.innerHTML = `<i class="fa-brands fa-google"></i> <span>Search ON</span>`;
        } else {
            searchBtn.className = "bg-slate-200 text-slate-600 font-semibold text-[11px] px-3 py-1.5 rounded-full flex items-center justify-center gap-1.5 mx-auto hover:bg-slate-300 transition w-[118px]";
            searchBtn.innerHTML = `<i class="fa-solid fa-ban"></i> <span>Search OFF</span>`;
        }
        searchBtn.onclick = () => {
            rule.use_google_search = !rule.use_google_search;
            renderEnrichmentRulesTable();
        };

        // AI 検証・自動修正 (生成結果の事実確認・日本語校閲パス)
        const verifyBtn = document.createElement("button");
        verifyBtn.type = "button";
        const verifyOn = rule.enable_verification !== false;
        if (verifyOn) {
            verifyBtn.className = "bg-emerald-600 text-white font-bold text-[11px] px-3 py-1.5 rounded-full shadow-sm flex items-center justify-center gap-1.5 mx-auto hover:bg-emerald-700 transition w-[118px]";
            verifyBtn.innerHTML = `<i class="fa-solid fa-circle-check"></i> <span>AI検証 ON</span>`;
            verifyBtn.title = "生成結果を別プロンプトで校閲し、事実誤り・途中で切れた文章・不自然な日本語を自動修正します（推奨）。";
        } else {
            verifyBtn.className = "bg-slate-200 text-slate-600 font-semibold text-[11px] px-3 py-1.5 rounded-full flex items-center justify-center gap-1.5 mx-auto hover:bg-slate-300 transition w-[118px]";
            verifyBtn.innerHTML = `<i class="fa-solid fa-circle-xmark"></i> <span>AI検証 OFF</span>`;
            verifyBtn.title = "検証パスを行いません。処理は速くなりますが、途中で切れた文章や誤情報が残る可能性があります。";
        }
        verifyBtn.onclick = () => {
            rule.enable_verification = !verifyOn;
            renderEnrichmentRulesTable();
        };

        toggleWrapper.appendChild(searchBtn);
        toggleWrapper.appendChild(verifyBtn);
        tdSearch.appendChild(toggleWrapper);


        // 5. Target Schema Field Selector
        const tdTarget = document.createElement("td");
        tdTarget.className = "py-3.5 px-3";
        const targetSelect = document.createElement("select");
        targetSelect.className = "w-full p-1.5 border border-emerald-300 rounded-md bg-emerald-50/40 font-mono font-bold text-emerald-950 text-xs focus:outline-none focus:border-emerald-600";
        let targetOpts = "";
        APP_STATE.mappableFields.forEach((mf) => {
            const sel = rule.target_field === mf.id ? "selected" : "";
            targetOpts += `<option value="${mf.id}" ${sel}>${mf.id} (${mf.type})</option>`;
        });
        targetSelect.innerHTML = targetOpts;
        targetSelect.onchange = (e) => {
            rule.target_field = e.target.value;
            if (rule.target_field === "description") {
                rule.output_format = "text";
            } else if (rule.target_field === "attributes") {
                rule.output_format = "attributes_kv";
            } else if (rule.target_field.includes("tags") || rule.target_field === "categories" || rule.target_field === "brands" || rule.target_field.includes("colors") || rule.target_field === "materials") {
                rule.output_format = "json_array";
            }
            renderEnrichmentRulesTable();
            renderSchemaMappingTable();
        };
        tdTarget.appendChild(targetSelect);

        // 6. Output Format Selector
        const tdFormat = document.createElement("td");
        tdFormat.className = "py-3.5 px-3";
        const formatSelect = document.createElement("select");
        formatSelect.className = "w-full p-1.5 border border-slate-300 rounded-md bg-white text-xs text-slate-700 focus:outline-none";
        formatSelect.innerHTML = `
            <option value="json_array" ${rule.output_format === "json_array" ? "selected" : ""}>JSON 配列 (REPEATED)</option>
            <option value="text" ${rule.output_format === "text" ? "selected" : ""}>単一テキスト (STRING)</option>
            <option value="attributes_kv" ${rule.output_format === "attributes_kv" ? "selected" : ""}>Key-Value (attributes)</option>
            <option value="json_object" ${rule.output_format === "json_object" ? "selected" : ""}>JSON オブジェクト (RECORD)</option>
        `;
        formatSelect.onchange = (e) => {
            rule.output_format = e.target.value;
        };
        tdFormat.appendChild(formatSelect);

        // 7. Prompt Summary & Edit Modal Button
        const tdPrompt = document.createElement("td");
        tdPrompt.className = "py-3.5 px-4";
        const promptPreviewText = (rule.prompt || "").replace(/\n+/g, " ").substring(0, 65) + "...";
        tdPrompt.innerHTML = `
            <div class="flex items-center justify-between gap-2 bg-slate-50 border border-slate-200 rounded-lg p-2">
                <span class="font-mono text-[11px] text-slate-600 truncate max-w-[200px]" title="${(rule.prompt || "").replace(/"/g, '&quot;')}">${promptPreviewText}</span>
                <button type="button" onclick="openPromptModal(${idx})" class="bg-white hover:bg-blue-50 text-blue-600 border border-blue-200 font-bold text-xs px-2.5 py-1 rounded shadow-sm whitespace-nowrap flex items-center gap-1 transition">
                    <i class="fa-solid fa-pen-to-square"></i> プロンプト設定
                </button>
            </div>
        `;

        // 8. Test Action & Delete Button
        const tdActions = document.createElement("td");
        tdActions.className = "py-3.5 px-3 text-center";
        tdActions.innerHTML = `
            <div class="flex items-center justify-center gap-1.5">
                <button type="button" onclick="testSingleEnrichmentRule(${idx})" class="bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs px-2.5 py-1.5 rounded-lg shadow-sm flex items-center gap-1 transition" title="先頭行のデータを使って Google Search + Gemini を即時テスト">
                    <i class="fa-solid fa-bolt"></i> 1行テスト
                </button>
                <button type="button" onclick="removeEnrichmentRule(${idx})" class="text-slate-400 hover:text-red-600 p-1.5 rounded-lg hover:bg-red-50 transition" title="このルールを削除">
                    <i class="fa-solid fa-trash-can"></i>
                </button>
            </div>
        `;

        tr.appendChild(tdEnable);
        tr.appendChild(tdName);
        tr.appendChild(tdSources);
        tr.appendChild(tdSearch);
        tr.appendChild(tdTarget);
        tr.appendChild(tdFormat);
        tr.appendChild(tdPrompt);
        tr.appendChild(tdActions);
        tbody.appendChild(tr);
    });
}


// ============================================================================
// Prompt Editor Modal Logic
// ============================================================================

function openPromptModal(ruleIndex) {
    APP_STATE.editingRuleIndex = ruleIndex;
    const rule = APP_STATE.enrichmentRules[ruleIndex];
    if (!rule) return;

    document.getElementById("promptModalTitle").textContent = `プロンプト設定 - ${rule.name}`;
    document.getElementById("promptModalTargetField").textContent = rule.target_field;
    document.getElementById("promptModalOutputFormat").textContent = rule.output_format;
    document.getElementById("promptModalTextarea").value = rule.prompt || "";

    const chipsDiv = document.getElementById("promptVariableChips");
    chipsDiv.innerHTML = "";
    const vars = getAvailableSourceFieldsForEnrichment();
    vars.forEach((v) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "bg-white hover:bg-blue-600 hover:text-white text-slate-700 border border-slate-300 font-mono text-xs px-2.5 py-1 rounded-md shadow-sm transition";
        btn.textContent = `{${v}}`;
        btn.onclick = () => insertVariableIntoTextarea(`{${v}}`);
        chipsDiv.appendChild(btn);
    });

    document.getElementById("promptModal").classList.remove("hidden");
}

function insertVariableIntoTextarea(varText) {
    const textarea = document.getElementById("promptModalTextarea");
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = textarea.value;
    textarea.value = text.substring(0, start) + varText + text.substring(end);
    textarea.focus();
    textarea.selectionStart = textarea.selectionEnd = start + varText.length;
}

function closePromptModal() {
    document.getElementById("promptModal").classList.add("hidden");
    APP_STATE.editingRuleIndex = null;
}

function savePromptModal() {
    if (APP_STATE.editingRuleIndex === null) return;
    const rule = APP_STATE.enrichmentRules[APP_STATE.editingRuleIndex];
    if (rule) {
        rule.prompt = document.getElementById("promptModalTextarea").value;
    }
    closePromptModal();
    renderEnrichmentRulesTable();
}


// ============================================================================
// Single Row Live Test Logic (1行即時テスト)
// ============================================================================

async function testSingleEnrichmentRule(ruleIndex) {
    const rule = APP_STATE.enrichmentRules[ruleIndex];
    if (!rule) return;

    const modal = document.getElementById("testResultModal");
    const loading = document.getElementById("testModalLoading");
    const content = document.getElementById("testModalContent");

    document.getElementById("testModalSubtitle").textContent = `ルール: ${rule.name} → 対象スキーマ項目: ${rule.target_field}`;
    modal.classList.remove("hidden");
    loading.classList.remove("hidden");
    content.classList.add("hidden");

    const projectId = document.getElementById("globalProjectId").value.trim();
    const modelName = document.getElementById("globalModelName").value;

    try {
        const res = await fetch("/api/enrichment/test-rule", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                dataset_id: APP_STATE.datasetId,
                row_index: 0,
                mapping_config: APP_STATE.mappingConfig,
                rule: rule,
                model_name: modelName,
                project_id: projectId
            })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || "テスト実行エラー");
        }

        const tr = data.test_result;
        loading.classList.add("hidden");
        content.classList.remove("hidden");

        document.getElementById("testElapsedBadge").textContent = `所要時間: ${tr.elapsed_seconds}秒`;
        document.getElementById("testTargetFieldBadge").textContent = tr.target_field;

        const qList = document.getElementById("testSearchQueriesList");
        qList.innerHTML = "";
        if (tr.search_queries && tr.search_queries.length > 0) {
            tr.search_queries.forEach((q) => {
                const badge = document.createElement("span");
                badge.className = "bg-white border border-blue-300 text-blue-900 px-2.5 py-1 rounded-full font-medium text-xs shadow-sm flex items-center gap-1";
                badge.innerHTML = `<i class="fa-solid fa-magnifying-glass text-blue-500 text-[10px]"></i> ${q}`;
                qList.appendChild(badge);
            });
        } else {
            qList.innerHTML = `<span class="text-slate-400 italic">実行された Web 検索クエリなし（内部知識による推論 または Search OFF）</span>`;
        }

        const sList = document.getElementById("testSearchSourcesList");
        sList.innerHTML = "";
        if (tr.sources && tr.sources.length > 0) {
            tr.sources.forEach((src) => {
                const div = document.createElement("div");
                div.className = "flex items-center gap-2 text-xs truncate";
                div.innerHTML = `
                    <i class="fa-solid fa-link text-blue-500"></i>
                    <a href="${src.uri}" target="_blank" class="text-blue-600 hover:underline font-medium truncate">${src.title || src.uri}</a>
                `;
                sList.appendChild(div);
            });
        } else {
            sList.innerHTML = `<span class="text-slate-400 italic">参照された外部 Web ドキュメントなし</span>`;
        }

        document.getElementById("testParsedOutput").textContent = JSON.stringify(tr.parsed_result, null, 2);
        document.getElementById("testRawResponse").textContent = tr.raw_response || tr.error || "";
        document.getElementById("testFullBigqueryRow").textContent = JSON.stringify(data.bigquery_row_preview, null, 2);

        // AI 品質検証（ファクトチェック ＆ 日本語校閲）結果を描画
        renderVerificationPanel(tr);

        // Before & After 改善サマリーを描画
        renderBeforeAfterDiff(data);

        const valBadge = document.getElementById("testValidationBadge");
        if (data.validation && data.validation.valid) {
            valBadge.className = "bg-emerald-100 text-emerald-800 px-2.5 py-0.5 rounded-full text-xs font-bold";
            valBadge.innerHTML = `<i class="fa-solid fa-check-circle mr-1"></i>BigQuery スキーマ適合`;
        } else {
            valBadge.className = "bg-amber-100 text-amber-800 px-2.5 py-0.5 rounded-full text-xs font-bold";
            valBadge.innerHTML = `<i class="fa-solid fa-triangle-exclamation mr-1"></i>必須項目確認が必要`;
        }

    } catch (err) {
        loading.classList.add("hidden");
        alert("1行テストに失敗しました: " + err.message);
        closeTestResultModal();
    }
}

// ============================================================================
// AI 品質検証パネル描画
// ============================================================================

const VERIFICATION_ISSUE_LABELS = {
    truncated: "出力の途中切れ（トークン上限）",
    incomplete_sentence: "文章が途中で終わっている",
    unbalanced_bracket: "括弧の開閉が不一致",
    too_short: "内容が極端に短い",
    repetition: "同一フレーズの繰り返し",
    unresolved_placeholder: "未置換のプレースホルダー",
    placeholder_text: "未確定・回答拒否の表現",
    parse_empty: "パース結果が空",
    parse_failed: "JSON パース失敗",
    malformed_item: "不正な要素の混入",
    empty: "出力が空",
    unnatural_japanese: "不自然な日本語",
    factual_error: "事実誤り",
    hallucination: "根拠のない記述（ハルシネーション）",
    format_violation: "出力形式違反",
    other: "その他"
};

function buildIssueRow(issue, origin) {
    const sev = (issue.severity || "low").toLowerCase();
    const sevStyle = sev === "high"
        ? "bg-red-100 text-red-800 border-red-200"
        : (sev === "medium" ? "bg-amber-100 text-amber-800 border-amber-200" : "bg-slate-100 text-slate-700 border-slate-200");
    const label = VERIFICATION_ISSUE_LABELS[issue.type] || issue.type || "問題";
    const evidence = issue.evidence
        ? `<div class="mt-1 text-[11px] text-slate-500 font-mono bg-slate-50 border-l-2 border-slate-300 pl-2 py-0.5">該当箇所: ${escapeHtml(issue.evidence)}</div>`
        : "";
    return `
        <div class="border ${sevStyle} rounded-lg px-3 py-2">
            <div class="flex items-start gap-2">
                <span class="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-white/70 border ${sevStyle}">${sev}</span>
                <div class="flex-1">
                    <div class="text-xs font-bold">${escapeHtml(label)}
                        <span class="text-[10px] font-normal text-slate-500 ml-1">(${origin})</span>
                    </div>
                    <div class="text-[11px] text-slate-700 mt-0.5">${escapeHtml(issue.detail || "")}</div>
                    ${evidence}
                </div>
            </div>
        </div>
    `;
}

function renderVerificationPanel(tr) {
    const box = document.getElementById("testVerificationBox");
    const verdictBadge = document.getElementById("testVerificationVerdictBadge");
    const elapsedBadge = document.getElementById("testVerificationElapsedBadge");
    const summaryEl = document.getElementById("testVerificationSummary");
    const issuesEl = document.getElementById("testVerificationIssues");
    const diffWrap = document.getElementById("testVerificationDiffWrap");
    if (!box) return;

    const ver = tr.verification || null;

    // 検証が無効、または実行されなかった場合
    if (!ver || !ver.enabled) {
        verdictBadge.textContent = "検証 OFF";
        verdictBadge.className = "bg-white/15 text-white px-2.5 py-0.5 rounded-full text-[11px] font-bold";
        elapsedBadge.textContent = "";
        summaryEl.innerHTML = `このルールは <strong>AI検証 OFF</strong> です。ルール行の「AI検証」ボタンを ON にすると、生成結果の事実確認・日本語校閲・途中切れの自動修正を行います。`;
        issuesEl.innerHTML = `<span class="text-xs text-slate-400 italic">検証を実行していません。</span>`;
        diffWrap.classList.add("hidden");
        return;
    }

    const preIssues = ver.pre_issues || [];
    const postIssues = ver.post_issues || [];
    const llmIssues = ver.llm_issues || [];
    const allIssues = [
        ...preIssues.map((i) => ({ i, origin: "機械チェック" })),
        ...llmIssues.map((i) => ({ i, origin: "AI校閲" }))
    ];
    const remainingHigh = postIssues.filter((i) => (i.severity || "") === "high").length;

    // 判定バッジ
    if (ver.verdict === "error") {
        verdictBadge.textContent = "検証エラー";
        verdictBadge.className = "bg-red-500 text-white px-2.5 py-0.5 rounded-full text-[11px] font-bold";
    } else if (ver.changed) {
        verdictBadge.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles mr-1"></i>自動修正あり`;
        verdictBadge.className = "bg-amber-400 text-amber-950 px-2.5 py-0.5 rounded-full text-[11px] font-bold";
    } else if (remainingHigh > 0) {
        verdictBadge.innerHTML = `<i class="fa-solid fa-triangle-exclamation mr-1"></i>要確認`;
        verdictBadge.className = "bg-red-400 text-red-950 px-2.5 py-0.5 rounded-full text-[11px] font-bold";
    } else {
        verdictBadge.innerHTML = `<i class="fa-solid fa-check mr-1"></i>問題なし`;
        verdictBadge.className = "bg-emerald-400 text-emerald-950 px-2.5 py-0.5 rounded-full text-[11px] font-bold";
    }
    elapsedBadge.textContent = `検証 ${ver.elapsed_seconds || 0}秒`;

    // サマリー文
    const parts = [];
    if (ver.regeneration_count > 0) {
        parts.push(`出力がトークン上限で切れたため <strong>${ver.regeneration_count} 回</strong>、上限を拡張して再生成しました。`);
    }
    parts.push(`機械チェックで <strong>${preIssues.length} 件</strong>、AI校閲で <strong>${llmIssues.length} 件</strong> の指摘を検出。`);
    if (ver.changed) {
        parts.push(`検証結果にもとづき本文を<strong class="text-amber-700">自動修正して格納</strong>しました。`);
    } else if (ver.verdict === "rejected") {
        parts.push(`<strong class="text-red-700">修正案が不適切だったため適用しませんでした。</strong>`);
    } else if (ver.verdict === "error") {
        parts.push(`<strong class="text-red-700">検証パスに失敗しました: ${escapeHtml(ver.error || "")}</strong>`);
    } else {
        parts.push(`修正は不要と判定されたため、生成結果をそのまま格納しています。`);
    }
    if (remainingHigh > 0) {
        parts.push(`<strong class="text-red-700">⚠ 修正後もなお ${remainingHigh} 件の重大な問題が残っています。プロンプトの見直しを推奨します。</strong>`);
    }
    summaryEl.innerHTML = parts.join(" ");

    // 問題一覧
    if (allIssues.length === 0) {
        issuesEl.innerHTML = `<div class="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
            <i class="fa-solid fa-circle-check mr-1"></i>文章の完全性・日本語の自然さ・事実の整合性・出力形式のいずれにも問題は検出されませんでした。
        </div>`;
    } else {
        issuesEl.innerHTML = allIssues.map(({ i, origin }) => buildIssueRow(i, origin)).join("");
    }

    // 修正前 / 修正後
    if (ver.changed && ver.corrected_response) {
        diffWrap.classList.remove("hidden");
        document.getElementById("testVerificationBefore").textContent = ver.original_response || "";
        document.getElementById("testVerificationAfter").textContent = ver.corrected_response || "";
    } else {
        diffWrap.classList.add("hidden");
    }
}

function toggleVerificationDiff() {
    const container = document.getElementById("testVerificationDiff");
    const icon = document.getElementById("testVerificationDiffIcon");
    const text = document.getElementById("testVerificationDiffText");
    const hidden = container.classList.contains("hidden");
    container.classList.toggle("hidden", !hidden);
    icon.className = hidden ? "fa-solid fa-chevron-down transition-transform" : "fa-solid fa-chevron-right transition-transform";
    text.textContent = hidden ? "修正前 / 修正後の全文を隠す" : "修正前 / 修正後の全文を表示";
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}


function buildMetricCard(label, beforeVal, afterVal, unit, icon) {
    const delta = afterVal - beforeVal;
    const improved = delta > 0;
    const deltaColor = improved ? "text-emerald-600" : (delta < 0 ? "text-red-600" : "text-slate-400");
    const deltaSign = delta > 0 ? "+" : "";
    const rateText = beforeVal > 0
        ? `${Math.round((afterVal / beforeVal) * 100)}%`
        : (afterVal > 0 ? "NEW" : "-");

    return `
        <div class="bg-white border ${improved ? "border-emerald-300" : "border-slate-200"} rounded-xl p-3 shadow-sm">
            <div class="flex items-center justify-between mb-1.5">
                <span class="text-[11px] font-bold text-slate-600 flex items-center gap-1"><i class="${icon} text-indigo-500"></i> ${label}</span>
                ${improved ? `<span class="bg-emerald-100 text-emerald-700 text-[10px] font-bold px-1.5 py-0.5 rounded-full">改善 ${rateText}</span>` : ""}
            </div>
            <div class="flex items-baseline gap-2">
                <span class="text-slate-400 font-mono text-sm line-through">${beforeVal}${unit}</span>
                <i class="fa-solid fa-arrow-right text-slate-300 text-[10px]"></i>
                <span class="text-slate-900 font-mono font-bold text-xl">${afterVal}${unit}</span>
                <span class="${deltaColor} font-bold text-xs">(${deltaSign}${delta}${unit})</span>
            </div>
        </div>
    `;
}

function renderBeforeAfterDiff(data) {
    const diff = data.diff_summary || { changes: [], metrics: {}, changed_field_count: 0 };
    const m = diff.metrics || {};

    // 1) 変更件数バッジ
    const badge = document.getElementById("diffChangedCountBadge");
    if (badge) {
        badge.textContent = diff.changed_field_count > 0
            ? `${diff.changed_field_count} 項目が改善されました`
            : "変化はありません";
    }

    // 2) 改善指標メトリクスカード
    const cards = document.getElementById("diffMetricCards");
    if (cards) {
        cards.innerHTML = [
            buildMetricCard("検索ヒット用キーワード数", m.search_terms_before || 0, m.search_terms_after || 0, " 個", "fa-solid fa-tags"),
            buildMetricCard("商品説明文の情報量", m.description_length_before || 0, m.description_length_after || 0, " 字", "fa-solid fa-align-left"),
            buildMetricCard("スペック属性 (attributes)", m.attributes_count_before || 0, m.attributes_count_after || 0, " 件", "fa-solid fa-sliders")
        ].join("");
    }

    // 3) 項目別 Before / After 比較
    const list = document.getElementById("diffFieldList");
    if (!list) return;
    list.innerHTML = "";

    if (!diff.changes || diff.changes.length === 0) {
        list.innerHTML = `
            <div class="bg-white border border-slate-200 rounded-lg p-4 text-center text-slate-400 italic">
                このルールによるスキーマ項目の変化はありませんでした。プロンプトや対象項目の設定をご確認ください。
            </div>`;
    } else {
        diff.changes.forEach((c) => {
            const isNew = c.change_type === "added";
            const typeBadge = isNew
                ? `<span class="bg-emerald-100 text-emerald-800 border border-emerald-300 text-[10px] font-bold px-2 py-0.5 rounded-full">新規追加</span>`
                : `<span class="bg-blue-100 text-blue-800 border border-blue-300 text-[10px] font-bold px-2 py-0.5 rounded-full">情報を拡充</span>`;

            let beforeHtml = "";
            let afterHtml = "";

            if (c.kind === "array") {
                const beforeSet = new Set((c.before_value || []).map(String));
                beforeHtml = (c.before_value && c.before_value.length)
                    ? c.before_value.map((v) => `<span class="bg-slate-200 text-slate-600 px-2 py-0.5 rounded-full text-[11px]">${escapeHtml(v)}</span>`).join(" ")
                    : `<span class="text-slate-400 italic text-[11px]">（データなし / 空配列）</span>`;

                afterHtml = (c.after_value || []).map((v) => {
                    const isAdded = !beforeSet.has(String(v));
                    return isAdded
                        ? `<span class="bg-emerald-100 text-emerald-900 border border-emerald-400 font-semibold px-2 py-0.5 rounded-full text-[11px]"><i class="fa-solid fa-plus text-[8px] mr-0.5"></i>${escapeHtml(v)}</span>`
                        : `<span class="bg-slate-200 text-slate-600 px-2 py-0.5 rounded-full text-[11px]">${escapeHtml(v)}</span>`;
                }).join(" ");
            } else {
                beforeHtml = c.before_value
                    ? `<span class="text-slate-600 text-[11px]">${escapeHtml(c.before_value).substring(0, 400)}</span>`
                    : `<span class="text-slate-400 italic text-[11px]">（データなし / null）</span>`;
                afterHtml = `<span class="text-emerald-900 text-[11px] font-medium">${escapeHtml(c.after_value).substring(0, 800)}</span>`;
            }

            const countText = c.kind === "array"
                ? `${c.before_count} 件 → <span class="text-emerald-700 font-bold">${c.after_count} 件</span>`
                : `${c.before_count} 字 → <span class="text-emerald-700 font-bold">${c.after_count} 字</span>`;

            const div = document.createElement("div");
            div.className = "bg-white border border-slate-200 rounded-lg overflow-hidden shadow-sm";
            div.innerHTML = `
                <div class="bg-slate-100 px-3 py-2 border-b border-slate-200 flex flex-wrap items-center justify-between gap-2">
                    <div class="flex items-center gap-2">
                        <code class="font-mono font-bold text-indigo-800 text-xs">${escapeHtml(c.field)}</code>
                        ${typeBadge}
                    </div>
                    <span class="text-[11px] text-slate-500 font-mono">${countText}</span>
                </div>
                <div class="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-200">
                    <div class="p-3 bg-slate-50/60 space-y-1.5">
                        <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wide flex items-center gap-1">
                            <i class="fa-regular fa-circle"></i> BEFORE
                        </div>
                        <div class="flex flex-wrap gap-1 max-h-32 overflow-y-auto">${beforeHtml}</div>
                    </div>
                    <div class="p-3 bg-emerald-50/40 space-y-1.5">
                        <div class="text-[10px] font-bold text-emerald-700 uppercase tracking-wide flex items-center gap-1">
                            <i class="fa-solid fa-circle-check"></i> AFTER
                            ${c.kind === "array" && c.added_items && c.added_items.length ? `<span class="ml-1 text-emerald-600 normal-case">(${c.added_items.length} 件を新たに追加)</span>` : ""}
                        </div>
                        <div class="flex flex-wrap gap-1 max-h-32 overflow-y-auto">${afterHtml}</div>
                    </div>
                </div>
            `;
            list.appendChild(div);
        });
    }

    // 4) JSON 左右比較
    const beforeJson = document.getElementById("diffBeforeJson");
    const afterJson = document.getElementById("diffAfterJson");
    if (beforeJson) beforeJson.textContent = JSON.stringify(data.bigquery_row_before || {}, null, 2);
    if (afterJson) afterJson.textContent = JSON.stringify(data.bigquery_row_preview || {}, null, 2);

    // JSON 比較は初期状態で閉じておく
    const jsonContainer = document.getElementById("diffJsonContainer");
    if (jsonContainer && !jsonContainer.classList.contains("hidden")) {
        toggleDiffJsonView();
    }
}

function toggleDiffJsonView() {
    const container = document.getElementById("diffJsonContainer");
    const icon = document.getElementById("diffJsonToggleIcon");
    const text = document.getElementById("diffJsonToggleText");
    if (!container) return;

    const isHidden = container.classList.toggle("hidden");
    if (isHidden) {
        if (icon) icon.className = "fa-solid fa-chevron-down";
        if (text) text.textContent = "Before / After の完全な JSON を左右で比較する";
    } else {
        if (icon) icon.className = "fa-solid fa-chevron-up";
        if (text) text.textContent = "JSON 比較を閉じる";
    }
}

function closeTestResultModal() {
    document.getElementById("testResultModal").classList.add("hidden");
}


// ============================================================================
// STEP 4: Batch Execution, Real-time Progress & BigQuery Export
// ============================================================================

async function startBatchProcessing() {
    if (!APP_STATE.datasetId) {
        alert("先に CSV/JSONL ファイルをアップロードするか、サンプルデータを読み込んでください。");
        return;
    }

    const rowLimit = parseInt(document.getElementById("batchRowLimit").value, 10);
    const concurrency = parseInt(document.getElementById("batchConcurrency").value, 10);
    const projectId = document.getElementById("globalProjectId").value.trim();
    const modelName = document.getElementById("globalModelName").value;

    document.getElementById("batchProgressPanel").classList.remove("hidden");
    document.getElementById("batchResultsPanel").classList.add("hidden");
    document.getElementById("jobSpinner").classList.remove("hidden");
    document.getElementById("jobProgressBar").style.width = "5%";
    // A previous job's file must not be downloadable while a new run is in flight.
    APP_STATE.currentJobId = null;
    APP_STATE.totalProcessedRows = 0;
    APP_STATE.processedResults = [];
    updateDownloadAvailability(0);
    document.getElementById("jobLogConsole").innerHTML = `<div class="text-blue-400">[システム] 一括データ変換および Google Search + Gemini Enrichment ジョブを初期化しています...</div>`;

    try {
        const res = await fetch("/api/process/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                dataset_id: APP_STATE.datasetId,
                mapping_config: APP_STATE.mappingConfig,
                enrichment_rules: APP_STATE.enrichmentRules,
                row_limit: rowLimit,
                concurrency: concurrency,
                model_name: modelName,
                project_id: projectId,
                enable_verification: (document.getElementById("batchEnableVerification") || { checked: true }).checked
            })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || "バッチジョブ開始エラー");
        }

        APP_STATE.currentJobId = data.job_id;
        document.getElementById("jobTotalCount").textContent = data.total_rows;

        if (APP_STATE.jobPollInterval) clearInterval(APP_STATE.jobPollInterval);
        APP_STATE.jobPollInterval = setInterval(pollJobStatus, 800);

    } catch (err) {
        alert("バッチ実行エラー: " + err.message);
    }
}

async function pollJobStatus() {
    if (!APP_STATE.currentJobId) return;

    try {
        const res = await fetch(`/api/process/status/${APP_STATE.currentJobId}`);
        const data = await res.json();

        document.getElementById("jobProcessedCount").textContent = data.processed_rows;
        document.getElementById("jobTotalCount").textContent = data.total_rows;
        document.getElementById("jobSuccessCount").textContent = data.success_count;
        const fixedEl = document.getElementById("jobFixedCount");
        if (fixedEl) fixedEl.textContent = data.fixed_count || 0;

        const pct = data.total_rows > 0 ? Math.round((data.processed_rows / data.total_rows) * 100) : 0;
        document.getElementById("jobProgressBar").style.width = `${Math.max(5, pct)}%`;

        const logConsole = document.getElementById("jobLogConsole");
        logConsole.innerHTML = "";
        (data.logs || []).forEach((line) => {
            const div = document.createElement("div");
            if (line.includes("[完了]")) div.className = "text-emerald-400 font-bold";
            else if (line.includes("[エラー]")) div.className = "text-red-400 font-bold";
            else div.className = "text-slate-300";
            div.textContent = line;
            logConsole.appendChild(div);
        });
        logConsole.scrollTop = logConsole.scrollHeight;

        if (data.status === "completed") {
            clearInterval(APP_STATE.jobPollInterval);
            APP_STATE.jobPollInterval = null;
            document.getElementById("jobSpinner").classList.add("hidden");
            document.getElementById("jobStatusTitle").textContent = "✅ 全商品データの AI Enrichment および BigQuery スキーマ変換が完了しました！";
            document.getElementById("jobStatusSubtitle").textContent = `全 ${data.total_rows} 件の処理が完了しました`;
            APP_STATE.processedResults = data.results_preview || [];
            APP_STATE.totalProcessedRows = data.total_rows || APP_STATE.processedResults.length;
            renderProcessedResultsTable();
            document.getElementById("batchResultsPanel").classList.remove("hidden");
            updateDownloadAvailability(APP_STATE.totalProcessedRows, estimateBytesPerRow());
        } else if (data.status === "failed") {
            clearInterval(APP_STATE.jobPollInterval);
            APP_STATE.jobPollInterval = null;
            document.getElementById("jobSpinner").classList.add("hidden");
            document.getElementById("jobStatusTitle").textContent = "❌ 処理中にエラーが発生しました。";
            document.getElementById("jobStatusSubtitle").textContent = data.error || "";
        }
    } catch (err) {
        console.error("Poll status error:", err);
    }
}

function renderProcessedResultsTable() {
    const tbody = document.getElementById("processedResultsTableBody");
    tbody.innerHTML = "";

    const total = APP_STATE.totalProcessedRows || APP_STATE.processedResults.length;
    const shown = APP_STATE.processedResults.length;
    document.getElementById("resultsSummaryText").textContent =
        shown < total
            ? `プレビュー ${shown} 件表示 / 全 ${total} 件 (JSONL には全 ${total} 件が出力されます)`
            : `全 ${total} 件`;

    APP_STATE.processedResults.forEach((item, idx) => {
        const bq = item.bigquery_row || {};
        const val = item.validation || { valid: true };
        const tr = document.createElement("tr");
        tr.className = "hover:bg-blue-50/30 transition";

        let tagsList = bq.tags || [];
        const attrTags = (bq.attributes || []).find((a) => a.key === "tags");
        if (attrTags && attrTags.value && attrTags.value.text) {
            tagsList = [...new Set([...tagsList, ...attrTags.value.text])];
        }

        const tagsHtml = tagsList.slice(0, 8).map((t) =>
            `<span class="bg-blue-50 text-blue-800 border border-blue-200 px-2 py-0.5 rounded-full text-[11px] font-medium">${t}</span>`
        ).join(" ") + (tagsList.length > 8 ? ` <span class="text-slate-400 text-[11px] font-bold">+${tagsList.length - 8}個</span>` : "");

        const descPreview = (bq.description || "").substring(0, 70) + ((bq.description || "").length > 70 ? "..." : "");
        const attrCount = (bq.attributes || []).length;

        tr.innerHTML = `
            <td class="py-3 px-4 font-mono text-slate-400">${idx + 1}</td>
            <td class="py-3 px-4 font-mono font-bold text-slate-800">${bq.id || "-"}</td>
            <td class="py-3 px-4 font-semibold text-slate-800">${bq.title || "-"}</td>
            <td class="py-3 px-4">
                <div class="flex flex-wrap gap-1">${tagsHtml || '<span class="text-slate-400 italic">タグなし</span>'}</div>
            </td>
            <td class="py-3 px-4">
                <div class="text-slate-700 text-xs line-clamp-2">${descPreview || "-"}</div>
                <div class="text-[11px] text-indigo-600 font-semibold mt-1">Attributes 属性: ${attrCount} 項目</div>
            </td>
            <td class="py-3 px-4 text-center">
                ${val.valid
                    ? `<span class="bg-emerald-100 text-emerald-800 px-2.5 py-1 rounded-full text-[11px] font-bold"><i class="fa-solid fa-check mr-1"></i>適合</span>`
                    : `<span class="bg-red-100 text-red-800 px-2.5 py-1 rounded-full text-[11px] font-bold"><i class="fa-solid fa-exclamation mr-1"></i>エラー</span>`
                }
            </td>
            <td class="py-3 px-4 text-center">
                <button onclick="openRowDetailModal(${idx})" class="bg-slate-800 hover:bg-blue-600 text-white text-xs font-semibold px-3 py-1.5 rounded-lg shadow-sm transition">
                    <i class="fa-solid fa-code mr-1"></i> 詳細比較
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}


// ============================================================================
// Export, Download & BigQuery Direct Load
// ============================================================================

/**
 * Estimates the average serialized byte size of one BigQuery JSONL row, based on the
 * preview rows we already have. Japanese text is multi-byte, so TextEncoder is used
 * rather than String.length. Falls back to a rough constant when no preview exists.
 */
function estimateBytesPerRow() {
    const rows = (APP_STATE.processedResults || []).filter((r) => r && r.bigquery_row);
    if (!rows.length) return 2200;

    const encoder = new TextEncoder();
    const totalBytes = rows.reduce(
        (sum, r) => sum + encoder.encode(JSON.stringify(r.bigquery_row)).length + 1, // +1 for the newline
        0
    );
    return Math.round(totalBytes / rows.length);
}

/**
 * Enables/disables the two JSONL download buttons and renders the row count and
 * estimated file size. Called when a batch job completes and when a new one starts.
 *
 * NOTE: totalRows must come from the job status payload (data.total_rows), NOT from
 * APP_STATE.processedResults.length - the backend caps results_preview at 20 rows
 * while the export endpoint returns every processed row.
 */
function updateDownloadAvailability(totalRows, avgBytesPerRow) {
    const ready = Boolean(APP_STATE.currentJobId) && totalRows > 0;
    const headerBtn = document.getElementById("headerDownloadJsonlBtn");
    const hint = document.getElementById("headerDownloadJsonlHint");
    const info = document.getElementById("jsonlFileInfo");

    if (headerBtn) {
        headerBtn.disabled = !ready;
        headerBtn.className = ready
            ? "bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs px-4 py-2.5 rounded-lg shadow flex items-center gap-2 transition"
            : "bg-slate-200 text-slate-400 cursor-not-allowed font-bold text-xs px-4 py-2.5 rounded-lg shadow-sm flex items-center gap-2 transition";
    }
    if (hint) {
        hint.textContent = ready ? `(全 ${totalRows} 件)` : "(実行後に有効化)";
    }

    if (info) {
        if (ready) {
            const estBytes = totalRows * (avgBytesPerRow || 2200);
            info.innerHTML = `<i class="fa-solid fa-file-lines mr-1"></i> 出力対象: 全 ${totalRows} 件 / 推定ファイルサイズ: 約 ${formatFileSize(estBytes)} ` +
                `<span class="font-normal text-emerald-700">(NDJSON 形式 ・ 1行 = 1商品 ・ BigQuery ロードにそのまま利用できます)</span>`;
        } else {
            info.textContent = "";
        }
    }
}

function formatFileSize(bytes) {
    if (!bytes || bytes < 1024) return `${bytes || 0} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * Downloads the generated BigQuery JSONL (NDJSON) file.
 *
 * Uses fetch + Blob rather than assigning window.location.href: navigating the page
 * away would discard the entire in-page mapping / enrichment configuration if the
 * server returned an error (e.g. the job no longer exists after a restart).
 */
async function downloadBigQueryJsonl() {
    if (!APP_STATE.currentJobId) {
        alert("先に「データマッピング ＆ Enrichment 一括実行」を実行してください。\n処理が完了すると JSONL ファイルをダウンロードできます。");
        return;
    }

    const buttons = ["headerDownloadJsonlBtn", "panelDownloadJsonlBtn"]
        .map((id) => document.getElementById(id))
        .filter(Boolean);
    const originalHtml = buttons.map((b) => b.innerHTML);

    buttons.forEach((b) => {
        b.disabled = true;
        b.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> JSONL を生成中...`;
    });

    try {
        const res = await fetch(`/api/export/jsonl/${APP_STATE.currentJobId}`);

        if (!res.ok) {
            let detail = "";
            try {
                const errBody = await res.json();
                detail = errBody.detail || "";
            } catch (e) { /* non-JSON error body */ }

            if (res.status === 404) {
                throw new Error("ジョブが見つかりません（サーバーの再起動によりデータが失われた可能性があります）。\nお手数ですが、一括実行をもう一度実行してください。");
            }
            if (res.status === 400) {
                throw new Error("ダウンロード可能な処理結果がありません。一括実行が正常に完了しているかご確認ください。");
            }
            throw new Error(detail || `ダウンロードに失敗しました (HTTP ${res.status})`);
        }

        // Prefer the server-provided filename from Content-Disposition.
        let filename = `aics_bigquery_catalog_${APP_STATE.currentJobId}.jsonl`;
        const disposition = res.headers.get("Content-Disposition") || "";
        const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
        if (match && match[1]) {
            filename = decodeURIComponent(match[1]);
        }

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        // Revoke on the next tick so Safari/Firefox have time to start the download.
        setTimeout(() => URL.revokeObjectURL(url), 2000);

        const info = document.getElementById("jsonlFileInfo");
        if (info) {
            info.innerHTML = `<i class="fa-solid fa-circle-check mr-1"></i> ダウンロード完了: <code>${filename}</code> (${formatFileSize(blob.size)})` +
                `<span class="font-normal text-emerald-700"> ・ NDJSON 形式 ・ BigQuery ロードにそのまま利用できます</span>`;
        }
        if (blob.size === 0) {
            alert("警告: ダウンロードされたファイルが空です。処理結果をご確認ください。");
        }
    } catch (err) {
        alert("JSONL ダウンロードエラー:\n\n" + err.message);
    } finally {
        buttons.forEach((b, i) => {
            b.disabled = false;
            b.innerHTML = originalHtml[i];
        });
    }
}

function copyBqCliCommand() {
    const proj = document.getElementById("globalProjectId").value.trim() || "retail-search-jp-demo-minsoo";
    const ds = document.getElementById("bqLoadDataset").value.trim() || "retail_search";
    const tbl = document.getElementById("bqLoadTable").value.trim() || "d-vais-c";
    const filename = `aics_bigquery_catalog_${APP_STATE.currentJobId || "output"}.jsonl`;

    const cmd = `bq load --source_format=NEWLINE_DELIMITED_JSON --autodetect ${proj}:${ds}.${tbl} ./${filename}`;
    navigator.clipboard.writeText(cmd);
    alert(`BigQuery ロード用 CLI コマンドをクリップボードにコピーしました:\n\n${cmd}`);
}

function openBigQueryLoadModal() {
    document.getElementById("bqLoadStatusMsg").classList.add("hidden");
    document.getElementById("bqLoadModal").classList.remove("hidden");
}

function closeBigQueryLoadModal() {
    document.getElementById("bqLoadModal").classList.add("hidden");
}

async function executeBigQueryLoad() {
    if (!APP_STATE.currentJobId) return;

    const btn = document.getElementById("bqLoadSubmitBtn");
    const statusMsg = document.getElementById("bqLoadStatusMsg");
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner animate-spin"></i> BigQuery へロード中...`;

    statusMsg.classList.remove("hidden");
    statusMsg.className = "p-3 rounded-lg font-medium bg-blue-50 text-blue-800 border border-blue-200";
    statusMsg.textContent = "Google Cloud BigQuery API を通じてテーブルへデータをロードしています...";

    try {
        const res = await fetch("/api/bigquery/load", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                job_id: APP_STATE.currentJobId,
                project_id: document.getElementById("bqLoadProject").value.trim(),
                dataset_id: document.getElementById("bqLoadDataset").value.trim(),
                table_id: document.getElementById("bqLoadTable").value.trim(),
                write_disposition: document.getElementById("bqLoadDisposition").value
            })
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || "BigQuery ロード失敗");
        }

        statusMsg.className = "p-3 rounded-lg font-bold bg-emerald-50 text-emerald-800 border border-emerald-300";
        statusMsg.innerHTML = `<i class="fa-solid fa-check-circle mr-1"></i> 完了！テーブル <code>${data.table}</code> に全 ${data.loaded_rows} 件のデータが格納されました。`;
    } catch (err) {
        statusMsg.className = "p-3 rounded-lg font-bold bg-red-50 text-red-800 border border-red-300";
        statusMsg.innerHTML = `<i class="fa-solid fa-circle-exclamation mr-1"></i> エラー: ${err.message}`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-cloud-arrow-up"></i> 今すぐロード実行`;
    }
}


// ============================================================================
// Modals: Row Comparison Detail, Schema Specification, Config Save/Load
// ============================================================================

function openRowDetailModal(index) {
    const item = APP_STATE.processedResults[index];
    if (!item) return;

    document.getElementById("rowDetailModalTitle").textContent = `商品 #${index + 1} (${item.bigquery_row?.id || ""}) 変換前後の JSON 詳細比較`;
    document.getElementById("rowDetailSourcePre").textContent = JSON.stringify(item.raw_row, null, 2);
    document.getElementById("rowDetailBqPre").textContent = JSON.stringify(item.bigquery_row, null, 2);
    document.getElementById("rowDetailModal").classList.remove("hidden");
}

function closeRowDetailModal() {
    document.getElementById("rowDetailModal").classList.add("hidden");
}

function openSchemaModal() {
    document.getElementById("schemaSpecJsonPre").textContent = JSON.stringify(APP_STATE.rawBigQuerySchema, null, 2);
    document.getElementById("schemaSpecModal").classList.remove("hidden");
}

function closeSchemaModal() {
    document.getElementById("schemaSpecModal").classList.add("hidden");
}

function exportConfiguration() {
    const configPayload = {
        version: "1.0",
        exported_at: new Date().toISOString(),
        project_id: document.getElementById("globalProjectId").value,
        model_name: document.getElementById("globalModelName").value,
        mapping_config: APP_STATE.mappingConfig,
        enrichment_rules: APP_STATE.enrichmentRules
    };

    const blob = new Blob([JSON.stringify(configPayload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `aics_enrichment_config_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

function importConfiguration(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const data = JSON.parse(e.target.result);
            if (data.project_id) document.getElementById("globalProjectId").value = data.project_id;
            if (data.model_name) document.getElementById("globalModelName").value = data.model_name;
            if (data.mapping_config) APP_STATE.mappingConfig = data.mapping_config;
            if (data.enrichment_rules) APP_STATE.enrichmentRules = data.enrichment_rules;

            renderSchemaMappingTable();
            renderEnrichmentRulesTable();
            alert("マッピングおよび Enrichment プロンプト設定が正常に復元されました！");
        } catch (err) {
            alert("設定ファイルの解析に失敗しました。有効な JSON ファイルであるか確認してください。");
        }
    };
    reader.readAsText(file);
}
