# Technology Stack & Development Setup

## Programming Languages & Versions

- **Python**: 3.11+ (required by pyproject.toml)
- **JavaScript**: ES6+ (modern browser support)
- **HTML/CSS**: HTML5, CSS3 with Flexbox/Grid

## Backend Stack

### Core Framework
- **FastAPI** (>=0.135.1): Async web framework for REST API
- **Uvicorn** (>=0.42.0): ASGI server with hot reload support
- **Jinja2** (>=3.1.6): Template engine for HTML rendering

### Trading & Analysis
- **Freqtrade** (>=2024.1): Trading bot framework and backtesting engine
- **Optuna**: Hyperparameter optimization
- **Datasieve**: Data processing utilities

### AI & LLM Integration
- **OpenAI** (>=1.0.0): OpenAI API client
- **httpx** (>=0.27.0): Async HTTP client for API calls
- **aiohttp** (>=3.9.0): Async HTTP library

### Utilities
- **aiofiles** (>=25.1.0): Async file I/O
- **python-multipart** (>=0.0.22): Multipart form data parsing
- **python-dotenv** (>=1.0.0): Environment variable management
- **filelock**: File locking for concurrent access
- **psutil**: System and process utilities

## Frontend Stack

### Core Libraries
- **Vanilla JavaScript**: No framework dependencies
- **Fetch API**: HTTP client for API communication
- **LocalStorage API**: Client-side persistence

### UI Components
- Custom modal system
- Toast notification system
- Form helpers and validation
- Loading state management
- Theme switching (light/dark)

## Build & Development Tools

### Python Development
- **pyproject.toml**: Project metadata and dependencies
- **requirements.txt**: Pinned dependency versions
- **Hot Reload**: Configured in `app/main.py` with exclusions for:
  - `data/backtest_runs/*/workspace`
  - `user_data/backtest_results/*`
  - `data/versions/*/*.json`

### JavaScript Development
- **Bun** (package manager): Configured in `.kilo/package.json`
- **No build step**: Direct ES6 module loading in browser

## Development Commands

### Starting the Application
```bash
# Primary startup method (with reload exclusions)
python app\main.py

# Alternative (not recommended - missing reload exclusions)
uvicorn app.main:app --reload
```

### Running Tests
```bash
# Test files follow pattern: test_*.py
python -m pytest test_ai_chat_apply_wrappers.py
python -m pytest test_backtest_run_control.py
python -m pytest test_strategy_intelligence_service.py
```

### Key Test Files
- `test_ai_chat_*.py`: AI chat functionality
- `test_backtest_*.py`: Backtest workflow
- `test_strategy_intelligence_*.py`: Diagnosis and intelligence
- `test_engine_selection.py`: Engine routing
- `test_deterministic_proposal_actions.py`: Proposal generation

## Configuration Files

### Application Configuration
- **pyproject.toml**: Project metadata, Python version, core dependencies
- **requirements.txt**: Extended dependencies including dev tools
- **.env**: Environment variables (OpenAI API key, Ollama endpoint)
- **data/settings/app_settings.json**: Runtime application settings

### Freqtrade Configuration
- **user_data/config.json**: Main Freqtrade configuration
- **user_data/strategies/**: Strategy Python files
- **user_data/data/**: Market data cache

## API Endpoints

### Backtest Workflow
- `GET/POST /api/backtest/run`: Execute backtest
- `GET /api/backtest/history`: Backtest history
- `GET /api/backtest/compare`: Compare two backtests
- `GET /api/backtest/results/{run_id}`: Get backtest results

### AI Chat
- `POST /api/ai/chat/message`: Send chat message
- `GET /api/ai/chat/threads/{strategy_name}`: Get chat history
- `WebSocket /api/ai/chat/stream`: Streaming responses

### Strategy Evolution
- `POST /api/ai/evolution/candidate`: Create candidate
- `POST /api/ai/evolution/apply`: Apply recommendation
- `GET /api/ai/evolution/diagnosis`: Get diagnosis

### Version Management
- `GET /api/versions/{strategy_name}`: List versions
- `POST /api/versions/{strategy_name}/promote`: Promote version
- `POST /api/versions/{strategy_name}/rollback`: Rollback version

### Settings
- `GET /api/settings`: Get all settings
- `POST /api/settings`: Update settings
- `GET /api/settings/validate`: Validate configuration

## Data Storage

### File-Based Storage
- **JSON**: Configuration, settings, metadata
- **ZIP**: Backtest result archives
- **Python**: Strategy files

### Directory Structure
- `data/`: Runtime application data
- `user_data/`: Freqtrade-specific data
- `data/versions/`: Strategy version snapshots
- `data/backtest_runs/`: Isolated execution workspaces

## Environment Variables

```
OPENAI_API_KEY=<api_key>           # OpenAI API authentication
OLLAMA_ENDPOINT=http://localhost:11434  # Ollama server URL
FREQTRADE_PATH=/path/to/freqtrade  # Freqtrade installation
```

## Performance Considerations

- **Async I/O**: FastAPI and aiofiles for non-blocking operations
- **Isolated Workspaces**: Each backtest run in separate directory to prevent conflicts
- **Streaming Responses**: AI chat uses WebSocket for real-time streaming
- **Lazy Loading**: Frontend loads page-specific JavaScript on demand
- **Hot Reload Exclusions**: Prevents unnecessary restarts from workflow file writes
