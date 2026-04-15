/**
 * decision-ready-renderer.js - Shared baseline-vs-candidate compare rendering helpers.
 */

import { formatNum, formatPct } from "../../../core/utils.js";

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function labelize(value) {
  return String(value || "-")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatMetricValue(valueFormat, value, currency = "", options = {}) {
  if (value == null || value === "") return "-";
  if (valueFormat === "pct") return formatPct(value);
  if (valueFormat === "count") {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    const prefix = options.signed && number > 0 ? "+" : "";
    return `${prefix}${Math.round(number)}`;
  }
  if (valueFormat === "money") {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    const prefix = options.signed && number > 0 ? "+" : "";
    return `${prefix}${formatNum(number, 2)}${currency ? ` ${currency}` : ""}`;
  }
  const number = Number(value);
  if (Number.isFinite(number)) {
    const prefix = options.signed && number > 0 ? "+" : "";
    return `${prefix}${formatNum(number, 3)}`;
  }
  return String(value);
}

export function formatCompactValue(value) {
  if (value == null || value === "") return "-";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "-";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function renderDecisionBadge(classification) {
  const value = String(classification || "neutral");
  return `<span class="decision-badge decision-badge--${escapeHtml(value)}">${escapeHtml(labelize(value))}</span>`;
}

function renderRuleList(title, rules, emptyNote) {
  const items = Array.isArray(rules) ? rules : [];
  return `
    <div class="compare-diagnosis-block">
      <div class="compare-diagnosis-block__title">${escapeHtml(title)}</div>
      ${items.length
        ? `<div class="compare-token-list">${items.map((rule) => `<span class="compare-token">${escapeHtml(rule)}</span>`).join("")}</div>`
        : `<div class="results-context__note">${escapeHtml(emptyNote)}</div>`}
    </div>
  `;
}

function countClassification(rows, classification) {
  return (Array.isArray(rows) ? rows : []).filter((row) => row?.classification === classification).length;
}

function strongestRow(rows, classification) {
  return (Array.isArray(rows) ? rows : [])
    .filter((row) => row?.classification === classification && row?.delta != null)
    .slice()
    .sort((left, right) => Math.abs(Number(right?.delta || 0)) - Math.abs(Number(left?.delta || 0)))[0] || null;
}

function strongestPair(rows, classification) {
  return (Array.isArray(rows) ? rows : [])
    .filter((row) => row?.classification === classification && row?.delta?.profit_total_pct != null)
    .slice()
    .sort((left, right) => Math.abs(Number(right?.delta?.profit_total_pct || 0)) - Math.abs(Number(left?.delta?.profit_total_pct || 0)))[0] || null;
}

function renderSnapshotCard(label, value, note = "") {
  return `
    <article class="compare-snapshot-card">
      <div class="compare-snapshot-card__label">${escapeHtml(label)}</div>
      <div class="compare-snapshot-card__value">${escapeHtml(value)}</div>
      ${note ? `<div class="compare-snapshot-card__note">${escapeHtml(note)}</div>` : ""}
    </article>
  `;
}

function renderDecisionSnapshot(comparison, options = {}) {
  const versionDiff = comparison?.version_diff || {};
  const metricRows = Array.isArray(comparison?.metrics) ? comparison.metrics : [];
  const pairRows = Array.isArray(comparison?.pairs?.rows) ? comparison.pairs.rows : [];
  const diagnosisDelta = comparison?.diagnosis_delta || {};
  const sourceTitle = versionDiff?.source_title || versionDiff?.summary || "Selected candidate";
  const codeChanged = versionDiff?.code_diff?.changed ? "Code Changed" : "Code Unchanged";
  const strongestMetricGain = strongestRow(metricRows, "improved");
  const strongestMetricLoss = strongestRow(metricRows, "regressed");
  const strongestPairGain = strongestPair(pairRows, "improved");
  const strongestPairLoss = strongestPair(pairRows, "regressed");
  const baselineLabel = options.baselineLabel || "Baseline";
  const candidateLabel = options.candidateLabel || "Selected Candidate";

const improvedCount = countClassification(metricRows, "improved");
  const regressedCount = countClassification(metricRows, "regressed");
  const improvedPairsCount = countClassification(pairRows, "improved");
  const regressedPairsCount = countClassification(pairRows, "regressed");
  const hasDifferences = improvedCount > 0 || regressedCount > 0 || improvedPairsCount > 0 || regressedPairsCount > 0;

  let summaryNote = "Summary-first view.";
  if (!hasDifferences) {
    summaryNote = "These runs have identical configuration. No metric or pair deltas detected.";
  }

return `
    <section class="results-context compare-decision-section compare-snapshot-section">
      <div class="results-context__title">Decision Snapshot</div>
      <div class="results-context__note">${summaryNote}</div>
      <div class="compare-snapshot-grid">
        ${renderSnapshotCard("Baseline Version", versionDiff?.baseline_version || baselineLabel, versionDiff?.baseline_version || "-")}
        ${renderSnapshotCard("Candidate Version", versionDiff?.candidate_version || candidateLabel, versionDiff?.candidate_version || "-")}
        ${renderSnapshotCard("Code", codeChanged, hasDifferences ? (versionDiff?.code_diff?.summary || "Unchanged") : "Same as baseline")}
        ${hasDifferences ? renderSnapshotCard("Improved Metrics", String(improvedCount), strongestMetricGain ? `${strongestMetricGain.label}: ${formatMetricValue(strongestMetricGain.format, strongestMetricGain.delta, '', { signed: true })}` : "None") : ""}
        ${hasDifferences ? renderSnapshotCard("Regressed Metrics", String(regressedCount), strongestMetricLoss ? `${strongestMetricLoss.label}: ${formatMetricValue(strongestMetricLoss.format, strongestMetricLoss.delta, '', { signed: true })}` : "None") : ""}
        ${hasDifferences ? renderSnapshotCard("Improved Pairs", String(improvedPairsCount), strongestPairGain ? `${strongestPairGain.pair}: ${formatPct(strongestPairGain?.delta?.profit_total_pct)}` : "None") : ""}
        ${hasDifferences ? renderSnapshotCard("Regressed Pairs", String(regressedPairsCount), strongestPairLoss ? `${strongestPairLoss.pair}: ${formatPct(strongestPairLoss?.delta?.profit_total_pct)}` : "None") : ""}
      </div>
    </section>
  `;
}

function renderSectionDetails(title, body, summaryNote = "", open = false) {
  return `
    <details class="compare-section-details"${open ? " open" : ""}>
      <summary class="compare-section-details__summary">
        <span>${escapeHtml(title)}</span>
        ${summaryNote ? `<span class="compare-section-details__note">${escapeHtml(summaryNote)}</span>` : ""}
      </summary>
      <div class="compare-section-details__body">
        ${body}
      </div>
    </details>
  `;
}

function groupParameterDiffRows(rows) {
  const groups = new Map();
  (Array.isArray(rows) ? rows : []).forEach((row) => {
    const path = String(row?.path || "$");
    const root = path === "$" ? "root" : (path.split(/[.[]/, 1)[0] || "root");
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root).push(row);
  });
  return Array.from(groups.entries()).map(([group, items]) => ({
    group,
    items: items.slice().sort((left, right) => String(left?.path || "").localeCompare(String(right?.path || ""))),
  }));
}

function renderParameterDiffGroups(versionDiff) {
  const groups = groupParameterDiffRows(versionDiff?.parameter_diff_rows || []);
  if (!groups.length) {
    return '<div class="results-context__note">No persisted parameter diff was detected between baseline and selected candidate.</div>';
  }

  return `
    <div class="compare-param-groups">
      ${groups.map(({ group, items }) => `
        <article class="compare-param-group">
          <div class="compare-param-group__title">${escapeHtml(labelize(group))}</div>
          <div class="compare-param-group__rows">
            ${items.map((row) => `
              <div class="compare-param-row">
                <div class="compare-param-row__header">
                  <span class="compare-param-row__path mono">${escapeHtml(row?.path || "-")}</span>
                  ${renderDecisionBadge(row?.status || "changed")}
                </div>
                <div class="compare-param-row__values">
                  <span><strong>Baseline:</strong> ${escapeHtml(formatCompactValue(row?.before))}</span>
                  <span><strong>Selected Candidate:</strong> ${escapeHtml(formatCompactValue(row?.after))}</span>
                </div>
              </div>
            `).join("")}
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderCodeDiff(versionDiff) {
  const codeDiff = versionDiff?.code_diff || {};
  const previewBlocks = Array.isArray(codeDiff?.preview_blocks) ? codeDiff.preview_blocks : [];
  const summary = codeDiff?.summary || "No persisted code diff summary is available.";
  return `
    <div class="compare-code-summary ${codeDiff?.changed ? "compare-code-summary--changed" : "compare-code-summary--unchanged"}">
      <div class="compare-code-summary__header">
        ${renderDecisionBadge(codeDiff?.changed ? "changed" : "neutral")}
        <span><strong>Code Diff:</strong> ${escapeHtml(summary)}</span>
      </div>
      <div class="compare-code-summary__meta">
        <span><strong>Added:</strong> ${escapeHtml(formatCompactValue(codeDiff?.added_lines ?? 0))}</span>
        <span><strong>Removed:</strong> ${escapeHtml(formatCompactValue(codeDiff?.removed_lines ?? 0))}</span>
        <span><strong>Diff Ref:</strong> ${escapeHtml(codeDiff?.diff_ref || "-")}</span>
      </div>
    </div>
    ${previewBlocks.length ? `
      <div class="compare-code-preview">
        ${previewBlocks.map((block) => `
          <section class="compare-code-preview__block">
            <div class="compare-code-preview__header">${escapeHtml(block?.header || 'Diff Block')}</div>
            <pre class="compare-code-preview__lines">${(Array.isArray(block?.lines) ? block.lines : []).map((line) => `<div class="compare-code-line compare-code-line--${escapeHtml(line?.kind || 'context')}"><span class="compare-code-line__marker">${line?.kind === 'added' ? '+' : line?.kind === 'removed' ? '-' : ' '}</span><span>${escapeHtml(line?.text || '')}</span></div>`).join('')}</pre>
          </section>
        `).join("")}
        ${codeDiff?.preview_truncated ? '<div class="results-context__note">Code preview truncated to the first 3 hunks and 40 diff lines.</div>' : ''}
      </div>
    ` : '<div class="results-context__note">No compact code preview is available for this compare.</div>'}
  `;
}


function renderRequestSnapshotDiff(versionDiff) {
  const diff = versionDiff?.request_snapshot_diff || {};
  const summary = diff?.summary || {};
  const warnings = Array.isArray(diff?.warnings) ? diff.warnings : [];
  const rows = Array.isArray(diff?.rows) ? diff.rows : [];

  if (!warnings.length && !rows.length) {
    return '<div class="results-context__note">No persisted run request snapshot diff is available for this compare.</div>';
  }

  return `
    ${warnings.length ? `
      <div class="compare-code-summary compare-code-summary--changed">
        <div class="compare-code-summary__header">
          ${renderDecisionBadge('changed')}
          <span><strong>Compare Warnings:</strong> ${escapeHtml(String(warnings.length))}</span>
        </div>
        <div class="results-context__note">${escapeHtml(warnings.join(' '))}</div>
      </div>
    ` : ''}
    ${rows.length ? `
      <div class="compare-param-groups">
        <article class="compare-param-group">
          <div class="compare-param-group__title">Request Snapshot (${escapeHtml(String(summary?.changed ?? '-'))} changed)</div>
          <div class="compare-param-group__rows">
            ${rows.map((row) => `
              <div class="compare-param-row">
                <div class="compare-param-row__header">
                  <span class="compare-param-row__path mono">${escapeHtml(row?.label || row?.path || '-')}</span>
                  ${renderDecisionBadge(row?.status || 'changed')}
                </div>
                <div class="compare-param-row__values">
                  <span><strong>Baseline:</strong> ${escapeHtml(String(row?.left_preview ?? formatCompactValue(row?.left)))}</span>
                  <span><strong>Selected Candidate:</strong> ${escapeHtml(String(row?.right_preview ?? formatCompactValue(row?.right)))}</span>
                </div>
                ${(row?.note ? `<div class="compare-cell-note">${escapeHtml(row.note)}</div>` : '')}
              </div>
            `).join('')}
          </div>
        </article>
      </div>
    ` : '<div class="results-context__note">No request snapshot rows are available for this compare.</div>'}
  `;
}

function renderVersionDiff(comparison, options = {}) {
  const versionDiff = comparison?.version_diff || {};
  const baselineLabel = options.baselineLabel || "Baseline";
  const candidateLabel = options.candidateLabel || "Selected Candidate";
  const summaryText = versionDiff?.summary || "No persisted candidate summary is available.";
  const matchedRules = Array.isArray(versionDiff?.matched_rules) ? versionDiff.matched_rules : [];

  return `
    <section class="results-context compare-decision-section">
      <div class="results-context__title">Version Diff</div>
      <div class="results-context__meta proposal-state-grid">
        <span><strong>${escapeHtml(baselineLabel)} Run:</strong> ${escapeHtml(comparison?.left?.run_id || '-')}</span>
        <span><strong>${escapeHtml(baselineLabel)} Version:</strong> ${escapeHtml(versionDiff?.baseline_version_id || comparison?.left?.version_id || '-')}</span>
        <span><strong>${escapeHtml(candidateLabel)} Run:</strong> ${escapeHtml(comparison?.right?.run_id || '-')}</span>
        <span><strong>${escapeHtml(candidateLabel)} Version:</strong> ${escapeHtml(versionDiff?.candidate_version_id || comparison?.right?.version_id || '-')}</span>
        <span><strong>Candidate Parent:</strong> ${escapeHtml(versionDiff?.candidate_parent_version_id || '-')}</span>
        <span><strong>Baseline Source:</strong> ${escapeHtml(labelize(versionDiff?.baseline_version_source || 'run'))}</span>
        <span><strong>Source Kind:</strong> ${escapeHtml(labelize(versionDiff?.source_kind || '-'))}</span>
        <span><strong>Source Title:</strong> ${escapeHtml(versionDiff?.source_title || '-')}</span>
        <span><strong>Candidate Mode:</strong> ${escapeHtml(labelize(versionDiff?.candidate_mode || '-'))}</span>
        <span><strong>Change Type:</strong> ${escapeHtml(labelize(versionDiff?.change_type || '-'))}</span>
        <span><strong>Action Type:</strong> ${escapeHtml(labelize(versionDiff?.action_type || '-'))}</span>
        <span><strong>Rule:</strong> ${escapeHtml(versionDiff?.rule || '-')}</span>
      </div>
      <div class="results-context__note">${escapeHtml(summaryText)}</div>
      ${matchedRules.length ? `<div class="compare-token-list">${matchedRules.map((rule) => `<span class="compare-token">${escapeHtml(rule)}</span>`).join('')}</div>` : ''}
      <div class="compare-version-diff-grid">
        <section class="compare-version-diff-panel">
          <div class="compare-version-diff-panel__title">Parameter Diff</div>
          ${renderParameterDiffGroups(versionDiff)}
        </section>
        <section class="compare-version-diff-panel">
          <div class="compare-version-diff-panel__title">Code Diff</div>
          ${renderCodeDiff(versionDiff)}
        </section>
        <section class="compare-version-diff-panel">
          <div class="compare-version-diff-panel__title">Run Snapshot Diff</div>
          ${renderRequestSnapshotDiff(versionDiff)}
        </section>
      </div>
    </section>
  `;
}

function renderMetricTable(comparison, options = {}) {
  const baselineLabel = options.baselineLabel || "Baseline";
  const candidateLabel = options.candidateLabel || "Selected Candidate";
  const rows = Array.isArray(comparison?.metrics) ? comparison.metrics : [];
  const leftCurrency = comparison?.left?.summary_metrics?.stake_currency || "";
  const rightCurrency = comparison?.right?.summary_metrics?.stake_currency || leftCurrency;
  const strongestGain = strongestRow(rows, "improved");
  const strongestLoss = strongestRow(rows, "regressed");

  return `
    <section class="results-context results-context--table compare-decision-section">
      <div class="results-context__title">Decision Metrics</div>
      <div class="results-context__meta compare-pair-summary-grid">
        <span><strong>Improved Metrics:</strong> ${escapeHtml(String(countClassification(rows, 'improved')))}</span>
        <span><strong>Regressed Metrics:</strong> ${escapeHtml(String(countClassification(rows, 'regressed')))}</span>
        <span><strong>Changed Metrics:</strong> ${escapeHtml(String(countClassification(rows, 'changed')))}</span>
        <span><strong>Top Improvement:</strong> ${escapeHtml(strongestGain ? `${strongestGain.label} (${formatMetricValue(strongestGain.format, strongestGain.delta, '', { signed: true })})` : 'No improving metric delta detected.')}</span>
        <span><strong>Top Regression:</strong> ${escapeHtml(strongestLoss ? `${strongestLoss.label} (${formatMetricValue(strongestLoss.format, strongestLoss.delta, '', { signed: true })})` : 'No regressing metric delta detected.')}</span>
      </div>
      ${rows.length ? `
        <div class="results-context__table">
          <table class="data-table compare-table proposal-compare-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>${escapeHtml(baselineLabel)}</th>
                <th>${escapeHtml(candidateLabel)}</th>
                <th>Delta</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map((metric) => `
                <tr>
                  <td>
                    <div>${escapeHtml(metric?.label || '-')}</div>
                    <div class="compare-cell-note">${escapeHtml(metric?.reason || '')}</div>
                  </td>
                  <td>${escapeHtml(formatMetricValue(metric?.format, metric?.left, leftCurrency))}</td>
                  <td>${escapeHtml(formatMetricValue(metric?.format, metric?.right, rightCurrency))}</td>
                  <td class="compare-metric-delta compare-metric-delta--${escapeHtml(metric?.classification || 'neutral')}">${escapeHtml(formatMetricValue(metric?.format, metric?.delta, rightCurrency, { signed: true }))}</td>
                  <td>${renderDecisionBadge(metric?.classification)}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      ` : '<div class="results-context__note">No persisted metric delta is available for this compare.</div>'}
    </section>
  `;
}

function renderPairTable(comparison, options = {}) {
  const baselineLabel = options.baselineLabel || "Baseline";
  const candidateLabel = options.candidateLabel || "Selected Candidate";
  const pairs = comparison?.pairs || {};
  const rows = Array.isArray(pairs?.rows) ? pairs.rows : [];
  const topImprovements = Array.isArray(pairs?.top_improvements) ? pairs.top_improvements : [];
  const topRegressions = Array.isArray(pairs?.top_regressions) ? pairs.top_regressions : [];
  const worstBefore = pairs?.worst_pair_change?.before || {};
  const worstAfter = pairs?.worst_pair_change?.after || {};
  const dragger = pairs?.pair_dragger_evidence || {};
  const summary = pairs?.summary || {};

  const improvementSummary = topImprovements.length
    ? topImprovements.map((row) => `${row.pair} (${formatPct(row?.delta?.profit_total_pct)})`).join(', ')
    : 'No improving pair delta detected.';
  const regressionSummary = topRegressions.length
    ? topRegressions.map((row) => `${row.pair} (${formatPct(row?.delta?.profit_total_pct)})`).join(', ')
    : 'No regressing pair delta detected.';

  return `
    <section class="results-context results-context--table compare-decision-section">
      <div class="results-context__title">Pair Delta</div>
      <div class="results-context__meta compare-pair-summary-grid">
        <span><strong>Improved Pairs:</strong> ${escapeHtml(formatCompactValue(summary?.improved_count ?? 0))}</span>
        <span><strong>Regressed Pairs:</strong> ${escapeHtml(formatCompactValue(summary?.regressed_count ?? 0))}</span>
        <span><strong>Changed Pairs:</strong> ${escapeHtml(formatCompactValue(summary?.changed_count ?? 0))}</span>
        <span><strong>Neutral Pairs:</strong> ${escapeHtml(formatCompactValue(summary?.neutral_count ?? 0))}</span>
        <span><strong>Top Improvements:</strong> ${escapeHtml(improvementSummary)}</span>
        <span><strong>Top Regressions:</strong> ${escapeHtml(regressionSummary)}</span>
        <span><strong>Worst Pair Before:</strong> ${escapeHtml(worstBefore?.pair || '-')}${worstBefore?.profit_total_pct == null ? '' : ` (${formatPct(worstBefore.profit_total_pct)})`}</span>
        <span><strong>Worst Pair After:</strong> ${escapeHtml(worstAfter?.pair || '-')}${worstAfter?.profit_total_pct == null ? '' : ` (${formatPct(worstAfter.profit_total_pct)})`}</span>
        <span><strong>Pair Dragger:</strong> ${escapeHtml(labelize(dragger?.status || 'none'))}</span>
      </div>
      ${rows.length ? `
        <div class="results-context__table">
          <table class="data-table compare-table compare-pairs-table">
            <thead>
              <tr>
                <th>Pair</th>
                <th>${escapeHtml(baselineLabel)} Profit</th>
                <th>${escapeHtml(candidateLabel)} Profit</th>
                <th>${escapeHtml(baselineLabel)} Win Rate</th>
                <th>${escapeHtml(candidateLabel)} Win Rate</th>
                <th>${escapeHtml(baselineLabel)} Trades</th>
                <th>${escapeHtml(candidateLabel)} Trades</th>
                <th>Profit Delta</th>
                <th>Win Rate Delta</th>
                <th>Trade Delta</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map((row) => `
                <tr>
                  <td>
                    <div>${escapeHtml(row?.pair || '-')}</div>
                    <div class="compare-cell-note">${escapeHtml(row?.reason || '')}</div>
                  </td>
                  <td>${escapeHtml(formatMetricValue('pct', row?.left?.profit_total_pct))}</td>
                  <td>${escapeHtml(formatMetricValue('pct', row?.right?.profit_total_pct))}</td>
                  <td>${escapeHtml(formatMetricValue('pct', row?.left?.win_rate))}</td>
                  <td>${escapeHtml(formatMetricValue('pct', row?.right?.win_rate))}</td>
                  <td>${escapeHtml(formatMetricValue('count', row?.left?.trades))}</td>
                  <td>${escapeHtml(formatMetricValue('count', row?.right?.trades))}</td>
                  <td class="compare-metric-delta compare-metric-delta--${escapeHtml(row?.classification || 'neutral')}">${escapeHtml(formatMetricValue('pct', row?.delta?.profit_total_pct, '', { signed: true }))}</td>
                  <td>${escapeHtml(formatMetricValue('pct', row?.delta?.win_rate, '', { signed: true }))}</td>
                  <td>${escapeHtml(formatMetricValue('count', row?.delta?.trades, '', { signed: true }))}</td>
                  <td>${renderDecisionBadge(row?.classification)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      ` : '<div class="results-context__note">No persisted pair breakdown is available for this compare.</div>'}
    </section>
  `;
}

function renderDiagnosisDelta(comparison) {
  const delta = comparison?.diagnosis_delta || {};
  return `
    <section class="results-context compare-decision-section">
      <div class="results-context__title">Diagnosis Delta</div>
      <div class="results-context__meta compare-pair-summary-grid">
        <span><strong>Resolved Rules:</strong> ${escapeHtml(String((delta?.resolved_rules || []).length))}</span>
        <span><strong>New Rules:</strong> ${escapeHtml(String((delta?.new_rules || []).length))}</span>
        <span><strong>Persistent Rules:</strong> ${escapeHtml(String((delta?.persistent_rules || []).length))}</span>
        <span><strong>Worst Pair Before:</strong> ${escapeHtml(delta?.worst_pair_before || '-')}</span>
        <span><strong>Worst Pair After:</strong> ${escapeHtml(delta?.worst_pair_after || '-')}</span>
      </div>
      <div class="results-context__note">Deterministic-only diagnosis evidence from persisted summaries, request snapshots, and run-linked versions.</div>
      <div class="compare-diagnosis-grid">
        ${renderRuleList('Resolved Rules', delta?.resolved_rules, 'No deterministic rules were resolved by the selected candidate.')}
        ${renderRuleList('New Rules', delta?.new_rules, 'No new deterministic rules appeared on the selected candidate.')}
        ${renderRuleList('Persistent Rules', delta?.persistent_rules, 'No deterministic rules persisted across baseline and candidate.')}
      </div>
    </section>
  `;
}

export function renderDecisionReadyCompare(comparison, options = {}) {
  const metricRows = Array.isArray(comparison?.metrics) ? comparison.metrics : [];
  const pairRows = Array.isArray(comparison?.pairs?.rows) ? comparison.pairs.rows : [];
  const improvedCount = countClassification(metricRows, "improved");
  const regressedCount = countClassification(metricRows, "regressed");
  const improvedPairsCount = countClassification(pairRows, "improved");
  const regressedPairsCount = countClassification(pairRows, "regressed");
  const hasDeltas = improvedCount > 0 || regressedCount > 0 || improvedPairsCount > 0 || regressedPairsCount > 0;

  let sections = `${renderDecisionSnapshot(comparison, options)}`;
  
  if (hasDeltas) {
    sections += renderSectionDetails('Metrics Delta', renderMetricTable(comparison, options), `${improvedCount} improved / ${regressedCount} regressed`, false);
    sections += renderSectionDetails('Pair Delta', renderPairTable(comparison, options), `${improvedPairsCount} improved / ${regressedPairsCount} regressed`, false);
  }
  
  return sections;
  `;
}
