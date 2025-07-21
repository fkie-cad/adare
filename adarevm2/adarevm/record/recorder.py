# import os
# import time

import pyautogui
from pynput import mouse, keyboard
from datetime import datetime
# import ctypes
# import platform
from pathlib import Path
# import subprocess
# import cv2


# def extract_icon(image_path, x, y, search_radius=50, output_image_path="extracted_icon.png"):
#     """
#     Extracts an icon from an image at a given position.
#
#     Parameters:
#         image_path (str): Path to the screenshot.
#         x (int): X-coordinate of the position.
#         y (int): Y-coordinate of the position.
#         search_radius (int): Radius around the position to detect the icon.
#         output_image_path (str): Path to save the extracted icon.
#
#     Returns:
#         extracted_icon (numpy array): Extracted icon image or None if no icon found.
#     """
#     # Load the image
#     img = cv2.imread(image_path)
#     if img is None:
#         print("Error: Image not found.")
#         return None
#
#     gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
#
#     # Define search area
#     h, w = gray.shape
#     x1, y1 = max(0, x - search_radius), max(0, y - search_radius)
#     x2, y2 = min(w, x + search_radius), min(h, y + search_radius)
#     region = gray[y1:y2, x1:x2]
#
#     # Apply Gaussian Blur to reduce noise
#     blurred = cv2.GaussianBlur(region, (5, 5), 0)
#
#     # Apply adaptive thresholding (alternative to Canny)
#     edges = cv2.Canny(blurred, 50, 150)
#
#     # Debugging: Save the edge-detected image for review
#     cv2.imwrite("debug_edges.png", edges)
#
#     # Find contours
#     contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
#
#     if not contours:
#         print("No icon detected. Check 'debug_edges.png' for analysis.")
#         return None
#
#     # Find the largest contour
#     largest_contour = max(contours, key=cv2.contourArea)
#
#     # Get bounding box of the icon
#     x_offset, y_offset, w, h = cv2.boundingRect(largest_contour)
#
#     # Apply padding
#     padding = 5
#     x1_crop = max(0, x1 + x_offset - padding)
#     y1_crop = max(0, y1 + y_offset - padding)
#     x2_crop = min(img.shape[1], x1 + x_offset + w + padding)
#     y2_crop = min(img.shape[0], y1 + y_offset + h + padding)
#
#     # Extract and save the icon
#     extracted_icon = img[y1_crop:y2_crop, x1_crop:x2_crop]
#
#     if extracted_icon.size == 0:
#         print("Error: Extracted icon is empty. Check 'debug_edges.png' for contour issues.")
#         return None
#
#     return extracted_icon

import logging
log = logging.getLogger(__name__)

class Recorder:
    def __init__(self, screenshot_directory: Path, logfile: Path, trigger_keys: set):
        self.screenshot_directory = screenshot_directory
        self.logfile = logfile
        self.trigger_keys = trigger_keys  # Set of keys to start/stop recording
        self.recording = False  # Recording state
        self.pressed_keys = set()
        self.mouse_listener = None
        self.keyboard_listener = keyboard.Listener(on_press=self.__on_keyboard_press,
                                                   on_release=self.__on_keyboard_release)

    def __on_keyboard_press(self, key):
        log.debug(f"Key pressed: {key}")
        try:
            key = key.char
        except AttributeError:
            key = str(key)

        self.pressed_keys.add(str(key))
        if self.trigger_keys.issubset(self.pressed_keys):
            self.recording = not self.recording  # Toggle recording state
            self.pressed_keys.clear()  # Clear keys to avoid false triggers
            state = "STARTED" if self.recording else "STOPPED"
            log.info(f"Recording {state}")
            with open(self.logfile, "a") as file:
                file.write(f"{datetime.now().timestamp()} - RECORDING {state}\n")

            if self.recording:
                self.__start_mouse_listener()
            else:
                self.stop()

        if self.recording:
            timestamp = datetime.now().timestamp()
            with open(self.logfile, "a") as file:
                file.write(f"{timestamp} - KEY - {key}\n")

    def __on_keyboard_release(self, key):
        try:
            key = key.char
        except AttributeError:
            key = str(key)

        self.pressed_keys.discard(key)  # Remove key safely

    def __on_mouse_click(self, x, y, button, pressed):
        if self.recording:
            timestamp = datetime.now().timestamp()
            with open(self.logfile, "a") as file:
                file.write(f"{timestamp} - {button} - {pressed} - {x} - {y}\n")
            self.__screenshot(str(timestamp))

    def __on_scroll(self, x, y, dx, dy):
        if self.recording:
            timestamp = datetime.now().timestamp()
            with open(self.logfile, "a") as file:
                file.write(f"{timestamp} - SCROLL - {dx} - {dy} - {x} - {y}\n")

    def __screenshot(self, timestamp: str):
        screenshot = pyautogui.screenshot()
        screenshot.save(self.screenshot_directory / f"{timestamp}.png")

    def __start_mouse_listener(self):
        if self.mouse_listener is None or not self.mouse_listener.running:
            self.mouse_listener = mouse.Listener(on_click=self.__on_mouse_click, on_scroll=self.__on_scroll)
            self.mouse_listener.start()

    def __stop_mouse_listener(self):
        if self.mouse_listener and self.mouse_listener.running:
            self.mouse_listener.stop()

    def start(self):
        print(f"Press '{'+'.join(self.trigger_keys)}' to start/stop recording.")
        self.keyboard_listener.start()
        self.keyboard_listener.join()

    def stop(self):
        self.__stop_mouse_listener()
        self.keyboard_listener.stop()


if __name__ == "__main__":
    screenshot_directory = Path("screenshots")
    # #result = extract_icon((screenshot_directory/'1738679773.362516.png').as_posix(), 267, 410)
    # #result = extract_icon((screenshot_directory / '1738679773.575831.png').as_posix(), 1341, 8)
    # #result = extract_icon((screenshot_directory / '1738679775.219464.png').as_posix(), 2408, 42)
    # result = extract_icon((screenshot_directory / '1738679779.794994.png').as_posix(), 712, 1170)
    # path = screenshot_directory / "icon.png"
    # cv2.imwrite(path.as_posix(), result)
    #
    # from guibot.guibot import GuiBot
    # gb = GuiBot()
    # print(gb.find(path.as_posix()))

    # def __hide_cursor(self):
    #     if self.system == "Windows":
    #         ctypes.windll.user32.ShowCursor(False)
    #     elif self.system == "Linux":
    #         # disabled by default
    #         pass
    #         # self.hide_cursor_process = subprocess.Popen(["unclutter", "-idle", "0.1"])
    #     else:
    #         raise NotImplementedError(f"Platform {platform.system()} not supported")
    #
    # def __show_cursor(self):
    #     if self.system == "Windows":
    #         ctypes.windll.user32.ShowCursor(True)
    #     elif self.system == "Linux":
    #         # disabled by default
    #         pass
    #         # stop unclutter process
    #         #self.hide_cursor_process.kill()
    #     else:
    #         raise NotImplementedError(f"Platform {platform.system()} not supported")

    screenshot_directory.mkdir(exist_ok=True)
    logfile = Path("log.txt")
    recorder = Recorder(screenshot_directory, logfile, trigger_keys={"Key.ctrl", "Key.alt", "r"})
    recorder.start()
