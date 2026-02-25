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

import re

def parse_text_tool_call(content: str) -> list:
    """Parse text-based tool calls like <function=name{args}</function>"""
    tool_calls = []
    
    # Find function calls in the format: <function=name{json}</function>
    func_match = re.search(r'function=(\w+)\{', content)
    if func_match:
        tool_name = func_match.group(1)
        
        # Extract the JSON part
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1:
            json_str = content[start:end+1]
            try:
                args = json.loads(json_str)
                tool_calls.append({
                    "id": f"call_{tool_name}",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(args)
                    }
                })
            except json.JSONDecodeError:
                pass
    
    return tool_calls

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
        description="Search for drugs by name. ALWAYS call this FIRST when user mentions a drug name. Returns drug_id needed for other tools.",
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
                "drug_id": {"type": "string", "description": "The unique drug ID from search_drugs"}
            },
            "required": ["drug_id"]
        },
        endpoint="/drug/{drug_id}"
    ),
    ToolDefinition(
        name="get_related_drugs",
        description="Find clinically-weighted alternative drugs by pharmacological class. Use when asked about alternatives, substitutes, or switching medications. Returns drugs with clinical_priority (PRIMARY=recommended first, SECONDARY=alternative if PRIMARY fails, CAUTION=limited use), clinical_weight (0-100), weight_rationale, weight_evidence, and weight_provenance (curator credentials).",
        parameters={
            "type": "object",
            "properties": {
                "drug_id": {"type": "string", "description": "The unique drug ID from search_drugs (NOT a drug name)"},
                "indication": {"type": "string", "description": "Optional indication for re-weighting: 'hyperlipidemia', 'cv_risk_reduction', 'hypertriglyceridemia', or 'statin_intolerance'. MUST use exact value with underscore, NOT space."}
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
                "drug_id": {"type": "string", "description": "The unique drug ID from search_drugs"}
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
        name="get_drug_ingredients",
        description="Get the active ingredients for a drug.",
        parameters={
            "type": "object",
            "properties": {
                "drug_id": {"type": "string", "description": "The unique drug ID from search_drugs"}
            },
            "required": ["drug_id"]
        },
        endpoint="/api/drug/{drug_id}/ingredients"
    ),
    ToolDefinition(
        name="get_drug_classes",
        description="Get all pharmacological classes a drug belongs to. Use to understand drug mechanism and find similar drugs by class. Returns classes grouped by ingredient.",
        parameters={
            "type": "object",
            "properties": {
                "drug_id": {"type": "string", "description": "The unique drug ID from search_drugs"}
            },
            "required": ["drug_id"]
        },
        endpoint="/api/drug/{drug_id}/classes"
    ),
    ToolDefinition(
        name="get_drugs_in_class",
        description="Find all drugs/ingredients that belong to a pharmacological class. Use when asked about drug classes, alternatives by mechanism, or drugs with similar effects. Class examples: 'Anti-Bacterial Agents', 'Antihypertensive Agents', 'Antineoplastic Agents'.",
        parameters={
            "type": "object",
            "properties": {
                "class_name": {"type": "string", "description": "Pharmacological class name (e.g., 'Anti-Bacterial Agents', 'Statins', 'ACE Inhibitors')"},
                "limit": {"type": "integer", "description": "Maximum results to return (default 50)"}
            },
            "required": ["class_name"]
        },
        endpoint="/api/class/{class_name}/drugs"
    ),
    ToolDefinition(
        name="search_classes",
        description="Search for pharmacological classes by name. Use when user mentions a drug class or asks about drug categories. Returns classes with ingredient counts.",
        parameters={
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Class name to search for (e.g., 'antibiotic', 'statin', 'antihypertensive')"}
            },
            "required": ["q"]
        },
        endpoint="/api/classes/search"
    )
]

SYSTEM_PROMPT = """You are a clinical pharmaceutical advisor with access to FDA drug data and expert-curated clinical weights.

CRITICAL WORKFLOW FOR ALTERNATIVE/COMPARISON QUERIES:
1. Call search_drugs to get the drug_id (a hash like "7dbb03eb94c1cc69")
2. Call get_related_drugs with that drug_id (NOT the drug name)
3. Present results using the CLINICAL WEIGHTING data

INDICATION-SPECIFIC RE-WEIGHTING:
If the user mentions a specific clinical context, pass the indication parameter to get_related_drugs:
- "statin intolerance" → indication: "statin_intolerance" (ezetimibe becomes PRIMARY)
- "hypertriglyceridemia" → indication: "hypertriglyceridemia" (fibrates promoted)
- "cardiovascular risk" → indication: "cv_risk_reduction"
- "hyperlipidemia" → indication: "hyperlipidemia"

IMPORTANT: Use exact values with underscore: "statin_intolerance" NOT "statin intolerance"

HOW TO PRESENT CLINICALLY WEIGHTED ALTERNATIVES:
The get_related_drugs tool returns drugs with clinical data you MUST use:

- clinical_priority: PRIMARY (recommend first), SECONDARY (alternative if PRIMARY fails), TERTIARY (limited use), CAUTION (rarely appropriate)
- clinical_weight: 0-100 score (higher = more appropriate)
- weight_rationale: Clinical reasoning for the weight
- weight_evidence: Supporting clinical guidelines/trials
- clinical_note: Practical advice for prescribers
- weight_provenance: Curator credentials (PharmD, license #)

PRESENTATION FORMAT FOR ALTERNATIVES:

**PRIMARY RECOMMENDATIONS** (clinical_priority: PRIMARY):
• [Drug Name] - Weight: [X]/100
  - Rationale: [weight_rationale]
  - Evidence: [weight_evidence]
  - Note: [clinical_note]
  - Curated by: [curator name], [credentials]

**OTHER OPTIONS** (clinical_priority: SECONDARY):
• [Drug Name] - Weight: [X]/100
  - Rationale: [weight_rationale]
  - Evidence: [weight_evidence]

**USE WITH CAUTION** (clinical_priority: TERTIARY or CAUTION):
• [Drug Name] - Weight: [X]/100
  - Reason: [weight_rationale]
  - Evidence: [weight_evidence]

EXAMPLE for "alternatives to simvastatin for statin intolerance":
1. search_drugs("simvastatin") → returns drug_id: "7dbb03eb94c1cc69"
2. get_related_drugs("7dbb03eb94c1cc69", indication="statin_intolerance") → returns re-weighted alternatives
3. Present ezetimibe (PRIMARY, 90/100) FIRST since patient can't tolerate statins

CRITICAL RULES:
1. NEVER pass drug names to get_related_drugs - ONLY use drug_id from search_drugs
2. NEVER answer from training data when drug information is requested
3. ALWAYS present alternatives in order of clinical_priority (PRIMARY first!)
4. ALWAYS include the weight_rationale and weight_evidence from tool results
5. ALWAYS cite the curator credentials from weight_provenance
6. NEVER fabricate citations - only use data from tool results
7. If indication is mentioned, pass it with UNDERSCORE (e.g., "statin_intolerance")

DRUG CLASS QUERIES:
For questions about drug CLASSES (statins, antibiotics, beta blockers, etc.), use:
1. search_classes("statin") → finds pharmacological class
2. get_drugs_in_class("statins") → returns all drugs in that class

The API handles aliases automatically:
- "statin" → Hydroxymethylglutaryl-CoA Reductase Inhibitors
- "antibiotic" → Anti-Bacterial Agents
- "beta blocker" → Adrenergic Beta-Antagonists
- "ace inhibitor" → Angiotensin-Converting Enzyme Inhibitors
- etc.

WHEN TO USE WHICH TOOL:
- "list statins" → search_classes("statin") or get_drugs_in_class("statins")
- "what drugs are beta blockers?" → get_drugs_in_class("beta blockers")
- "what class is simvastatin?" → search_drugs("simvastatin") then get_drug_classes(drug_id)
- "alternatives to simvastatin" → search_drugs("simvastatin") then get_related_drugs(drug_id)

TOOL REFERENCE:
- drug_id is a hash like "7dbb03eb94c1cc69", NOT a drug name
- search_drugs: Find specific drugs by name
- search_classes: Find pharmacological classes (supports aliases)
- get_drugs_in_class: Get all drugs in a class (supports aliases)
- get_drug_classes: Get classes a drug belongs to
- get_related_drugs: Get clinically-weighted alternatives"""

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

async def execute_tool_call(tool_name: str, arguments: Dict) -> Dict:
    """Execute a tool call by making an API request."""
    tool = get_tool_by_name(tool_name)
    if not tool:
        return {"error": f"Unknown tool: {tool_name}"}
    
    # Build the endpoint URL
    endpoint = tool.endpoint
    params = {}
    
    # Handle different endpoint patterns
    for key, value in arguments.items():
        placeholder = f"{{{key}}}"
        if placeholder in endpoint:
            endpoint = endpoint.replace(placeholder, str(value))
        else:
            params[key] = value
    
    # Special handling for search_drugs - endpoint expects 'q' not 'query'
    if tool_name == "search_drugs" and "query" in params:
        params["q"] = params.pop("query")
    
    # Normalize indication parameter - convert spaces to underscores
    if "indication" in params and params["indication"]:
        params["indication"] = params["indication"].replace(" ", "_").lower()
    
    # Make the API call
    async with httpx.AsyncClient(timeout=30.0) as client:
        base_url = "http://localhost:8000"
        try:
            response = await client.get(f"{base_url}{endpoint}", params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"API returned status {response.status_code}", "details": response.text}
        except Exception as e:
            return {"error": str(e)}

async def chat_query(user_message: str, conversation_history: List[Dict] = None) -> Dict:
    """Process a user query with tool calling support."""
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if conversation_history:
        messages.extend(conversation_history)
    
    messages.append({"role": "user", "content": user_message})
    
    tools = get_tool_definitions()
    
    tool_calls_log = []
    max_iterations = 5
    
    for iteration in range(max_iterations):
        response = await call_venice(messages, tools)
        
        # Debug logging
        print(f"[DEBUG] Response: {response}")
        
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        print(f"[DEBUG] Message: {message}")
        
        # Check if we have tool calls (JSON or text format)
        tool_calls = message.get("tool_calls", [])
        
        # Also check for text-based tool calls
        if not tool_calls and message.get("content"):
            text_tool_calls = parse_text_tool_call(message["content"])
            if text_tool_calls:
                tool_calls = text_tool_calls
                message["tool_calls"] = tool_calls  # Add to message for proper handling
        
        if tool_calls:
            messages.append(message)
            
            for tool_call in message["tool_calls"]:
                tool_name = tool_call["function"]["name"]
                arguments = json.loads(tool_call["function"]["arguments"])
                
                result = await execute_tool_call(tool_name, arguments)
                
                tool_calls_log.append({
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": result
                })
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result)
                })
        
        # Check if we have a final response
        elif message.get("content"):
            return {
                "response": message["content"],
                "tool_calls": tool_calls_log,
                "drugs_found": None
            }
        
        else:
            break
    
    return {
        "response": "I was unable to complete your request. Please try again.",
        "tool_calls": tool_calls_log,
        "drugs_found": None
    }
