from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

from prompt_toolkit import prompt
from prompt_toolkit.history import InMemoryHistory

def get_prompt():
    # This function generates the prompt string. You can customize it as needed.
    # For example, fetching the username from the environment or any other logic.
    username = "user"
    return f"{username}@shell> "

def main():
    history = InMemoryHistory()

    while True:
        try:
            # Use the get_prompt function to dynamically generate the prompt message.
            user_input = prompt(get_prompt(), history=history)
            print(f"Executing: {user_input}")
            # Here, you can add your logic to handle the command entered by the user.
            # This is just a placeholder for demonstration.
            if user_input.lower() == "exit":
                break
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            break
        except EOFError:
            # Handle Ctrl+D gracefully
            break


