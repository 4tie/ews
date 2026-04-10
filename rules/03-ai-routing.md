# AI Routing Rule

This project uses a hybrid AI model strategy.

Policy:
- Use local Ollama models for easy or non-deep tasks.
- Use OpenRouter free-only models for deeper reasoning tasks.
- Support multiple OpenRouter API keys.
- Fall back to another key on recoverable failures.
- Fall back to another free model when needed.
- Validate outputs before accepting them as success.

Light/local tasks include:
- short summaries
- labels
- helper text
- light classification
- small structured JSON extraction
- simple result explanation

Deep/cloud tasks include:
- strategy diagnosis
- compare-runs reasoning
- candidate code mutation proposals
- evolution generation
- multi-step structured reasoning over larger context

Hard rules:
- never use paid cloud models when free-only mode is enabled
- never let provider choice leak into UI business logic
- never hardcode one model path as the only valid path
- never treat malformed JSON or invalid patches as success

Preferred behavior:
1. classify task
2. route to Ollama if light and available
3. otherwise use OpenRouter free-only
4. on recoverable failure, try another key
5. then try another free model
6. if task allows degradation, fall back to Ollama
7. otherwise return a clear failure