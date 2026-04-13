# 4tie / EWS - Product Overview

## Project Purpose

4tie (EWS - Evolutionary Workflow System) is an AI-powered trading strategy optimization and backtesting platform built on Freqtrade. It provides a comprehensive web-based control panel for creating, testing, comparing, and evolving cryptocurrency trading strategies through intelligent candidate generation and deterministic analysis.

## Core Value Proposition

- **Intelligent Strategy Evolution**: AI-driven candidate generation from backtest diagnosis and parameter suggestions
- **Decision-Ready Comparisons**: Version-aware baseline vs. selected candidate analysis with deterministic diagnosis deltas
- **Isolated Workflow Execution**: Candidate reruns in isolated workspaces with version-exact reproducibility
- **Multi-Model AI Support**: Flexible routing between OpenAI, Ollama, HuggingFace, and OpenRouter providers
- **Persistent Chat Integration**: Shared AI chat drawer across all workflow surfaces for continuous strategy refinement

## Key Features

### Backtesting & Analysis
- Freqtrade-native backtest execution and result ingestion
- Comprehensive backtest history and comparison workflows
- Deterministic diagnosis service for identifying trading issues
- Pair-level performance analysis with improved/regressed classification
- Parameter and code diff visualization

### Candidate Management
- Versioned strategy candidates with canonical-first approach
- Parameter-only and code-patch candidate modes
- Deterministic and AI-driven proposal actions
- Staged candidate creation without live file writes
- Version promotion and rollback workflows

### AI Integration
- Multi-provider model routing with configurable policies
- AI chat loop service with streaming support
- Strategy intelligence service for diagnosis-driven recommendations
- Deep analysis tools for backtest result interpretation
- Context-aware prompt building from backtest metrics and diagnosis

### Configuration & Settings
- Freqtrade path and executable configuration
- Ollama endpoint and model selection
- OpenAI API key management
- Theme and UI preferences
- Default trading pair and timeframe settings

## Target Users

- **Quantitative Traders**: Develop and optimize algorithmic trading strategies
- **Strategy Developers**: Iterate on strategy logic with AI-assisted recommendations
- **Backtesting Engineers**: Analyze historical performance and identify improvement opportunities
- **Freqtrade Users**: Leverage existing Freqtrade infrastructure with enhanced UI and AI capabilities

## Use Cases

1. **Strategy Optimization Loop**: Run backtest → analyze diagnosis → generate AI candidates → compare → promote
2. **Parameter Tuning**: Use AI suggestions to adjust strategy parameters based on backtest results
3. **Code Evolution**: Generate code patches for strategy improvements with isolated testing
4. **Performance Diagnosis**: Identify root causes of poor performance through deterministic analysis
5. **Multi-Strategy Comparison**: Compare baseline vs. evolved candidates with detailed diff analysis
