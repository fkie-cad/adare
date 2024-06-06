from rich.console import Console
import time

# Create a Rich console object
console = Console()

# Define the two styled outputs
output1 = "[bold magenta]Output 1: Hello, this is a styled output![/bold magenta]"
output2 = "[bold green]Output 2: Another styled output, with different style![/bold green]"

# Start with the first output
current_output = output1
console.print(current_output)


def toggle_output():
    global current_output
    console.clear()  # Clear the console for clean toggle
    if current_output == output1:
        current_output = output2
    else:
        current_output = output1
    console.print(current_output)


def main():
    # Keep the program running
    console.print("[italic]Press 't' and Enter to toggle output, 'q' to quit.[/italic]")
    while True:
        user_input = input("Enter command: ")
        if user_input == 't':
            toggle_output()
        elif user_input == 'q':
            break
        else:
            console.print("[red]Invalid command, use 't' to toggle or 'q' to quit.[/red]")
