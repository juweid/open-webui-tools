import asyncio
import json
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from dotenv import load_dotenv

import tiktoken 

# Load environment variables from a .env file
load_dotenv()

# Disable Open WebUI auth for testing outside the server environment
os.environ["WEBUI_AUTH"] = "False"

# Ensure project root is in sys.path when running as a script directly
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tools.exa_search_tool import Tools


@patch("tools.exa_search_tool.Users.get_user_by_id", new_callable=AsyncMock)
async def run_example(mock_get_user):
    """Run a simple example usage and print simulated OpenWebUI behaviour."""
    
    # Simulate OpenWebUI's __event_emitter__ behavior
    mock_emitter = AsyncMock()
    mock_user = {"id": "user-demo-456", "name": "Demo User", "role": "admin"}
    
    mock_user_obj = MagicMock()
    mock_user_obj.id = mock_user["id"]
    
    mock_get_user.return_value = mock_user_obj

    # create an instance of the Tools class
    
    tool = Tools()
    
    # Set valves 
    tool.valves.exa_api_key = os.getenv("EXA_API_KEY")
        
    # -----------------------------------------------
    # Test exa_search from exa_search_tool.py
    # -----------------------------------------------
    tokenizer = tiktoken.get_encoding("cl100k_base")
    
    mock_emitter.reset_mock()  # Reset the mock for the next test
    
    print("\nRunning exa_search outside OpenWebUI...\n")
    result = await tool.exa_search(
        query="Modal serverless cloud GPU pricing and subscription plan tiers",
        objective=(
            "Retrieve the official Modal pricing breakdown. Rank modal.com/pricing first. "
            "Extract the exact per-second and per-hour rates for B200 and H200 GPUs, "
            "plus the monthly cost, free credit allowance, and concurrency limits for the Team plan."
        ),
        include_domains=["modal.com"],
        live_fetch=True,
        __event_emitter__=mock_emitter,
        __user__=mock_user
    )
    
    print("--- Captured OpenWebUI Status Events ---")
    for call in mock_emitter.await_args_list:
        event = call.args[0]
        desc = event.get("data", {}).get("description")
        done = event.get("data", {}).get("done")
        print(f"[{event.get('type')}] {desc} (done={done})")

    print("\n--- Result ---")
    print(json.dumps(json.loads(result), indent=2, ensure_ascii=False))
    print("Token count:", len(tokenizer.encode(result)))
    print()

def main():
    asyncio.run(run_example())


if __name__ == "__main__":
    main()