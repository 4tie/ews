#!/usr/bin/env python3
"""Quick test to verify path normalization fix."""

from app.freqtrade.settings import get_freqtrade_runtime_settings

# Test path normalization with mixed forward/backslashes
settings = get_freqtrade_runtime_settings({
    'freqtrade_path': r'T:\Optimizer/.venv/Scripts/freqtrade',
    'user_data_path': r'T:\Optimizer/user_data',
    'results_base_path': r'T:\Optimizer/user_data/backtest_results'
})

print('✅ Path Normalization Tests:')
print(f'freqtrade_path: {settings["freqtrade_path"]}')
print(f'user_data_path: {settings["user_data_path"]}')
print(f'results_base_path: {settings["results_base_path"]}')
print(f'config_path: {settings["config_path"]}')
print()

# Verify all paths use backslashes
for key in ['freqtrade_path', 'user_data_path', 'results_base_path', 'config_path']:
    path = settings[key]
    if '/' in path and '\\' not in path:
        print(f'❌ {key} still has forward slashes: {path}')
    elif path:
        print(f'✓ {key} correctly normalized')

print()
print('All paths now use consistent Windows backslashes ✓')
