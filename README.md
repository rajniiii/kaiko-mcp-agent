**Kaiko MCP Agent**

**Summary**: Kaiko Reference Data MCP server and example MCP client. The server exposes Kaiko basic-tier reference endpoints as FastMCP tools (exchanges, instruments, assets). The agent/demo client demonstrates calling those tools via a FastMCP Client.

**Quick Workflow**:
- Start the MCP server: `python rshenkar_server.py`. The server imports `fastmcp` and registers tools such as `get_exchanges`, `get_instruments`, and `get_assets`. FastMCP wraps Kaiko HTTP endpoints and returns JSON strings for each tool.
- Run the agent client: `python rshenkar_agent.py`. The client uses `fastmcp.Client` to list available tools and adapts them into an LLM-friendly toolset. When the LLM requests reference data (for example, "what exchanges does Kaiko cover?"), the agent calls the appropriate MCP tool and returns the tool output to the LLM.
- Example flow: Agent receives question → prefers MCP tools for Kaiko data → calls `get_exchanges` or `get_instruments` → formats and returns JSON/text answer to the user.

**Notes & Requirements**:
- `fastmcp` is required (see `rshenkar_requirments.txt`).
- Provide `KAIKO_API_KEY` via your environment (or an untracked `.env` file) for endpoints that require a key. This repo excludes `.env` from commits to avoid leaking secrets.
- Files and caches such as `.env`, `*.sqlite3`, and large outputs are ignored via `.gitignore`.

**Commands**:
```
python rshenkar_server.py
python rshenkar_agent.py
```

**Contacts**: refer to the source files `rshenkar_server.py` and `rshenkar_agent.py` for implementation details and available MCP tool names.
