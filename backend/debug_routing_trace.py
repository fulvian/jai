#!/usr/bin/env python3
"""Debug script to capture routing execution trace for betting query."""

import asyncio
import sys
import json
import logging
from pathlib import Path

# Setup logging to capture all routing events
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/tmp/routing_trace.log", mode="w"),
    ],
)

# Configure structlog to be extra verbose for this debug session
import structlog

structlog.configure(
    processors=[structlog.processors.JSONRenderer()],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
)

logger = logging.getLogger(__name__)


async def debug_routing():
    """Execute a single betting query and capture routing trace."""

    # Import after logging setup
    from me4brain.engine.hybrid_router.router import HybridToolRouter
    from me4brain.engine.hybrid_router.types import HybridRouterConfig
    from me4brain.llm.nanogpt import get_llm_client
    from me4brain.domains.sports_nba.tools import get_tool_definitions, get_executors
    from me4brain.domains.web_search.tools import get_tool_definitions as get_web_search_tools

    query = "Analizza le partite NBA stasera, identifica i migliori pronostici ed elabora un sistema di scommesse vincente"

    print("\n" + "=" * 80)
    print("ROUTING DEBUG SESSION - NBA BETTING QUERY")
    print("=" * 80)
    print(f"Query: {query}")
    print("=" * 80 + "\n")

    try:
        # Initialize LLM
        print("[1/5] Initializing LLM client...")
        llm_client = get_llm_client()
        print("✓ LLM client initialized\n")

        # Get tools
        print("[2/5] Loading tool definitions...")
        nba_tools = get_tool_definitions()
        web_search_tools = get_web_search_tools()

        # Convert ToolDefinition objects to OpenAI-compatible dicts
        all_tools_dicts = []
        for tool in nba_tools + web_search_tools:
            if hasattr(tool, "to_dict"):
                all_tools_dicts.append(tool.to_dict())
            else:
                # Fallback: create minimal dict
                all_tools_dicts.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": {},
                        },
                    }
                )

        print(f"✓ Loaded {len(nba_tools)} NBA tools + {len(web_search_tools)} web_search tools")
        print(f"✓ Converted to {len(all_tools_dicts)} OpenAI-compatible tool dicts\n")

        # Get executors
        print("[3/5] Loading tool executors...")
        nba_executors = get_executors()
        print(f"✓ Loaded {len(nba_executors)} NBA tool executors\n")

        # Build tool domains mapping from ToolDefinition objects
        tool_domains = {}
        for tool in nba_tools:
            tool_domains[tool.name] = "sports_nba"
        for tool in web_search_tools:
            tool_domains[tool.name] = "web_search"

        print(f"[4/5] Tool domains mapped: {len(tool_domains)} tools")
        print(f"  - sports_nba: {len([d for d in tool_domains.values() if d == 'sports_nba'])}")
        print(f"  - web_search: {len([d for d in tool_domains.values() if d == 'web_search'])}\n")

        # Initialize router
        print("[5/5] Initializing HybridToolRouter...")
        config = HybridRouterConfig(
            use_query_decomposition=True,
            router_model="qwen3.5-9b-mlx",
            use_llamaindex_retriever=False,  # Disable LlamaIndex, use in-memory retriever
        )

        router = HybridToolRouter(llm_client=llm_client, config=config)

        # Create embedding function (dummy for now)
        async def dummy_embed(text: str) -> list[float]:
            """Dummy embedding function."""
            import hashlib

            # Generate deterministic embedding based on text hash
            h = hashlib.md5(text.encode()).hexdigest()
            return [float(ord(c)) / 255.0 for c in h[:100]]

        await router.initialize(
            tool_schemas=all_tools_dicts,
            tool_domains=tool_domains,
            embed_fn=dummy_embed,
            llm_client=llm_client,
        )
        print("✓ HybridToolRouter initialized\n")

        # Execute routing
        print("=" * 80)
        print("EXECUTING ROUTING PIPELINE")
        print("=" * 80 + "\n")

        import time

        start_time = time.time()

        try:
            tool_tasks = await asyncio.wait_for(
                router.route(
                    query=query,
                    context=None,
                    max_tools=100,
                ),
                timeout=90.0,  # 90 second timeout for full routing
            )

            elapsed = time.time() - start_time

            print("\n" + "=" * 80)
            print("ROUTING COMPLETE")
            print("=" * 80)
            print(f"Time elapsed: {elapsed:.2f}s")
            print(f"Tools selected: {len(tool_tasks)}")

            if tool_tasks:
                print("\nSelected tools:")
                for task in tool_tasks:
                    print(f"  - {task.tool_name}")
            else:
                print("❌ NO TOOLS SELECTED!")

            # Write trace to file for analysis
            trace = {
                "query": query,
                "elapsed_ms": int(elapsed * 1000),
                "tools_selected": len(tool_tasks),
                "tool_names": [t.tool_name for t in tool_tasks],
                "status": "success" if tool_tasks else "no_tools_selected",
            }

            with open("/tmp/routing_trace_result.json", "w") as f:
                json.dump(trace, f, indent=2)

            print("\n✓ Trace written to /tmp/routing_trace_result.json")
            print("✓ Full logs written to /tmp/routing_trace.log")

        except asyncio.TimeoutError:
            print("\n❌ TIMEOUT: Routing execution exceeded 90 seconds")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ ROUTING ERROR: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ INITIALIZATION ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(debug_routing())
