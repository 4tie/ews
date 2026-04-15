const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5000';

function buildRun(runId, versionId, extras = {}) {
  return {
    run_id: runId,
    strategy: 'TestStrat',
    version_id: versionId,
    status: 'completed',
    summary_available: true,
    trigger_source: 'manual',
    created_at: '2026-01-01T00:00:00',
    completed_at: '2026-01-01T01:00:00',
    summary_metrics: {
      strategy: 'TestStrat',
      trade_start: '2026-01-01T00:00:00',
      trade_end: '2026-01-01T01:00:00',
      timeframe: '1h',
      stake_currency: 'USDT',
    },
    request_snapshot: {
      strategy: 'TestStrat',
      timeframe: '1h',
      timerange: '20260101-20260131',
      exchange: 'binance',
      pairs: ['BTC/USDT', 'ETH/USDT'],
      config_path: 'user_data/config.json',
      extra_flags: [],
    },
    ...extras,
  };
}

function buildVersion(versionId, baselineRunId, createdAt, extras = {}) {
  return {
    version_id: versionId,
    strategy_name: 'TestStrat',
    parent_version_id: 'v-live',
    source_ref: `backtest_run:${baselineRunId}`,
    status: 'candidate',
    change_type: 'parameter_change',
    summary: `Candidate ${versionId}`,
    created_at: createdAt,
    source_context: {
      title: `Candidate ${versionId}`,
      candidate_mode: 'parameter_only',
    },
    audit_events: [],
    ...extras,
  };
}

function buildResultsPayload(runId, versionId) {
  return {
    strategy: 'TestStrat',
    run_id: runId,
    version_id: versionId,
    summary_available: true,
    diagnosis_status: 'ready',
    summary_metrics: {
      trade_start: '2026-01-01T00:00:00',
      trade_end: '2026-01-01T01:00:00',
      stake_currency: 'USDT',
    },
    diagnosis: {
      primary_flags: [],
      ranked_issues: [],
      parameter_hints: [],
      proposal_actions: [],
    },
    ai: {
      ai_status: 'ready',
      suggestions: [],
    },
  };
}

function buildComparePayload(leftRun, rightRun) {
  return {
    left: leftRun,
    right: rightRun,
    metrics: [
      {
        key: 'profit_total_pct',
        label: 'Total Profit %',
        format: 'pct',
        left: 1,
        right: 2,
        delta: 1,
        classification: 'improved',
        reason: 'Higher profit is better.',
      },
    ],
    versions: {},
    version_diff: {
      baseline_version_id: leftRun.version_id,
      candidate_version_id: rightRun.version_id,
      candidate_parent_version_id: null,
      baseline_version_source: 'run',
      source_kind: null,
      source_title: null,
      candidate_mode: null,
      change_type: null,
      summary: null,
      action_type: null,
      rule: null,
      matched_rules: [],
      parameter_diff_rows: [],
      code_diff: {
        changed: false,
        added_lines: 0,
        removed_lines: 0,
        diff_ref: null,
        summary: 'No persisted code changes were detected between baseline and candidate.',
        preview_blocks: [],
        preview_truncated: false,
      },
      request_snapshot_diff: {
        warnings: [],
        rows: [],
        summary: { changed: 0 },
      },
    },
    pairs: {
      rows: [],
      summary: {
        improved_count: 0,
        regressed_count: 0,
        changed_count: 0,
        neutral_count: 0,
      },
      top_improvements: [],
      top_regressions: [],
      worst_pair_change: { before: {}, after: {} },
      pair_dragger_evidence: { status: 'none', before: {}, after: {} },
    },
    diagnosis_delta: {
      resolved_rules: [],
      new_rules: [],
      persistent_rules: [],
      worst_pair_before: null,
      worst_pair_after: null,
    },
  };
}

function buildThread(runId, versionId) {
  return {
    strategy_name: 'TestStrat',
    latest_context: {
      strategy: 'TestStrat',
      run_id: runId,
      version_id: versionId,
      diagnosis_status: 'ready',
      summary_available: true,
      version_source: 'run',
    },
    active_job: null,
    messages: [
      {
        id: 'assistant-1',
        role: 'assistant',
        title: 'AI',
        text: 'Tighten stoploss for the current baseline.',
        parameters: {
          stoploss: -0.1,
        },
      },
    ],
  };
}

async function installApiMocks(page, state) {
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const method = request.method();

    if (pathname === '/api/backtest/options') {
      return route.fulfill({ json: { strategies: ['TestStrat'], timeframes: ['1h'], exchanges: ['binance'] } });
    }
    if (pathname === '/api/settings') {
      return route.fulfill({ json: { default_timeframe: '1h', default_exchange: 'binance' } });
    }
    if (pathname === '/api/backtest/runs') {
      return route.fulfill({ json: { runs: state.runs } });
    }
    if (/^\/api\/backtest\/runs\/[^/]+$/.test(pathname)) {
      const runId = decodeURIComponent(pathname.split('/').pop());
      const run = state.runs.find((entry) => entry.run_id === runId) || null;
      return route.fulfill({ json: { run } });
    }
    if (pathname === '/api/backtest/configs') {
      return route.fulfill({ json: { configs: [] } });
    }
    if (pathname === '/api/backtest/summary') {
      return route.fulfill({ json: { summary: null } });
    }
    if (pathname === '/api/backtest/trades') {
      return route.fulfill({ json: { trades: [] } });
    }
    if (pathname === '/api/backtest/compare') {
      return route.fulfill({ json: state.comparePayload });
    }
    if (pathname === '/api/backtest/runs/bt-base/proposal-candidates' && method === 'POST') {
      const created = buildVersion('v-chat-1', 'bt-base', '2026-01-01T00:02:00', {
        summary: 'Drawer candidate',
        source_context: {
          title: 'Drawer candidate',
          candidate_mode: 'parameter_only',
        },
      });
      state.versions = [created, ...state.versions.filter((entry) => entry.version_id !== created.version_id)];
      return route.fulfill({
        json: {
          candidate_version_id: created.version_id,
          candidate_change_type: created.change_type,
          candidate_status: created.status,
          baseline_run_id: 'bt-base',
          baseline_version_id: 'v-live',
          baseline_run_version_id: 'v-live',
          baseline_version_source: 'run',
          source_kind: 'ai_chat_draft',
          source_title: 'Drawer candidate',
          message: 'Candidate version created.',
        },
      });
    }
    if (pathname === '/api/versions/TestStrat' && url.searchParams.get('include_archived') === 'true') {
      return route.fulfill({ json: { versions: state.versions, active_version_id: 'v-live' } });
    }
    if (pathname === '/api/versions/TestStrat/active') {
      return route.fulfill({ json: { version_id: 'v-live', strategy_name: 'TestStrat', code_snapshot: 'class TestStrat: pass' } });
    }
    if (/^\/api\/versions\/TestStrat\/[^/]+$/.test(pathname)) {
      const versionId = decodeURIComponent(pathname.split('/').pop());
      const version = state.versions.find((entry) => entry.version_id === versionId) || { version_id: versionId, strategy_name: 'TestStrat', code_snapshot: 'class TestStrat: pass' };
      return route.fulfill({ json: version });
    }
    if (pathname === '/api/ai/chat/threads/TestStrat') {
      return route.fulfill({ json: state.thread });
    }

    return route.fulfill({ json: {} });
  });
}

async function openBacktesting(page, state) {
  await installApiMocks(page, state);
  await page.goto(`${BASE_URL}/backtesting`);
  await page.waitForFunction(() => Boolean(window._events && window._appState));
  await expect(page.locator('#select-strategy')).toHaveValue('TestStrat');
}

async function emitResultsLoaded(page, payload) {
  await page.evaluate((data) => {
    window._events.emit(window._events.EVENTS.RESULTS_LOADED, data);
  }, payload);
}

test('workflow compare falls back to generic compare when the baseline has no candidates', async ({ page }) => {
  const baselineRun = buildRun('bt-base', 'v-live');
  const altRun = buildRun('bt-alt', 'v-alt', {
    strategy: 'AltStrat',
    summary_metrics: {
      strategy: 'AltStrat',
      trade_start: '2026-01-02T00:00:00',
      trade_end: '2026-01-02T01:00:00',
      timeframe: '4h',
      stake_currency: 'USDT',
    },
    request_snapshot: {
      strategy: 'AltStrat',
      timeframe: '4h',
      timerange: '20260201-20260228',
      exchange: 'kraken',
      pairs: ['SOL/USDT'],
      config_path: 'user_data/alt-config.json',
      extra_flags: [],
    },
  });
  const state = {
    runs: [baselineRun, altRun],
    versions: [],
    comparePayload: buildComparePayload(baselineRun, altRun),
    thread: buildThread('bt-base', 'v-live'),
  };

  await openBacktesting(page, state);
  await emitResultsLoaded(page, buildResultsPayload('bt-base', 'v-live'));

  await page.locator('#results-tabs [data-tab="compare"]').click();

  await expect(page.locator('#compare-area')).toContainText('Generic compare is still available across persisted runs, including different strategies.');
  await expect(page.locator('#compare-left-run')).toHaveCount(1);
  await expect(page.locator('#compare-right-run')).toHaveCount(1);
  await expect(page.locator('#compare-left-run')).toHaveValue('bt-base');
  await expect(page.locator('#compare-right-run')).toHaveValue('bt-alt');
  await expect(page.locator('#compare-area')).toContainText('AltStrat');
});

test('selected candidate stays pinned per baseline run', async ({ page }) => {
  const state = {
    runs: [buildRun('bt-base', 'v-live'), buildRun('bt-other', 'v-live')],
    versions: [
      buildVersion('v-base-new', 'bt-base', '2026-01-01T00:05:00'),
      buildVersion('v-base-old', 'bt-base', '2026-01-01T00:01:00'),
      buildVersion('v-other-only', 'bt-other', '2026-01-01T00:03:00'),
    ],
    comparePayload: {},
    thread: buildThread('bt-base', 'v-live'),
  };

  await openBacktesting(page, state);
  await emitResultsLoaded(page, buildResultsPayload('bt-base', 'v-live'));

  const candidateSelector = page.locator('#summary-proposals select[data-role="selected-candidate"]');
  await expect(candidateSelector).toHaveValue('v-base-new');
  await candidateSelector.selectOption('v-base-old');
  await expect(candidateSelector).toHaveValue('v-base-old');

  await emitResultsLoaded(page, buildResultsPayload('bt-other', 'v-live'));
  await expect(page.locator('#summary-proposals')).toContainText('Selected Candidate');

  await emitResultsLoaded(page, buildResultsPayload('bt-base', 'v-live'));
  await expect(page.locator('#summary-proposals select[data-role="selected-candidate"]')).toHaveValue('v-base-old');
});

test('shared drawer candidate creation selects the created candidate across workflow surfaces', async ({ page }) => {
  const state = {
    runs: [buildRun('bt-base', 'v-live')],
    versions: [],
    comparePayload: {},
    thread: buildThread('bt-base', 'v-live'),
  };

  await openBacktesting(page, state);
  await emitResultsLoaded(page, buildResultsPayload('bt-base', 'v-live'));

  await page.locator('#btn-open-ai-chat').click();
  await expect(page.locator('#ai-chat-panel')).toHaveAttribute('aria-hidden', 'false');
  await expect(page.getByRole('button', { name: 'Create parameter candidate' })).toBeEnabled();

  await page.getByRole('button', { name: 'Create parameter candidate' }).click();

  await expect(page.locator('#summary-proposals')).toContainText('Selected Candidate: v-chat-1');
  await page.locator('#results-tabs [data-tab="compare"]').click();
  await expect(page.locator('#compare-selected-candidate')).toHaveValue('v-chat-1');
  await expect(page.locator('#compare-left-run')).toHaveCount(0);
  await expect(page.locator('#compare-right-run')).toHaveCount(0);
});
