/**
 * options-loader.js — Load and populate strategy, timeframe, and exchange options.
 */

import api from "../../../core/api.js";
import showToast from "../../../components/toast.js";

export async function loadOptions() {
  try {
    const options = await api.backtest.options();
    
    // Populate strategies
    const strategySelect = document.getElementById("select-strategy");
    if (strategySelect && options.strategies) {
      options.strategies.forEach(strategy => {
        const option = document.createElement("option");
        option.value = strategy;
        option.textContent = strategy;
        strategySelect.appendChild(option);
      });
    }
    
    // Populate timeframes
    const timeframeSelect = document.getElementById("select-timeframe");
    if (timeframeSelect && options.timeframes) {
      options.timeframes.forEach(timeframe => {
        const option = document.createElement("option");
        option.value = timeframe;
        option.textContent = timeframe;
        timeframeSelect.appendChild(option);
      });
    }
    
    // Exchanges are already in HTML, but we could validate them
    // const exchangeSelect = document.getElementById("select-exchange");
    
  } catch (error) {
    showToast("Failed to load options: " + error.message, "error");
  }
}
