# SkyPilot Code Sandbox

A self-hosted, secure code execution sandbox for LLM agents deployed on your cloud infrastructure using [SkyPilot](https://skypilot.readthedocs.io/). Built on [llm-sandbox](https://vndee.github.io/llm-sandbox/languages/) for multi-language code execution.

## Key Features

- **Team Collaboration**: Mount S3 buckets in read-only mode for shared data access across team members
- **Secure & Scalable**: Token-based auth, Docker sandboxing, auto-scaling
- **Multi-language**: Python, JavaScript, Java, C++, etc with dynamic package installation
- **Universal MCP Integration**: Works with [Claude Desktop](https://claude.ai/download), [VS Code](https://code.visualstudio.com/docs/copilot/chat/mcp-servers), and other [MCP clients](https://modelcontextprotocol.io/clients)
- **Cloud Native**: Deploy on any cloud (AWS, GCP, Azure, etc.) with built-in load balancing and cost optimization

## Requirements

- [SkyPilot](https://skypilot.readthedocs.io/) for deployment
- Valid cloud credentials
- Docker for local development

## Quick Start

### 1. Deploy the Service
```bash
export AUTH_TOKEN=<YOUR_AUTH_TOKEN>
sky serve up -n code-executor src/code-execution-service.yaml --env AUTH_TOKEN --secret AUTH_TOKEN AUTH_TOKEN
```

### 2. Get the API Endpoint
```bash
sky serve status code-executor-service --endpoint
```

### 3. Configure Your MCP Client

Using Claude Desktop as an example:

- macOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "code-execution-server": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/alex000kim/skypilot-code-sandbox.git",
        "mcp-server"
      ],
      "env": {
        "API_BASE_URL": "<YOUR_ENDPOINT>",
        "AUTH_TOKEN": "<YOUR_AUTH_TOKEN>"
      }
    }
  }
}
```

**VS Code**: Add the same configuration to `.vscode/mcp.json` (rename `mcpServers` to `servers`).

## Team Deployment Benefits

The **S3 read-only mount** feature enables seamless team collaboration:
- **Shared datasets**: All team members access the same data without duplication
- **Security**: Read-only access prevents accidental data modification
- **Cost efficient**: Single data storage, multiple execution environments

Great for collaborative research projects.


## Local Development

```bash
pip install -e .
python -m uvicorn src.api:app --host 0.0.0.0 --workers 4 --port 8080
```

Update MCP config to use `"API_BASE_URL": "http://localhost:8080"` for local testing.




