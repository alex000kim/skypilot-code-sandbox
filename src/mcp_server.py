import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP("Remote Code Execution")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8080")

def get_auth_headers() -> Dict[str, str]:
    """Get authentication headers if token is available."""
    token = os.getenv("AUTH_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}

def clean_libraries(libraries: Any) -> List[str]:
    """Convert libraries input to a clean list of strings."""
    if not libraries:
        return []
    
    if isinstance(libraries, str):
        try:
            parsed = json.loads(libraries)
            if isinstance(parsed, list):
                libraries = parsed
            else:
                libraries = [libraries]
        except json.JSONDecodeError:
            libraries = [lib.strip() for lib in libraries.split(',')]
    
    if isinstance(libraries, list):
        return [str(lib).strip() for lib in libraries if lib and str(lib).strip()]
    else:
        return [str(libraries).strip()] if libraries else []

async def make_api_request(method: str, endpoint: str, data: Optional[Dict] = None, timeout: int = 120) -> Dict[str, Any]:
    """Make an HTTP request to the FastAPI backend."""
    headers = get_auth_headers()
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if method == "GET":
                response = await client.get(f"{API_BASE_URL}{endpoint}", headers=headers)
            elif method == "POST":
                clean_data = {k: v for k, v in (data or {}).items() if v is not None}
                response = await client.post(f"{API_BASE_URL}{endpoint}", json=clean_data, headers=headers)
            elif method == "DELETE":
                response = await client.delete(f"{API_BASE_URL}{endpoint}", headers=headers)
            else:
                return {"error": f"Unsupported HTTP method: {method}"}
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

@mcp.tool()
async def execute_code(
    code: str,
    language: str = "python",
    libraries: Any = None,
    timeout: Optional[int] = 30,
    session_id: Optional[str] = None
) -> str:
    """
    Execute code in a sandboxed environment.
    
    IMPORTANT: To install Python packages, use the 'libraries' parameter instead of 
    running 'pip install' commands in your code. This is more reliable and efficient.
    
    IMPORTANT: Always reuse the same session_id if it exists for consecutive code executions
    unless you need to change the language or libraries. This maintains state 
    between executions (variables, imports, etc.) and improves performance.
    
    Args:
        code: The code to execute (DO NOT include pip install commands)
        language: Programming language (python, javascript, java, cpp, go, r)
        libraries: List of libraries to install (e.g., ["numpy", "pandas"])
                  Use this instead of subprocess.run(['pip', 'install', ...]) or !pip install
        timeout: Execution timeout in seconds
        session_id: Session ID for session persistence (reuse the same ID
                   unless language or libraries change)
    
    Returns:
        JSON string with execution results
    """
    if not code.strip():
        return json.dumps({"error": "Code cannot be empty"}, indent=2)
    
    libraries_list = clean_libraries(libraries)
    
    request_data = {
        "code": code,
        "language": language,
        "timeout": timeout or 30,
        "session_id": session_id
    }
    
    if libraries_list:
        request_data["libraries"] = libraries_list
    
    result = await make_api_request("POST", "/execute", request_data)
    return json.dumps(result, indent=2)

@mcp.tool()
async def create_session(
    language: str = "python",
    libraries: Any = None
) -> str:
    """
    Create a new execution session.
    
    Args:
        language: Programming language for the session
        libraries: List of libraries to pre-install
    
    Returns:
        JSON string with session information
    """
    libraries_list = clean_libraries(libraries)
    
    if libraries_list:
        params = f"language={language}&" + "&".join(f"libraries={lib}" for lib in libraries_list)
        endpoint = f"/session/create?{params}"
    else:
        endpoint = f"/session/create?language={language}"
    
    result = await make_api_request("POST", endpoint)
    return json.dumps(result, indent=2)

@mcp.tool()
async def close_session(session_id: str) -> str:
    """
    Close an execution session.
    
    Args:
        session_id: The session ID to close
    
    Returns:
        JSON string with closure confirmation
    """
    if not session_id or not session_id.strip():
        return json.dumps({"error": "Session ID cannot be empty"}, indent=2)
    
    result = await make_api_request("DELETE", f"/session/{session_id.strip()}")
    return json.dumps(result, indent=2)

@mcp.tool()
async def get_supported_languages() -> str:
    """
    Get the list of supported programming languages.
    
    Returns:
        JSON string with supported languages
    """
    result = await make_api_request("GET", "/languages")
    return json.dumps(result, indent=2)

@mcp.tool()
async def get_health_status() -> str:
    """
    Check the health status of the code execution service.
    
    Returns:
        JSON string with health status
    """
    result = await make_api_request("GET", "/health")
    return json.dumps(result, indent=2)

@mcp.tool()
async def get_pool_stats() -> str:
    """
    Get session pool statistics.
    
    Returns:
        JSON string with pool statistics
    """
    result = await make_api_request("GET", "/pool/stats")
    return json.dumps(result, indent=2)

def main():
    """Main entry point for the MCP server."""
    mcp.run()

if __name__ == "__main__":
    main()