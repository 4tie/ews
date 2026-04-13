# Project Structure & Architecture

## Directory Organization

```
t:\Optimizer/
├── app/                          # Backend application (Python/FastAPI)
│   ├── ai/                       # AI integration layer
│   │   ├── memory/              # Chat thread persistence
│   │   ├── models/              # Multi-provider model routing
│   │   ├── pipelines/           # AI orchestration and classification
│   │   ├── prompts/             # Trading-specific prompt templates
│   │   ├── tools/               # Deep analysis and context tools
│   │   ├── context_builder.py   # Backtest context assembly
│   │   └── output_format.py     # AI response formatting
│   ├── engines/                 # Engine abstraction layer
│   │   ├── base.py              # Base engine interface
│   │   └── resolver.py          # Engine selection logic
│   ├── freqtrade/               # Freqtrade integration
│   │   ├── cli_service.py       # CLI command execution
│   │   ├── commands.py          # Freqtrade command definitions
│   │   ├── engine.py            # Freqtrade engine implementation
│   │   ├── executable.py        # Executable path resolution
│   │   ├── paths.py             # Path management
│   │   ├── result_parser.py     # Backtest result parsing
│   │   ├── runtime.py           # Runtime environment setup
│   │   └── settings.py          # Freqtrade settings
│   ├── models/                  # Data models
│   │   ├── backtest_models.py   # Backtest result schemas
│   │   ├── optimizer_models.py  # Optimizer run schemas
│   │   └── settings_models.py   # Configuration schemas
│   ├── routers/                 # API endpoints
│   │   ├── ai_chat.py           # AI chat endpoints
│   │   ├── backtest.py          # Backtest workflow endpoints
│   │   ├── evolution.py         # Strategy evolution endpoints
│   │   ├── optimizer.py         # Optimizer endpoints
│   │   ├── settings.py          # Settings endpoints
│   │   ├── versions.py          # Version management endpoints
│   │   └── web_ui_routes.py     # Web UI template routes
│   ├── services/                # Business logic layer
│   │   ├── ai_chat/             # Chat persistence and loop service
│   │   ├── autotune/            # Iterative optimization
│   │   ├── results/             # Diagnosis and intelligence services
│   │   ├── config_service.py    # Configuration management
│   │   ├── mutation_service.py  # Strategy mutation logic
│   │   ├── persistence_service.py # Data persistence
│   │   ├── results_service.py   # Backtest result handling
│   │   └── validation_service.py # Input validation
│   ├── storage/                 # Data storage layer
│   ├── utils/                   # Utility functions
│   └── main.py                  # FastAPI app initialization
├── web/                         # Frontend (HTML/CSS/JavaScript)
│   ├── static/
│   │   ├── css/                 # Stylesheets
│   │   └── js/                  # JavaScript modules
│   │       ├── components/      # Reusable UI components
│   │       ├── core/            # Core utilities (API, state, theme)
│   │       └── pages/           # Page-specific logic
│   │           ├── backtesting/ # Backtest workflow UI
│   │           ├── optimizer/   # Optimizer workflow UI
│   │           ├── settings/    # Settings UI
│   │           └── shared/      # Shared components
│   └── templates/               # Jinja2 templates
│       ├── pages/               # Page templates
│       ├── partials/            # Partial templates
│       └── base.html            # Base template
├── data/                        # Runtime data storage
│   ├── ai_chat_jobs/            # AI chat job records
│   ├── ai_chat_threads/         # Chat thread persistence
│   ├── backtest_runs/           # Backtest execution workspaces
│   ├── download_runs/           # Download job tracking
│   ├── optimizer_runs/          # Optimizer execution records
│   ├── saved_configs/           # User-saved configurations
│   ├── settings/                # Application settings
│   └── versions/                # Strategy version snapshots
├── user_data/                   # Freqtrade user data
│   ├── backtest_results/        # Backtest result archives
│   ├── config/                  # Freqtrade config files
│   ├── data/                    # Market data
│   ├── strategies/              # Strategy files
│   └── config.json              # Main Freqtrade config
├── rules/                       # Development rules and guidelines
└── .amazonq/rules/memory-bank/  # Memory bank documentation
```

## Core Components & Relationships

### Backend Architecture

**API Layer** (routers/)
- Exposes REST endpoints for frontend consumption
- Routes requests to appropriate service layer
- Handles request validation and response formatting

**Service Layer** (services/)
- `results_service.py`: Orchestrates backtest result ingestion and analysis
- `strategy_intelligence_service.py`: Generates diagnosis and proposals from backtest results
- `strategy_intelligence_apply_service.py`: Applies AI recommendations to create candidates
- `ai_chat/loop_service.py`: Manages AI conversation loops with streaming
- `ai_chat/persistent_chat_service.py`: Persists chat threads to disk
- `mutation_service.py`: Handles strategy parameter and code mutations
- `persistence_service.py`: Manages data serialization and storage

**AI Integration** (ai/)
- `models/provider_dispatch.py`: Routes requests to configured AI provider
- `models/model_routing_policy.py`: Determines model selection based on task
- `pipelines/orchestrator.py`: Coordinates multi-step AI workflows
- `context_builder.py`: Assembles backtest context for AI prompts
- `tools/deep_analysis.py`: Analyzes backtest results for insights

**Freqtrade Integration** (freqtrade/)
- `engine.py`: Freqtrade execution engine
- `cli_service.py`: Executes Freqtrade CLI commands
- `result_parser.py`: Parses backtest result JSON/ZIP files
- `runtime.py`: Sets up isolated execution environments

**Data Models** (models/)
- Pydantic schemas for type safety and validation
- Backtest result structures
- Optimizer run configurations
- Settings and configuration schemas

### Frontend Architecture

**Core Utilities** (js/core/)
- `api.js`: HTTP client for backend communication
- `state.js`: Global application state management
- `persistence.js`: Local storage and session management
- `theme.js`: Theme switching and styling
- `pair-parser.js`: Trading pair parsing and validation

**Components** (js/components/)
- Reusable UI elements (modals, toasts, forms)
- AI chat panel with streaming support
- Loading states and command previews

**Pages** (js/pages/)
- **Backtesting**: Run setup, history, results, compare, trades, charts
- **Optimizer**: Active results, checkpoints, live logs
- **Settings**: General, paths, Ollama, theme, defaults

## Architectural Patterns

### Workflow Invariants
- Candidate creation never writes live files (staged only)
- Promotion and rollback are the only live-write paths
- Reruns use version-exact isolated workspaces
- Compare workflow stays baseline-vs-selected-candidate

### Data Flow
1. **Backtest Execution**: User submits backtest → Freqtrade runs → Results stored
2. **Diagnosis**: Results ingested → Deterministic analysis → Issues identified
3. **Candidate Generation**: Diagnosis + AI → Parameter/code suggestions → Staged candidate
4. **Comparison**: Baseline vs. candidate → Diff analysis → Decision-ready output
5. **Promotion**: User accepts → Version promoted to live

### Isolation Strategy
- Each backtest run gets isolated workspace in `data/backtest_runs/{run_id}/workspace`
- Version snapshots stored in `data/versions/{strategy_name}/{version_id}`
- Reruns use version-exact parameters and code
- Results archived in `user_data/backtest_results/{strategy_name}`

### State Management
- Single selected candidate version across workflow surfaces
- Persistent state in `data/settings/app_settings.json`
- Chat threads persisted in `data/ai_chat_threads/{strategy_name}`
- Run metadata in `run_meta.json` as source of truth for linkage
