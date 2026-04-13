/**
 * options-loader.js - Fetch strategies, timeframes, exchanges from backend
 * and populate strategy/timeframe/exchange selects with deterministic fallbacks.
 */

import api from "../../../core/api.js";
import showToast from "../../../components/toast.js";
import persistence, { KEYS } from "../../../core/persistence.js";

const DEFAULT_SELECT_IDS = {
  strategy: "select-strategy",
  timeframe: "select-timeframe",
  exchange: "select-exchange",
};

const EMPTY_COPY = {
  strategies: "No strategies found",
  timeframes: "No timeframes available",
  exchanges: "No exchanges available",
};

const ERROR_COPY = {
  strategies: "Failed to load strategies",
  timeframes: "Failed to load timeframes",
  exchanges: "Failed to load exchanges",
};

function normalizeValue(value) {
  return String(value ?? "").trim();
}

function normalizeOptionList(values) {
  if (!Array.isArray(values)) return [];
  return [...new Set(values.map((value) => normalizeValue(value)).filter(Boolean))];
}

function getSelect(selectId) {
  return selectId ? document.getElementById(selectId) : null;
}

function getSavedBacktestConfig() {
  const saved = persistence.load(KEYS.BACKTEST_CONFIG, {});
  return saved && typeof saved === "object" ? saved : {};
}

function parseDefaultTimerange(timerange) {
  const value = normalizeValue(timerange);
  if (!value.includes("-")) {
    return { startDate: "", endDate: "" };
  }

  const [start, end] = value.split("-");
  return {
    startDate: start ? `${start.slice(0, 4)}-${start.slice(4, 6)}-${start.slice(6, 8)}` : "",
    endDate: end ? `${end.slice(0, 4)}-${end.slice(4, 6)}-${end.slice(6, 8)}` : "",
  };
}

function readExistingOptionValues(select) {
  if (!select) return [];
  return normalizeOptionList(Array.from(select.options).map((option) => option.value));
}

function renderSelectOptions(select, options, emptyText) {
  if (!select) return;

  select.innerHTML = "";
  if (!options.length) {
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = emptyText;
    emptyOption.disabled = true;
    emptyOption.selected = true;
    select.appendChild(emptyOption);
    select.disabled = true;
    return;
  }

  select.disabled = false;
  options.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
}

function resolveSelection(options, preferredValues = []) {
  const preferred = preferredValues.map((value) => normalizeValue(value)).filter(Boolean);
  for (const value of preferred) {
    if (options.includes(value)) {
      return value;
    }
  }
  return options[0] || "";
}

function applyResolvedSelection(select, options, preferredValues, emptyText) {
  renderSelectOptions(select, options, emptyText);
  const selected = resolveSelection(options, preferredValues);
  if (select && selected) {
    select.value = selected;
  }
  return selected;
}

function persistBacktestSelectionRepairs(savedConfig, selected, optionSets, shouldPersist) {
  if (!shouldPersist) return;

  const repairs = {};
  const savedStrategy = normalizeValue(savedConfig.strategy);
  const savedTimeframe = normalizeValue(savedConfig.timeframe);
  const savedExchange = normalizeValue(savedConfig.exchange);

  if (savedStrategy && !optionSets.strategies.includes(savedStrategy)) {
    repairs.strategy = selected.strategy || "";
  }
  if (savedTimeframe && !optionSets.timeframes.includes(savedTimeframe)) {
    repairs.timeframe = selected.timeframe || "";
  }
  if (savedExchange && optionSets.exchanges.length && !optionSets.exchanges.includes(savedExchange)) {
    repairs.exchange = selected.exchange || "";
  }

  if (Object.keys(repairs).length) {
    persistence.save(KEYS.BACKTEST_CONFIG, { ...savedConfig, ...repairs });
  }
}

export async function loadOptions(config = {}) {
  const {
    strategySelectId = DEFAULT_SELECT_IDS.strategy,
    timeframeSelectId = DEFAULT_SELECT_IDS.timeframe,
    exchangeSelectId = DEFAULT_SELECT_IDS.exchange,
    persistBacktestSelections = strategySelectId === DEFAULT_SELECT_IDS.strategy
      && timeframeSelectId === DEFAULT_SELECT_IDS.timeframe,
  } = config;

  const strategySelect = getSelect(strategySelectId);
  const timeframeSelect = getSelect(timeframeSelectId);
  const exchangeSelect = getSelect(exchangeSelectId);

  if (!strategySelect && !timeframeSelect && !exchangeSelect) {
    return {
      ok: false,
      strategies: [],
      timeframes: [],
      exchanges: [],
      settings: {},
      defaults: { startDate: "", endDate: "", dryRunWallet: null, maxOpenTrades: null },
      selected: { strategy: "", timeframe: "", exchange: "" },
      empty: { strategies: true, timeframes: true, exchanges: true },
      messages: {},
      errors: { options: "No option selects found on the page.", settings: "" },
    };
  }

  const savedConfig = getSavedBacktestConfig();
  const result = {
    ok: true,
    strategies: [],
    timeframes: [],
    exchanges: [],
    settings: {},
    defaults: {
      startDate: "",
      endDate: "",
      dryRunWallet: null,
      maxOpenTrades: null,
    },
    selected: {
      strategy: "",
      timeframe: "",
      exchange: "",
    },
    empty: {
      strategies: false,
      timeframes: false,
      exchanges: false,
    },
    messages: {
      strategies: "",
      timeframes: "",
      exchanges: "",
    },
    errors: {
      options: "",
      settings: "",
    },
  };

  const [optionsResponse, settingsResponse] = await Promise.allSettled([
    api.backtest.options(),
    api.settings.get(),
  ]);

  if (optionsResponse.status === "fulfilled") {
    result.strategies = normalizeOptionList(optionsResponse.value?.strategies);
    result.timeframes = normalizeOptionList(optionsResponse.value?.timeframes);
    result.exchanges = normalizeOptionList(optionsResponse.value?.exchanges);
  } else {
    result.ok = false;
    result.errors.options = optionsResponse.reason?.message || "Failed to load options.";
    showToast(`Failed to load options: ${result.errors.options}`, "error");
  }

  if (settingsResponse.status === "fulfilled") {
    result.settings = settingsResponse.value ?? {};
    result.defaults = {
      ...parseDefaultTimerange(result.settings.default_timerange),
      dryRunWallet: result.settings.default_dry_run_wallet ?? null,
      maxOpenTrades: result.settings.default_max_open_trades ?? null,
    };
  } else {
    result.errors.settings = settingsResponse.reason?.message || "Failed to load settings.";
    console.warn("[options-loader] Failed to load settings:", result.errors.settings);
  }

  const exchangeOptions = result.exchanges.length ? result.exchanges : readExistingOptionValues(exchangeSelect);

  result.messages.strategies = result.errors.options
    ? ERROR_COPY.strategies
    : result.strategies.length
      ? ""
      : EMPTY_COPY.strategies;
  result.messages.timeframes = result.errors.options
    ? ERROR_COPY.timeframes
    : result.timeframes.length
      ? ""
      : EMPTY_COPY.timeframes;
  result.messages.exchanges = result.errors.options && !exchangeOptions.length
    ? ERROR_COPY.exchanges
    : exchangeOptions.length
      ? ""
      : EMPTY_COPY.exchanges;

  result.selected.strategy = applyResolvedSelection(
    strategySelect,
    result.strategies,
    [savedConfig.strategy],
    result.messages.strategies || EMPTY_COPY.strategies,
  );
  result.selected.timeframe = applyResolvedSelection(
    timeframeSelect,
    result.timeframes,
    [savedConfig.timeframe, result.settings.default_timeframe],
    result.messages.timeframes || EMPTY_COPY.timeframes,
  );
  result.selected.exchange = applyResolvedSelection(
    exchangeSelect,
    exchangeOptions,
    [savedConfig.exchange, result.settings.default_exchange],
    result.messages.exchanges || EMPTY_COPY.exchanges,
  );

  result.empty = {
    strategies: !result.strategies.length,
    timeframes: !result.timeframes.length,
    exchanges: exchangeSelect ? !exchangeOptions.length : false,
  };

  persistBacktestSelectionRepairs(
    savedConfig,
    result.selected,
    {
      strategies: result.strategies,
      timeframes: result.timeframes,
      exchanges: exchangeOptions,
    },
    persistBacktestSelections,
  );

  return result;
}
