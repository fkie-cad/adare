
import logging
import sys
from adarelib.common.variables import VariableRegistry, Variable, VariableType

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def test_raw_string_resolution():
    print("Testing raw string variable resolution...")
    
    # Create a registry
    registry = VariableRegistry()
    
    # Add a variable with r"..." format
    raw_value = r'r"C:\Users\adare\Documents\TestCase"'
    print(f"Adding variable 'case_directory' with value: {raw_value}")
    
    # We simulate what comes from YAML: the string literally contains the characters r " ... "
    # Note: In Python, r'r"..."' means the string is r"..." 
    registry.add("case_directory", Variable.auto_infer(raw_value))
    
    # Add a dependent variable to test nested resolution
    registry.add("command", Variable.auto_infer('Get-Item "{{ case_directory }}"'))

    # Resolve context
    context = registry.to_execution_context()
    resolved_dir = context.get("case_directory")
    
    print(f"Resolved 'case_directory': {resolved_dir}")
    
    # Check expectations
    expected = r"C:\Users\adare\Documents\TestCase"
    
    if resolved_dir == expected:
        print("SUCCESS: Raw string prefix was stripped.")
    else:
        print(f"FAILURE: Expected '{expected}', got '{resolved_dir}'")
        if resolved_dir == raw_value:
             print("Confirmation: The r\"...\" wrapper was preserved.")

if __name__ == "__main__":
    test_raw_string_resolution()
