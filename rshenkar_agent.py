"""
FE524 HW12 – Kaiko Reference Data Agent

Usage:
    export OPENAI_API_KEY="your-openai-key"

No Kaiko API key needed – the basic-tier reference endpoints are public.

At the prompt type a question or type "demo" to run the built-in examples.
Type "quit" to exit.
"""

import asyncio
import json
import os
import sys

from openai import OpenAI
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = "gpt-4o-mini"

# Path to the MCP server (must be in the same directory as this script)
SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "rshenkar_server.py")

SYSTEM_PROMPT = """You are a data-availability assistant embedded in a crypto trading firm.
You have access to Kaiko reference data tools that tell you which exchanges, instruments
(trading pairs), and assets are available in Kaiko's database.

Rules:
1. Always call a tool to look up real data — never guess codes or timestamps.
2. When asked about a specific asset or exchange, pass filters to get_instruments
   rather than fetching everything unfiltered.
3. If you need an exchange code (e.g. for Coinbase), call get_exchanges first.
4. trade_end_timestamp = null means the instrument is still actively trading.
5. Summarize results concisely — do not dump raw JSON back to the user.
"""


def _mcp_tools_to_openai(mcp_tools: list) -> list[dict]:
    """
    FastMCP 2.x Tool objects have .name, .description, and .parameters
    (a JSON Schema dict).  Convert them to the format OpenAI expects.
    """
    result = []
    for tool in mcp_tools:
        # .parameters holds the JSON Schema for the tool's input
        params_schema = tool.parameters if hasattr(tool, "parameters") else {}
        if not params_schema:
            params_schema = {"type": "object", "properties": {}}
        result.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": params_schema,
            },
        })
    return result


# ---------------------------------------------------------------------------
# Agent loop (one question at a time)
# ---------------------------------------------------------------------------

async def run_agent(question: str, mcp_client: Client, openai_client: OpenAI) -> str:
    """
    OpenAI function-calling agent loop:
      1. Ask the model with the available tools.
      2. If it wants to call a tool, run it via MCP and feed the result back.
      3. Repeat until the model produces a plain-text answer (no tool call).
    """
    mcp_tools = await mcp_client.list_tools()
    openai_tools = _mcp_tools_to_openai(mcp_tools)

    # Build conversation as plain dicts (required for multi-turn history)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": question},
    ]

    MAX_ROUNDS = 6  # safety limit on tool-call rounds

    for _ in range(MAX_ROUNDS):
        response = openai_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # No tool call → final answer ready
        if not msg.tool_calls:
            return msg.content or "(empty response)"

        # Add the assistant turn as a plain dict
        messages.append({
            "role": "assistant",
            "content": msg.content,           # may be None
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        # Execute each tool call via MCP and append results
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments or "{}")

            print(f"  [tool call] {fn_name}({fn_args})", flush=True)

            try:
                call_result = await mcp_client.call_tool(fn_name, fn_args)
                # CallToolResult.content is a list of TextContent / other objects
                content_list = call_result.content if hasattr(call_result, "content") else []
                if content_list and hasattr(content_list[0], "text"):
                    result_text = content_list[0].text
                else:
                    result_text = json.dumps(str(call_result))
            except Exception as exc:
                result_text = f"Tool error: {exc}"

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_text,
            })

    return "Reached maximum tool-call rounds without a final answer."


# ---------------------------------------------------------------------------
# Demo questions
# ---------------------------------------------------------------------------

DEMO_QUESTIONS = [
    "When was Synapse (SYN) last traded on Coinbase?",
    "What major derivatives exchanges are available on Kaiko?",
    "Is ETH/USDT available on Binance? When did it start trading?",
    "What spot instruments does Kraken offer for BTC?",
    "Does Kaiko have data for USDC pairs on any exchange?",
]

# ---------------------------------------------------------------------------
# Main REPL
# ---------------------------------------------------------------------------

async def main():
    if not OPENAI_API_KEY:
        sys.exit("ERROR: Set OPENAI_API_KEY in your environment before running.")

    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    # Launch the MCP server as a Python subprocess over stdio
    transport = PythonStdioTransport(SERVER_SCRIPT)

    async with Client(transport) as mcp_client:
        print("=" * 60)
        print("  Kaiko Reference Data Agent  –  FE524 HW12")
        print("  Commands: ask anything, 'demo', or 'quit'")
        print("=" * 60)

        while True:
            try:
                user_input = input("\nQuestion > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break

            if not user_input:
                continue
            if user_input.lower() in {"quit", "exit", "q"}:
                print("Goodbye.")
                break
            if user_input.lower() == "demo":
                for i, q in enumerate(DEMO_QUESTIONS, 1):
                    print(f"\n{'─' * 60}")
                    print(f"Demo {i}: {q}")
                    answer = await run_agent(q, mcp_client, openai_client)
                    print(f"\nAnswer: {answer}")
                continue

            answer = await run_agent(user_input, mcp_client, openai_client)
            print(f"\nAnswer: {answer}")


if __name__ == "__main__":
    asyncio.run(main())