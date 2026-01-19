"""Claude API integration with MCP connector for additional research."""

import anthropic
import httpx
from typing import Optional

from src.settings import settings
from src.logging_conf import logger


def call_claude(system_prompt: str, user_message: str = "") -> str:
    """
    Call Claude API with MCP connector for database access.
    
    Args:
        system_prompt: Fully rendered system prompt with context
        user_message: Optional additional user message
    
    Returns:
        Claude's response text (markdown)
    """
    # Create client with extended timeout for MCP tool calls
    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=httpx.Timeout(300.0, connect=30.0)  # 5 min total, 30s connect
    )
    
    # Build messages
    messages = []
    if user_message:
        messages.append({"role": "user", "content": user_message})
    else:
        # If no explicit user message, use a generic prompt
        messages.append({
            "role": "user", 
            "content": "Please analyze the context provided and respond according to your instructions."
        })
    
    # MCP server configuration
    mcp_servers = [
        {
            "type": "url",
            "url": settings.mcp_server_url,
            "name": "ibhelm-db",
            "authorization_token": settings.mcp_bearer_token
        }
    ]
    
    # MCP toolset - enable all tools
    tools = [
        {
            "type": "mcp_toolset",
            "mcp_server_name": "ibhelm-db"
        }
    ]
    
    try:
        logger.info(f"Calling Claude ({settings.claude_model}) with MCP connector")
        logger.info(f"MCP server: {settings.mcp_server_url}")
        
        # Use beta endpoint for MCP connector
        response = client.beta.messages.create(
            model=settings.claude_model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            mcp_servers=mcp_servers,
            tools=tools,
            betas=["mcp-client-2025-11-20"]
        )
        
        logger.info(f"Response received - stop_reason: {response.stop_reason}")
        logger.info(f"Response content blocks: {len(response.content)}")
        
        # Extract text from response, log all block types
        result_text = ""
        for i, block in enumerate(response.content):
            block_type = type(block).__name__
            logger.debug(f"Block {i}: {block_type}")
            
            if hasattr(block, 'text'):
                result_text += block.text
            elif hasattr(block, 'type') and block.type == 'mcp_tool_use':
                logger.debug(f"  MCP tool call: {getattr(block, 'name', 'unknown')}")
            elif hasattr(block, 'type') and block.type == 'mcp_tool_result':
                logger.debug(f"  MCP tool result received")
        
        logger.info(f"Claude response text ({len(result_text)} chars)")
        return result_text
        
    except anthropic.APIError as e:
        logger.error(f"Claude API error: {e}")
        return f"❌ AI error: {str(e)}"
    except httpx.TimeoutException as e:
        logger.error(f"Timeout calling Claude API: {e}")
        return f"❌ AI timeout - request took too long"
    except Exception as e:
        logger.error(f"Unexpected error calling Claude: {e}", exc_info=True)
        return f"❌ AI error: {str(e)}"


def call_claude_simple(system_prompt: str, user_message: str = "") -> str:
    """
    Call Claude API without MCP connector (for testing or when MCP is not needed).
    
    Args:
        system_prompt: Fully rendered system prompt with context
        user_message: Optional additional user message
    
    Returns:
        Claude's response text (markdown)
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    
    messages = []
    if user_message:
        messages.append({"role": "user", "content": user_message})
    else:
        messages.append({
            "role": "user", 
            "content": "Please analyze the context provided and respond according to your instructions."
        })
    
    try:
        logger.info(f"Calling Claude ({settings.claude_model}) without MCP")
        
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
        )
        
        result_text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                result_text += block.text
        
        logger.info(f"Claude response received ({len(result_text)} chars)")
        return result_text
        
    except anthropic.APIError as e:
        logger.error(f"Claude API error: {e}")
        return f"❌ AI error: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error calling Claude: {e}")
        return f"❌ AI error: {str(e)}"

