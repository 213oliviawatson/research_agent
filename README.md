# Research Agent

A FastAPI backend and Dash web UI for researching questions with Claude and
public web evidence from Tavily. Responses are returned in separate Summary,
Technical / Audit, and Data Focus tabs, with an optional PDF report.

## Run with Docker

### 1. Install Docker

Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
or [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/).
On Windows, enable the WSL 2 backend during installation if prompted. Start
Docker Desktop and wait until it reports that Docker is running.

Verify the installation in a new terminal:

```powershell
docker --version
docker info
```

### 2. Configure environment variables

From the repository root, create `.env` from the example and add your API
keys. Do not commit `.env` to source control.

PowerShell:

```powershell
Copy-Item .env.example .env
```

Command Prompt:

```bat
copy .env.example .env
```

Generate the required API keys from the provider dashboards, configuring any rate or token limits as necessary:

- Create an [Anthropic API key](https://console.anthropic.com/settings/keys)
  for Claude. In `.env`, set `ANTHROPIC_API_KEY` to this value.
- Create a [Tavily API key](https://app.tavily.com/home) for public web search. In `.env`, set `TAVILY_API_KEY` to this value.

At minimum, configure both `ANTHROPIC_API_KEY` and `TAVILY_API_KEY` in `.env`.
Keep these values private and never commit `.env` to the repository.

### 3. Build and run

```powershell
docker build -t research-agent .
docker run --rm --name research-agent --env-file .env -p 8000:8000 -p 8050:8050 research-agent
```

Open the UI at **http://localhost:8050**.

The FastAPI documentation is available at **http://localhost:8000/docs**.

Stop the running container with `Ctrl+C`. If it was started in the background,
use:

```powershell
docker stop research-agent
```

The Docker image runs both the FastAPI backend on port `8000` and Dash UI on
port `8050`.

### Runtime and security notes

The included Docker setup is intended to make the application reproducible
for local development, demonstrations, and trusted internal use. It is not a
complete internet-facing service:

- The container runs the API and UI as two processes in one container.
- The UI currently starts with Dash debug mode disabled, it can be enabled by modifyed the app.run() call in app/ui.py.
- The API has no built-in authentication, rate limiting, or user management.
- Do not publish port `8000` publicly unless direct API access is required.
- Keep `.env` outside the image and use a secret manager in hosted production.

These limitations matter if the application is later adapted for public use.
In that case, use a process supervisor or separate containers for the API and
UI,  add authentication and rate limiting, and add health checks, centralized
logs, monitoring, backups, and resource limits.

To run the included container in the background for local or internal use:

```powershell
docker run -d --name research-agent --restart unless-stopped --env-file .env -p 8000:8000 -p 8050:8050 research-agent
```

View logs with `docker logs -f research-agent` and stop it with
`docker stop research-agent`.

## Local development

### Requirements

- Python 3.10 or newer
- An Anthropic API key
- A Tavily API key for public web search

Create and activate a virtual environment:

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your API keys.

Start the backend in one terminal:

```bash
uvicorn app.main:app --reload
```

Start the Dash UI in a second terminal:

```bash
python -m app.ui
```

Open http://localhost:8050.

## API

Send a research request to the backend:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What public evidence exists for candidate A?"}'
```

The interactive API documentation is at http://localhost:8000/docs.

### Request flow

For each `POST /chat` request:

1. FastAPI validates the request shape and the application policy checks the
  message.
2. The agent sends the question and reference context to Claude.
3. Claude can request the explicitly registered Tavily public-web search tool.
4. Tool arguments and the final response are validated, with bounded agent
  iterations and search calls.
5. The response parser separates `summary`, `audit`, and `data_focus` fields.
6. The API generates a base64-encoded PDF artifact, when report generation
  succeeds, and returns it in the `download` field.

The Dash callback calls the backend server-side, renders the three response
fields in separate tabs, and exposes the returned PDF as a download link.

## Configuration

Environment variables are documented in `.env.example`:

- `ANTHROPIC_API_KEY`: API key for Claude.
- `ANTHROPIC_MODEL`: Claude model name; defaults to `claude-sonnet-5`.
- `TAVILY_API_KEY`: API key for public web search.
- `TAVILY_SEARCH_DEPTH`: Tavily search depth; defaults to `basic`.
- `TAVILY_MAX_RESULTS`: Maximum Tavily results; defaults to `5`.
- `USE_MOCK_ANTHROPIC`: Set to `true` for local tests without an Anthropic key.
- `BACKEND_URL`: Backend URL used by Dash; defaults to `http://localhost:8000`.
- `BACKEND_TIMEOUT`: Dash request timeout in seconds; defaults to `120`.

## Architecture

1. FastAPI receives a user question.
2. The policy layer checks the request.
3. The agent sends the request to Claude.
4. Claude may request a Tavily public-web search.
5. Tool and output validation checks the request and response.
6. FastAPI returns separate summary, audit, data, and PDF fields.
7. Dash renders the fields in separate tabs.

For the detailed component design, request lifecycle, instruction hierarchy,
restrictions, and architecture diagram, see [DESIGN.md](DESIGN.md).

## Where to customize

### Hard constraints

Edit `app/policy.py`. The policy layer is deliberately separate from the LLM
prompt.

### Tool access

Edit `app/tools.py`. Only tools registered in `TOOLS` and explicitly permitted
by `check_tool_permission()` can execute.

The `search_public_web` tool uses Tavily and returns normalized public-source
results for Claude to evaluate. Configure `TAVILY_API_KEY` before relying on
research results.

### Input validation

Edit `check_user_request()` in `app/policy.py`.

### Tool validation

Edit `validate_tool_arguments()` in `app/validation.py`.

### Output validation

Edit `validate_final_response()` in `app/validation.py`.

### Agent behavior

Edit `SYSTEM_PROMPT` in `app/agent.py`. The system prompt controls agent
behavior, but it should not be relied upon for hard security or authorization
constraints.
