"""
LangChain tools that the agent can use to interact with the system.
"""

from typing import Any
from langchain.tools import tool
from actions.executor import ActionExecutor

# Global executor instance for tools to use
_executor = ActionExecutor()

@tool
def click_element(element_name: str, x: int, y: int) -> str:
    """Click on a UI element at the specified screen coordinates.
    
    Args:
        element_name: A short description of what is being clicked (for logging purposes).
        x: The X coordinate on the screen.
        y: The Y coordinate on the screen.
        
    Returns:
        A status message indicating success or failure.
    """
    return _executor.click(x, y)


@tool
def type_text(text: str) -> str:
    """Type a string of text using the keyboard.
    
    Args:
        text: The text to type.
        
    Returns:
        A status message indicating success or failure.
    """
    return _executor.type_text(text)


@tool
def press_key(key: str) -> str:
    """Press a specific keyboard key (e.g., 'enter', 'tab', 'escape').
    
    Args:
        key: The name of the key to press.
        
    Returns:
        A status message indicating success or failure.
    """
    return _executor.press_key(key)


def get_all_tools() -> list[Any]:
    """Return the list of tools available to the agent."""
    return [click_element, type_text, press_key]
