import os
import time

import pyautogui
from pynput import mouse, keyboard
from datetime import datetime
import ctypes
import platform
from pathlib import Path
import subprocess


class Recorder:
    mouse_listener: mouse.Listener
    keyboard_listener: keyboard.Listener
    screenshot_directory: Path
    logfile: Path
    system = platform.system()
    hide_cursor_process = None

    def __init__(self, screenshot_directory: Path, logfile: Path):
        self.__install_listeners()
        self.screenshot_directory = screenshot_directory
        self.logfile = logfile

    def __on_keyboard_press(self, key):
        try:
            key = key.char
        except AttributeError:
            key = str(key)

        with open(self.logfile, "a") as file:
            file.write(f"{datetime.now()} - {key}\n")

    def __on_mouse_click(self, x, y, button, pressed):
        timestamp = datetime.now().timestamp()
        with open(self.logfile, "a") as file:
            file.write(f"{timestamp} - {button} - {pressed} - {x} - {y}\n")
        self.__screenshot(str(timestamp))

    def __hide_cursor(self):
        if self.system == "Windows":
            ctypes.windll.user32.ShowCursor(False)
        elif self.system == "Linux":
            self.hide_cursor_process = subprocess.Popen(["unclutter", "-idle", "0.1"])
        else:
            raise NotImplementedError(f"Platform {platform.system()} not supported")

    def __show_cursor(self):
        if self.system == "Windows":
            ctypes.windll.user32.ShowCursor(True)
        elif self.system == "Linux":
            # stop unclutter process
            self.hide_cursor_process.kill()
        else:
            raise NotImplementedError(f"Platform {platform.system()} not supported")

    def __screenshot(self, timestamp: str):
        screenshot = pyautogui.screenshot()
        screenshot.save(self.screenshot_directory / f"{timestamp}.png")

    def __install_listeners(self):
        self.keyboard_listener = keyboard.Listener(on_press=self.__on_keyboard_press)
        self.mouse_listener = mouse.Listener(on_click=self.__on_mouse_click)

    def start(self):
        self.mouse_listener.start()
        self.keyboard_listener.start()

    def stop(self):
        self.mouse_listener.join()
        self.keyboard_listener.join()


if __name__ == "__main__":
    screenshot_directory = Path("screenshots")
    screenshot_directory.mkdir(exist_ok=True)
    logfile = Path("log.txt")
    recorder = Recorder(screenshot_directory, logfile)
    recorder.start()
    time.sleep(40)
    recorder.stop()
