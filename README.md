# open-webui-tools
Custom tools and skills for [Open WebUI](https://openwebui.com/).

## Structure
- `tools/`: Open WebUI tools.
- `skills/`: Open WebUI skills.
- `tests/`: Tests for the tools.

## Usage
Import files from `tools/` into Open WebUI (**Workspace → Tools**) and configure their Valves.

## Local Development
Create a `.env` file in the project root for running tests (`EXA_API_KEY`, plus an OpenAI-compatible `OPENAI_API_KEY` and `OPENAI_API_BASE_URL`):
```powershell
uv sync                                  # Install dependencies (Python >=3.11)
uv run python tests/tools/<test_file>.py # Run a test script
```

Start a local Open WebUI instance for testing (optional):
```powershell
.\dev.ps1
```
