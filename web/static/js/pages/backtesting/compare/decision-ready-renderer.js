/**
 * decision-ready-renderer.js - Shared baseline-vs-candidate compare rendering helpers.
 */

import { formatNum, formatPct } from "../../../core/utils.js";

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
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

function collectMetricLabels(rows, classification) {
  return (Array.isArray(rows) ? rows : [])
    .filter((row) => row?.classification === classification)
    .map((row) => row?.label || row?.key || "Metric");
}

function renderMetricHighlights(rows) {
  return `
    <div class="compare-diagnosis-grid">
      ${renderRuleList("Improved", collectMetricLabels(rows, "improved"), "No metrics improved on the selected candidate.")}
      ${renderRuleList("Regressed", collectMetricLabels(rows, "regressed"), "No metrics regressed on the selected candidate.")}
      ${renderRuleList("Changed", collectMetricLabels(rows, "changed"), "No metrics changed without a directional verdict.")}
    </div>
  `;
}

function renderParameterDiffTable(versionDiff) {
  const rows = Array.isArray(versionDiff?.parameter_diff_rows) ? versionDiff.parameter_diff_rows : [];
  if (!rows.length) {
    return '<div class="results-context__note">No persisted parameter diff was detected between baseline and selected candidate.</div>';
  }

  return `
    <div class="results-context__table">
      <table class="data-table compare-table compare-diff-table">
        <thead>
          <tr>
            <th>Status</th>
            <th>Parameter Path</th>
            <th>Baseline</th>
            <th>Selected Candidate</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${renderDecisionBadge(row?.status || "changed")}</td>
              <td class="mono">${escapeHtml(row?.path || "-")}</td>
              <td>${escapeHtml(formatCompactValue(row?.before))}</td>
              <td>${escapeHtml(formatCompactValue(row?.after))}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderCodeDiff(versionDiff) {
  const codeDiff = versionDiff?.code_diff || {};
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
  `;
}

function renderMetricTable(comparison, options = {}) {
  const baselineLabel = options.baselineLabel || "Baseline";
  const candidateLabel = options.candidateLabel || "Selected Candidate";
  const rows = Array.isArray(comparison?.metrics) ? comparison.metrics : [];
  const leftCurrency = comparison?.left?.summary_metrics?.stake_currency || "";
  const rightCurrency = comparison?.right?.summary_metrics?.stake_currency || leftCurrency;

  return `
    <section class="results-context results-context--table compare-decision-section">
      <div class="results-context__title">Decision Metrics</div>
      ${renderMetricHighlights(rows)}
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
                    <div>${escapeHtml(metric?.label || "-")}</div>
                    <div class="compare-cell-note">${escapeHtml(metric?.reason || "")}</div>
                  </td>
                  <td>${escapeHtml(formatMetricValue(metric?.format, metric?.left, leftCurrency))}</td>
                  <td>${escapeHtml(formatMetricValue(metric?.format, metric?.right, rightCurrency))}</td>
                  <td class="compare-metric-delta compare-metric-delta--${escapeHtml(metric?.classification || "neutral")}">${escapeHtml(formatMetricValue(metric?.format, metric?.delta, rightCurrency, { signed: true }))}</td>
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
      <div class="results-context__note">Deterministic-only diagnosis evidence from persisted summaries, request snapshots, and run-linked versions.</div>
      <div class="compare-diagnosis-grid">
        ${renderRuleList('Resolved Rules', delta?.resolved_rules, 'No deterministic rules were resolved by the selected candidate.')}
        ${renderRuleList('New Rules', delta?.new_rules, 'No new deterministic rules appeared on the selected candidate.')}
        ${renderRuleList('Persistent Rules', delta?.persistent_rules, 'No deterministic rules persisted across baseline and candidate.')}
      </div>
      <div class="results-context__meta compare-pair-summary-grid">
        <span><strong>Worst Pair Before:</strong> ${escapeHtml(delta?.worst_pair_before || '-')}</span>
        <span><strong>Worst Pair After:</strong> ${escapeHtml(delta?.worst_pair_after || '-')}</span>
      </div>
    </section>
  `;
}

export function renderDecisionReadyCompare(comparison, options = {}) {
  const versionDiff = comparison?.version_diff || {};
  const baselineLabel = options.baselineLabel || 'Baseline';
  const candidateLabel = options.candidateLabel || 'Selected Candidate';
  const summaryText = versionDiff?.summary || 'No persisted candidate summary is available.';
  const matchedRules = Array.isArray(versionDiff?.matched_rules) ? versionDiff.matched_rules : [];

  return `
    <section class="results-context results-context--table compare-decision-section">
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
      ${renderParameterDiffTable(versionDiff)}
      ${renderCodeDiff(versionDiff)}
    </section>
    ${renderMetricTable(comparison, { baselineLabel, candidateLabel })}
    ${renderPairTable(comparison, { baselineLabel, candidateLabel })}
    ${renderDiagnosisDelta(comparison)}
  `;
}
