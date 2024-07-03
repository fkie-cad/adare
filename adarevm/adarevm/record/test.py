from pynput import mouse
import time


def on_click(x, y, button, pressed):
    print(f"{x}, {y}, {button}, {pressed}")


if __name__ == "__main__":
    listener = mouse.Listener(on_click=on_click)
    listener.start()
    time.sleep(20)
    listener.join()

