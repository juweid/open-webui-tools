import asyncio
import json
import sys
import os
from pathlib import Path
from fastapi import Request
from unittest.mock import AsyncMock, MagicMock, patch
from dotenv import load_dotenv
import openai

# Load environment variables from a .env file
load_dotenv()

# Disable Open WebUI auth for testing outside the server environment
os.environ["WEBUI_AUTH"] = "False"

# Ensure project root is in sys.path when running as a script directly
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tools.job_search_tool import Tools

def openai_generate(messages : list[dict[str, str]], model: str = "gpt-6-luna"):
    """Simulate a realistic OpenAI API response structure."""
    client = openai.OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE_URL")
    )
    response = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    return response.to_dict()

def mock_generate_chat_completion(request, body, user):
    """Simulate a realistic OpenAI API response structure."""
    return openai_generate(body["messages"], model=body.get("model", "gpt-6-luna"))

@patch("tools.job_search_tool.Users.get_user_by_id", new_callable=AsyncMock)
@patch("tools.job_search_tool.generate_chat_completion", new_callable=AsyncMock)
async def run_example(mock_generate, mock_get_user):
    """Run a simple example usage and print simulated OpenWebUI behaviour."""
    
    # Simulate OpenWebUI's __event_emitter__ behavior
    mock_emitter = AsyncMock()
    mock_model = {"id": "gpt-6-luna", "name": "Task Model"}
    mock_user = {"id": "user-demo-456", "name": "Demo User", "role": "admin"}
    mock_request = MagicMock(spec=Request)
    
    mock_user_obj = MagicMock()
    mock_user_obj.id = mock_user["id"]
    
    mock_get_user.return_value = mock_user_obj
    mock_generate.side_effect = mock_generate_chat_completion
    
    # create an instance of the Tools class
    
    tool = Tools()
    
    # Set valves 
    tool.valves.nominatim_user_agent = "job_search_tool_test"
    tool.valves.dataset_min_population = 15000
    tool.valves.exa_api_key = os.getenv("EXA_API_KEY")
    
    # -----------------------------------------------
    # Test get_cities_nearby from job_search_tool.py
    # -----------------------------------------------

    mock_emitter.reset_mock()  # Reset the mock for the next test

    print("Running get_cities_nearby outside OpenWebUI...\n")
    result = await tool.get_cities_nearby(
        target_city="Munich, Germany",
        radius_km=30,
        count=5,
        min_population=25000,
        __event_emitter__=mock_emitter,
    )

    print("--- Captured OpenWebUI Status Events ---")
    for call in mock_emitter.await_args_list:
        event = call.args[0]
        desc = event.get("data", {}).get("description")
        done = event.get("data", {}).get("done")
        print(f"[{event.get('type')}] {desc} (done={done})")

    print("\n--- Result ---")
    cities = json.loads(result)
    print(json.dumps(cities, indent=2, ensure_ascii=False))
    
    # -----------------------------------------------
    # Test search_jobs from job_search_tool.py
    # -----------------------------------------------
    
    mock_emitter.reset_mock()  # Reset the mock for the next test
    
    print("\nRunning search_jobs outside OpenWebUI...\n")
    result = await tool.search_jobs(
        query="Python software engineer in Frankfurt, Germany",
        __event_emitter__=mock_emitter,
        __model__=mock_model,
        __request__=mock_request,
        __user__=mock_user
    )
    
    print("--- Captured OpenWebUI Status Events ---")
    for call in mock_emitter.await_args_list:
        event = call.args[0]
        desc = event.get("data", {}).get("description")
        done = event.get("data", {}).get("done")
        print(f"[{event.get('type')}] {desc} (done={done})")

    print("\n--- Result ---")
    jobs = json.loads(result)
    print(json.dumps(jobs, indent=2, ensure_ascii=False))

def main():
    asyncio.run(run_example())


if __name__ == "__main__":
    main()