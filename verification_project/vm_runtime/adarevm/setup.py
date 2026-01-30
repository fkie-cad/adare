from setuptools import setup, find_packages

setup(
    name="adarevm",
    version="0.1.0",
    description="ADARE guest VM agent for executing GUI automation playbooks",
    author="miqsoft",
    author_email="mksaxhandball@gmail.com",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "adarelib",
        "pyautogui>=0.9.54",
        "pillow>=11.3.0",
        "websockets>=15.0",
        "cattrs>=23.2.3",
        "attrs>=24.0.0",
        "python-dateutil>=2.9.0.post0",
        "python-ulid>=2.7.0",
        "pytz>=2025.2",
    ],
    entry_points={
        "console_scripts": [
            "adarevm=adarevm.main:run",
        ],
    },
)
