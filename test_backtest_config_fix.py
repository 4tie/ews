"""
Test for freqtrade backtest command generation with empty parameter snapshots.

This verifies the fix for the "[stream] Connection closed" issue that occurred
when versions had no parameters (resulting in empty config.version.json being passed to freqtrade).
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

from app.models.optimizer_models import ChangeType, MutationRequest
from app.services.freqtrade_cli_service import FreqtradeCliService
from app.services.mutation_service import mutation_service


def test_empty_parameters_doesnt_create_overlay_config() -> None:
    """
    Test that when a version has no parameters, we don't pass an empty config overlay to freqtrade.
    
    Verifies the fix for: "[stream] Connection closed" error where empty config.version.json
    was being passed to freqtrade, causing it to fail immediately.
    """
    tmpdir = tempfile.mkdtemp(prefix="backtest_test_")
    
    try:
        # Setup paths
        results_dir = os.path.join(tmpdir, "user_data", "backtest_results", "TestStrat")
        runs_dir = os.path.join(tmpdir, "data", "backtest_runs", "bt-test-123")
        os.makedirs(results_dir, exist_ok=True)
        os.makedirs(runs_dir, exist_ok=True)
        
        # Create a main config file
        config_dir = os.path.join(tmpdir, "user_data")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump({
                "strategy": "TestStrat",
                "stake_currency": "USDT",
                "exchange": {"name": "binance"},
                "pair_whitelist": ["BTC/USDT"],
            }, f)
        
        # Create a version with NO parameters (only code)
        strategy_name = "TestStrat"
        version = mutation_service.create_mutation(
            MutationRequest(
                strategy_name=strategy_name,
                change_type=ChangeType.MANUAL,
                summary="Test version with no parameters",
                created_by="test",
                code="class TestStrat:\n    pass\n",
                parameters=None,  # No parameters!
            )
        )
        
        # Create CLI service with mocked settings
        cli_service = FreqtradeCliService()
        
        with patch.object(cli_service, '_settings') as mock_settings:
            mock_settings.return_value = {
                "user_data_path": tmpdir,
                "freqtrade_path": "freqtrade",
                "config_path": config_path,
            }
            
            with patch.object(cli_service, '_freqtrade_path', return_value="freqtrade"):
                with patch.object(cli_service, '_user_data_path', return_value=tmpdir):
                    with patch('app.utils.command_builder.resolve_freqtrade_executable', return_value="freqtrade.exe"):
                        # Prepare a backtest run with this version
                        prepared = cli_service.prepare_backtest_run({
                            "strategy": strategy_name,
                            "run_id": "bt-test-123",
                            "version_id": version.version_id,
                            "timeframe": "5m",
                            "pairs": ["BTC/USDT"],
                            "timerange": "20250101-20260101",
                            "dry_run_wallet": 1000,
                            "max_open_trades": 1,
                        })
        
        # Verify that config_paths only contains the main config (NOT the overlay)
        config_paths = prepared["config_paths"]
        assert len(config_paths) == 1, f"Expected 1 config path, got {len(config_paths)}: {config_paths}"
        assert config_paths[0] == config_path, f"Expected main config, got {config_paths[0]}"
        
        # Verify that config_overlay_path is None (wasn't created)
        assert prepared["config_overlay_path"] is None, "config_overlay_path should be None"
        
        # Verify the command doesn't include the overlay config
        command_str = prepared["command"]
        assert "--config" in command_str  # Should have the main config
        # Count how many --config flags there are
        config_count = command_str.count(" --config ")
        assert config_count == 1, f"Expected 1 --config flag, but command has {config_count}: {command_str}"
        
        print("[PASS] Empty parameters don't create overlay config file")
        print(f"       Command: {command_str[:100]}...")
        
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_with_parameters_creates_overlay_config() -> None:
    """
    Test that when a version HAS parameters, we DO create and pass the overlay config.
    
    This is the normal case - verifies we don't break the parameter override mechanism.
    """
    tmpdir = tempfile.mkdtemp(prefix="backtest_test_")
    
    try:
        # Setup paths
        results_dir = os.path.join(tmpdir, "user_data", "backtest_results", "TestStrat")
        runs_dir = os.path.join(tmpdir, "data", "backtest_runs", "bt-test-456")
        os.makedirs(results_dir, exist_ok=True)
        os.makedirs(runs_dir, exist_ok=True)
        
        # Create a main config file
        config_dir = os.path.join(tmpdir, "user_data")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "config.json")
        with open(config_path, "w") as f:
            json.dump({
                "strategy": "TestStrat",
                "stake_currency": "USDT",
                "exchange": {"name": "binance"},
                "pair_whitelist": ["BTC/USDT"],
            }, f)
        
        # Create a version WITH parameters
        strategy_name = "TestStrat"
        parameters = {"buy_rsi": 30, "sell_rsi": 70}
        version = mutation_service.create_mutation(
            MutationRequest(
                strategy_name=strategy_name,
                change_type=ChangeType.MANUAL,
                summary="Test version with parameters",
                created_by="test",
                code="class TestStrat:\n    pass\n",
                parameters=parameters,  # Has parameters!
            )
        )
        
        # Create CLI service with mocked settings
        cli_service = FreqtradeCliService()
        
        with patch.object(cli_service, '_settings') as mock_settings:
            mock_settings.return_value = {
                "user_data_path": tmpdir,
                "freqtrade_path": "freqtrade",
                "config_path": config_path,
            }
            
            with patch.object(cli_service, '_freqtrade_path', return_value="freqtrade"):
                with patch.object(cli_service, '_user_data_path', return_value=tmpdir):
                    with patch('app.utils.command_builder.resolve_freqtrade_executable', return_value="freqtrade.exe"):
                        # Prepare a backtest run with this version
                        prepared = cli_service.prepare_backtest_run({
                            "strategy": strategy_name,
                            "run_id": "bt-test-456",
                            "version_id": version.version_id,
                            "timeframe": "5m",
                            "pairs": ["BTC/USDT"],
                            "timerange": "20250101-20260101",
                            "dry_run_wallet": 1000,
                            "max_open_trades": 1,
                        })
        
        # Verify that config_paths contains BOTH the main config AND the overlay
        config_paths = prepared["config_paths"]
        assert len(config_paths) == 2, f"Expected 2 config paths, got {len(config_paths)}: {config_paths}"
        assert config_paths[0] == config_path, f"First config should be main config"
        
        # Verify that config_overlay_path was set
        overlay_path = prepared["config_overlay_path"]
        assert overlay_path is not None, "config_overlay_path should not be None"
        assert overlay_path == config_paths[1], "config_overlay_path should match second config path"
        
        # Verify the overlay file exists and contains the parameters
        assert os.path.isfile(overlay_path), f"Overlay config file should exist: {overlay_path}"
        with open(overlay_path, "r") as f:
            overlay_content = json.load(f)
        assert overlay_content == parameters, f"Overlay should contain parameters: {overlay_content}"
        
        # Verify the command includes both configs
        command_str = prepared["command"]
        config_count = command_str.count(" --config ")
        assert config_count == 2, f"Expected 2 --config flags, but command has {config_count}: {command_str}"
        
        print("[PASS] Parameters create overlay config file correctly")
        print(f"       Overlay path: {overlay_path}")
        print(f"       Parameters: {overlay_content}")
        
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_empty_parameters_doesnt_create_overlay_config()
    test_with_parameters_creates_overlay_config()
    print("\n✅ All backtest config generation tests passed!")
