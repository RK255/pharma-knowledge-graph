"""
LLM-powered natural language query interface for the Pharmaceutical Knowledge Graph.
Uses Venice.ai API (OpenAI-compatible).
"""
import os
import json
import httpx
import re
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

# Venice.ai Configuration
VENICE_API_KEY = os.getenv("VENICE_API_KEY", "VENICE-INFERENCE-KEY-REDACTED")
VENICE_BASE_URL = "https://api.venice.ai/api/v1"
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b")

@dataclass
class ToolDefinition:
    """Definition of a tool the LLM can call."""
    name: str
    description: str
    parameters: Dict
    endpoint: str

# Define available tools
TOOLS = [
    ToolDefinition(
        name="search_drugs",
        description="Search for drugs by name. Use when user asks about a specific drug or searches by drug name.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Drug name or partial name to search for"}
            },
            "required": ["query"]
        },
        endpoint="/api/search"
    ),
    ToolDefinition(
        name="get_drug_details",
        description="Get detailed information about a specific drug including sections, manufacturer, and identifiers.",
        parameters={
            "type": "object",
            "properties": {
                "drug_id": {"type": "string", "description": "The unique drug ID"}
            },
            "required": ["drug_id"]
        },
        endpoint="/drug/{drug_id}"
    ),
    ToolDefinition(
        name="get_drug_ingredients",
        description="Get the active ingredients for a drug.",
        parameters={
            "type": "object",
            "properties": {
                "drug_id": {"type": "string", "description": "The unique drug ID"}
            },
            "required": ["drug_id"]
        },
        endpoint="/api/drug/{drug_id}/ingredients"
    ),
    ToolDefinition(
        name="get_related_drugs",
        description="Find alternative drugs by pharmacological class. Results include 'clinical_priority': PRIMARY=same drug class (recommend first), SECONDARY=related class, TERTIARY=broad class. ALWAYS present PRIMARY alternatives first, then mention SECONDARY as 'other options', and TERTIARY only if patient has failed primary options.",
        parameters={
            "type": "object",
            "properties": {
                "drug_id": {"type": "string", "description": "The unique drug ID"}
            },
            "required": ["drug_id"]
        },
        endpoint="/api/drug/{drug_id}/related"
    ),
    ToolDefinition(
        name="get_drug_graph",
        description="Get the full RxNorm graph data for a drug.",
        parameters={
            "type": "object",
            "properties": {
                "drug_id": {"type": "string", "description": "The unique drug ID"}
            },
            "required": ["drug_id"]
        },
        endpoint="/api/drug/{drug_id}/graph"
    ),
    ToolDefinition(
        name="search_by_ingredient",
        description="Find all drugs that contain a specific ingredient. Use when asked 'what drugs contain X'.",
        parameters={
            "type": "object",
            "properties": {
                "ingredient": {"type": "string", "description": "The ingredient name (e.g., 'aspirin', 'metformin')"}
            },
            "required": ["ingredient"]
        },
        endpoint="/api/ingredient/{ingredient}/drugs"
    ),
    ToolDefinition(
        name="get_drug_suggestions",
        description="Get autocomplete suggestions for drug names.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Partial drug name"}
            },
            "required": ["query"]
        },
        endpoint="/api/search/suggestions"
    ),
    ToolDefinition(
        name="get_stats",
        description="Get statistics about the knowledge graph.",
        parameters={"type": "object", "properties": {}, "required": []},
        endpoint="/api/stats"
    ),
]

SYSTEM_PROMPT = """You are a pharmaceutical knowledge assistant with access to a comprehensive FDA drug database and RxNorm clinical terminology.

Your database contains:
- FDA drug labels (indications, warnings, dosage, interactions, etc.)
- RxNorm clinical drug terminology
- Drug ingredient relationships
- Manufacturer and NDC information
- Drug-to-drug relationships (shared ingredients)

CRITICAL RULES:
1. NEVER answer from training data when drug information is requested
2. ALWAYS use tools to get accurate, cited data from our FDA database
3. EVERY drug mentioned MUST have a real AMA citation from tool results
4. If you list drugs, you MUST call tools for EACH drug to get citations
5. NEVER fabricate citations - only use citations returned by tools

TOOL USAGE FOR DRUG CLASSES:
When asked about a drug class (beta blockers, statins, PPIs, etc.):
1. List the drugs you know are in that class
2. For EACH drug, call search_by_ingredient to get real products with citations
3. Present the data WITH the AMA citations from tool results

Example for beta blockers:
1. Call search_by_ingredient for metoprolol
2. Call search_by_ingredient for atenolol  
3. Call search_by_ingredient for propranolol
4. Present results with real citations

TOOL REFERENCE:
- drug_id is a hash like StqMW1puaaH3nTTwAebJzM, NOT a drug name
- search_drugs: Find drugs by name - returns drug_id and manufacturer
- get_drug_details: Get full info and AMA citation using drug_id
- search_by_ingredient: Find all products containing an ingredient

DRUG CLASSES:
- Beta blockers: metoprolol, atenolol, propranolol, carvedilol, bisoprolol, nebivolol
- Statins: atorvastatin, rosuvastatin, simvastatin, pravastatin
- PPIs: omeprazole, esomeprazole, pantoprazole, lansoprazole
- ACE inhibitors: lisinopril, enalapril, ramipril
- ARBs: losartan, valsartan, irbesartan

ALWAYS cite real FDA package inserts. Format: Drug Name [package insert]. Manufacturer; Year."""

def get_tool_definitions() -> List[Dict]:
    """Get tool definitions in OpenAI function calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
        }
        for tool in TOOLS
    ]

def get_tool_by_name(name: str) -> Optional[ToolDefinition]:
    """Find a tool by its name."""
    for tool in TOOLS:
        if tool.name == name:
            return tool
    return None

async def call_venice(messages: List[Dict], tools: List[Dict]) -> Dict:
    """Call Venice.ai API for chat completion with tool support."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        payload = {
            "model": LLM_MODEL,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.1,
        }
        
        response = await client.post(
            f"{VENICE_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {VENICE_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload
        )
        response.raise_for_status()
        return response.json()

def extract_tool_call(response: Dict) -> Optional[Dict]:
    """Extract tool call from LLM response - handles both OpenAI and Venice formats."""
    try:
        message = response.get("choices", [{}])[0].get("message", {})
        
        # Try OpenAI format first
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            tc = tool_calls[0]
            return {
                "name": tc["function"]["name"],
                "arguments": json.loads(tc["function"]["arguments"]),
                "id": tc.get("id", "call_1")
            }
        
        # Try Venice/text format: <function=name{json}</function>
        content = message.get("content", "")
        if "<function=" in content:
            match = re.search(r'<function=(\w+)(\{[^}]+\})</function>', content)
            if match:
                tool_name = match.group(1)
                args_json = match.group(2)
                return {
                    "name": tool_name,
                    "arguments": json.loads(args_json),
                    "id": "call_venice_1"
                }
    except Exception as e:
        print(f"Error extracting tool call: {e}")
    return None

def extract_text_response(response: Dict) -> Optional[str]:
    """Extract text response from LLM."""
    try:
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        # Remove function calls from text if present
        if "<function=" in content:
            content = re.sub(r'<function=\w+\{[^}]+\}</function>', '', content).strip()
        return content if content else None
    except:
        return None

async def execute_tool_call(tool_name: str, arguments: Dict, base_url: str = "http://localhost:8000") -> Dict:
    """Execute a tool call by making a request to the local API."""
    tool = get_tool_by_name(tool_name)
    if not tool:
        return {"error": f"Unknown tool: {tool_name}"}
    
    # Build the endpoint URL with arguments
    endpoint = tool.endpoint
    for key, value in arguments.items():
        endpoint = endpoint.replace(f"{{{key}}}", str(value))
    
    # Handle query parameters
    if tool_name == "search_drugs":
        endpoint = f"{endpoint}?q={arguments.get('query', '')}&limit=10"
    elif tool_name == "get_drug_suggestions":
        endpoint = f"{endpoint}?q={arguments.get('query', '')}"
    
    url = f"{base_url}{endpoint}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"API returned status {response.status_code}", "details": response.text}
    except Exception as e:
        return {"error": str(e)}

async def chat_query(user_message: str, conversation_history: List[Dict] = None) -> Dict:
    """
    Process a natural language query about drugs.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if conversation_history:
        messages.extend(conversation_history)
    
    messages.append({"role": "user", "content": user_message})
    
    tools = get_tool_definitions()
    tool_calls_made = []
    max_iterations = 15
    
    for iteration in range(max_iterations):
        try:
            response = await call_venice(messages, tools)
        except httpx.HTTPStatusError as e:
            return {
                "response": f"API Error: {e.response.status_code}",
                "tool_calls": tool_calls_made,
                "success": False
            }
        except Exception as e:
            return {
                "response": f"Error calling LLM: {str(e)}",
                "tool_calls": tool_calls_made,
                "success": False
            }
        
        tool_call = extract_tool_call(response)
        text_response = extract_text_response(response)
        
        if tool_call:
            # Execute the tool call
            tool_result = await execute_tool_call(tool_call["name"], tool_call["arguments"])
            tool_calls_made.append({
                "tool": tool_call["name"],
                "arguments": tool_call["arguments"],
                "result": tool_result
            })
            
            # Add assistant message
            message = response["choices"][0]["message"]
            messages.append(message)
            
            # Add tool result
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(tool_result)
            })
            
            continue
        
        elif text_response:
            return {
                "response": text_response,
                "tool_calls": tool_calls_made,
                "success": True
            }
        
        else:
            return {
                "response": "I couldn't process that request. Please try again.",
                "tool_calls": tool_calls_made,
                "success": False
            }
    
    return {
        "response": "I reached the maximum number of tool calls.",
        "tool_calls": tool_calls_made,
        "success": False
    }


async def test_connection():
    """Test the Venice API connection."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{VENICE_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {VENICE_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [{"role": "user", "content": "Say 'Hello'"}],
                    "max_tokens": 10
                }
            )
            if response.status_code == 200:
                return {"success": True, "message": "Venice API connection successful"}
            else:
                return {"success": False, "error": f"Status {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
