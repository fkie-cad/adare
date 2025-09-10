*************************
Complete Playbook Reference
*************************

This comprehensive reference covers all possibilities for writing ADARE playbooks. Playbooks use YAML syntax to define GUI automation steps for experiments.

Basic Structure
***************

Every playbook has this basic structure:

.. code-block:: yaml

    settings:           # Global settings (optional)
      idle: 1.0
      timeout: 300
      screenshot:
        format: "png"
        quality: 95
        
    variables:          # Variables for templating (optional)
      username: "testuser"
      filepath: "/home/{{ username }}/test.txt"
      
    actions:            # List of actions to execute
      - action_type:
          # action parameters
      - another_action:
          # parameters

Settings Section
****************

The ``settings`` section configures global playbook behavior:

.. code-block:: yaml

    settings:
      idle: 2.5                    # Default pause between actions (seconds)
      timeout: 600                 # Overall experiment timeout (seconds)
      screenshot:                  # Default screenshot settings
        format: "png"              # Image format: "png" or "jpg"
        quality: 95                # Quality for JPEG (1-100)

Variables Section
*****************

Variables allow templating throughout the playbook:

.. code-block:: yaml

    variables:
      username: "vagrant"
      password: "secret123"
      filepath: "/home/{{ username }}/testfile.txt"
      url: "https://example.com/{{ username }}"
      timeout_value: 30

Variables can reference other variables using Jinja2 template syntax ``{{ variable_name }}``.

Action Types
************

Click Actions
=============

**Basic Click**

.. code-block:: yaml

    - click:
        target:
          image: "button.png"      # Click on image
          # OR
          text: "Login"            # Click on text
          # OR  
          position: [100, 200]     # Click at coordinates
        description: "Click the login button"

**Right Click**

.. code-block:: yaml

    - right_click:
        target:
          text: "File"
        description: "Right-click on File menu"

**Double Click**

.. code-block:: yaml

    - double_click:
        target:
          image: "folder.png"
        description: "Double-click folder to open"

Target Selection Strategies
===========================

When multiple matches are found, use strategies to select the desired one:

.. code-block:: yaml

    - click:
        target:
          text: "Submit"
          strategy:
            # Select the nth match (1-based indexing)
            SweepStrategy:
              index: 2
            # OR select match with highest confidence
            BestConfidenceStrategy: {}
            # OR select match closest to coordinates
            ClosestToStrategy:
              x: 500
              y: 300
            # OR select by position
            TopLeftStrategy: {}        # Topmost-leftmost
            TopRightStrategy: {}       # Topmost-rightmost  
            BottomLeftStrategy: {}     # Bottommost-leftmost
            BottomRightStrategy: {}    # Bottommost-rightmost
            # OR select by size
            LargestStrategy: {}        # Largest bounding box
            SmallestStrategy: {}       # Smallest bounding box

Keyboard Actions
================

**Type Text**

.. code-block:: yaml

    - keyboard:
        keys: "{{ username }}"
        description: "Type username"

**Key Combinations**

.. code-block:: yaml

    - keyboard:
        combination: ["ctrl", "c"]
        description: "Copy shortcut"
        
    - keyboard:
        combination: ["ctrl", "shift", "n"]
        description: "Multiple key combination"
        
    - keyboard:
        combination: ["alt", "f4"]
        description: "Alt+F4"

**Special Keys**

.. code-block:: yaml

    - keyboard:
        combination: ["enter"]
        description: "Press Enter"
        
    - keyboard:
        combination: ["delete"]
        description: "Press Delete key"
        
    - keyboard:
        combination: ["tab"]
        description: "Press Tab"

Movement and Interaction
========================

**Drag and Drop**

.. code-block:: yaml

    - drag:
        source:
          image: "file.png"
        destination:
          text: "Trash"
        description: "Drag file to trash"

**Mouse Movement**

.. code-block:: yaml

    - goto:
        target:
          position: [500, 300]
        description: "Move mouse to coordinates"

**Scrolling**

.. code-block:: yaml

    - scroll:
        direction: "down"          # "up", "down", "left", "right"
        amount: 5                  # Number of scroll steps
        description: "Scroll down 5 steps"

Command Execution  
=================

**Basic Command**

.. code-block:: yaml

    - command:
        name: "Create Directory"
        description: "Create test directory"
        cmd: "mkdir -p /tmp/{{ username }}"
        timeout: 10

**Command with Tool**

.. code-block:: yaml

    - command:
        name: "Download File"
        tool: "curl"                           # Tool/executable name
        command: "curl -o {{ filepath }} {{ url }}"  # Command to run
        cwd: "/tmp"                            # Working directory
        env:                                   # Environment variables
          USER: "{{ username }}"
          TIMEOUT: "{{ timeout_value }}"
        timeout: 60.0                          # Command timeout
        shell: true                            # Run in shell

**Windows Command**

.. code-block:: yaml

    - command:
        name: "Windows Command"
        cmd: "dir C:\\Users\\{{ username }}"
        shell: true
        description: "List user directory"

Utility Actions
===============

**Wait/Pause**

.. code-block:: yaml

    - idle:
        duration: 3.0
        description: "Wait 3 seconds"

**Take Screenshot**

.. code-block:: yaml

    # Full screenshot
    - screenshot:
        description: "Capture full screen"
        
    # Partial screenshot
    - screenshot:
        description: "Capture specific area"
        x: 100              # Top-left X coordinate
        y: 200              # Top-left Y coordinate  
        width: 400          # Width in pixels
        height: 300         # Height in pixels

**Save Timestamp**

.. code-block:: yaml

    - save_timestamp:
        variable: "TIMESTAMP.START"
        description: "Record start time"
        
    - save_timestamp:
        variable: "TIMESTAMP.DELETION"
        description: "Record when file was deleted"

Test Execution
==============

Tests are defined in ``testset.yml`` and executed in playbooks:

**Inline Test**

.. code-block:: yaml

    - test: "file_exists"

**Detailed Test**

.. code-block:: yaml

    - test:
        name: "network_connectivity"
        description: "Check network connection"

Conditional Execution
*********************

Block Actions
=============

Group actions together and execute conditionally:

**Simple Block**

.. code-block:: yaml

    - block:
        description: "Group of related actions"
        actions:
          - command:
              cmd: "echo 'Block action 1'"
          - idle:
              duration: 1.0
          - command:
              cmd: "echo 'Block action 2'"

**Conditional Block - Exists**

.. code-block:: yaml

    - block:
        description: "Execute if element exists"
        when:
          - exists:
              text: "Continue"
        actions:
          - click:
              target:
                text: "Continue"
          - keyboard:
              keys: "proceeding..."

**Conditional Block - Not Exists**

.. code-block:: yaml

    - block:
        description: "Execute if element doesn't exist"
        when:
          - not_exists:
              image: "error.png"
        actions:
          - command:
              cmd: "echo 'No error detected'"

**Multiple Conditions**

All conditions must be met (AND logic):

.. code-block:: yaml

    - block:
        description: "Multiple conditions required"
        when:
          - exists:
              text: "Ready"
          - not_exists:
              image: "loading.png"
        actions:
          - command:
              cmd: "echo 'System is ready'"
          - screenshot:
              description: "Ready state screenshot"

**Image-based Conditions**

.. code-block:: yaml

    - block:
        description: "Check for dialog"
        when:
          - exists:
              image: "dialog.png"
        actions:
          - click:
              target:
                text: "OK"
          - keyboard:
              combination: ["enter"]

**Nested Blocks**

.. code-block:: yaml

    - block:
        description: "Outer block"
        actions:
          - command:
              cmd: "echo 'Outer block start'"
          - block:
              description: "Inner block"
              when:
                - exists:
                    text: "Inner Condition"
              actions:
                - click:
                    target:
                      text: "Inner Button"
                - keyboard:
                    keys: "inner action"
          - command:
              cmd: "echo 'Outer block end'"

Conditional Keyboard Actions
============================

Individual actions can also have conditions:

.. code-block:: yaml

    - keyboard:
        keys: "test input"
        when:
          - exists:
              text: "Input Field"
        description: "Type only if input field is visible"

Advanced Features
*****************

Variable Templating
===================

Use Jinja2 template syntax for dynamic values:

.. code-block:: yaml

    variables:
      username: "testuser"
      base_path: "/home/{{ username }}"
      log_file: "{{ base_path }}/experiment.log"
      
    actions:
      - command:
          cmd: "touch {{ log_file }}"
      - keyboard:
          keys: "Hello {{ username }}!"

Template Functions
==================

ADARE supports some template functions:

.. code-block:: yaml

    - command:
        cmd: "python3 -c \"print('Hello {{ username }}!')\""
        cwd: "{{ filepath | dirname }}"        # Get directory of filepath
        description: "Command with template function"

Complex Examples
****************

File Management Workflow
=========================

.. code-block:: yaml

    settings:
      idle: 1.0
      timeout: 300
      
    variables:
      username: "vagrant"
      test_file: "C:/Users/{{ username }}/Documents/test.txt"
      
    actions:
      # Create test file
      - command:
          name: "Create Test File"
          cmd: "echo 'Test content' > '{{ test_file }}'"
          shell: true
          
      # Open File Explorer  
      - click:
          target:
            image: "explorer.png"
          description: "Open File Explorer"
          
      # Navigate to Documents
      - click:
          target:
            text: "Documents"
            strategy:
              SweepStrategy:
                index: 2
          description: "Click Documents folder"
          
      # Right-click on test file
      - right_click:
          target:
            text: "test.txt"
          description: "Right-click test file"
          
      # Delete file
      - click:
          target:
            text: "Delete"
          description: "Click Delete from context menu"
          
      # Confirm deletion if dialog appears
      - block:
          when:
            - exists:
                text: "Are you sure"
          actions:
            - click:
                target:
                  text: "Yes"
            - save_timestamp:
                variable: "TIMESTAMP.DELETED"

Multi-Application Workflow
==========================

.. code-block:: yaml

    actions:
      # Open first application
      - keyboard:
          combination: ["win", "r"]
          description: "Open Run dialog"
          
      - keyboard:
          keys: "notepad"
          description: "Type notepad"
          
      - keyboard:
          combination: ["enter"]
          description: "Press Enter to launch"
          
      # Wait for application to load
      - idle:
          duration: 2.0
          
      # Type content only if notepad is ready
      - block:
          when:
            - exists:
                text: "Untitled - Notepad"
          actions:
            - keyboard:
                keys: "This is test content from {{ username }}"
            - keyboard:
                combination: ["ctrl", "s"]
            - keyboard:
                keys: "{{ username }}_test.txt"
            - keyboard:
                combination: ["enter"]
                
      # Switch to browser
      - keyboard:
          combination: ["alt", "tab"]
          description: "Switch applications"
          
      # Navigate to website
      - keyboard:
          combination: ["ctrl", "l"]
          description: "Focus address bar"
          
      - keyboard:
          keys: "https://example.com"
          
      - keyboard:
          combination: ["enter"]

Error Handling Pattern
======================

.. code-block:: yaml

    actions:
      # Try main action
      - click:
          target:
            text: "Submit"
          description: "Try to submit form"
          
      # Handle success case
      - block:
          description: "Handle successful submission"
          when:
            - exists:
                text: "Success"
          actions:
            - screenshot:
                description: "Success screenshot"
            - save_timestamp:
                variable: "TIMESTAMP.SUCCESS"
                
      # Handle error case  
      - block:
          description: "Handle submission error"
          when:
            - exists:
                text: "Error"
            - not_exists:
                text: "Success"
          actions:
            - screenshot:
                description: "Error screenshot"  
            - click:
                target:
                  text: "Try Again"

Common Pitfalls
***************

1. **Missing Waits**: Not allowing enough time for UI elements to appear
2. **Ambiguous Targets**: Text or images that match multiple elements without strategies
3. **No Error Handling**: Not accounting for different possible UI states

Complete Parameter Reference
****************************

This section lists all available parameters for each action type, indicating which are required vs optional.

Click Actions Parameters
========================

**ClickAction, RightClickAction, DoubleClickAction:**

.. code-block:: yaml

    - click:  # or right_click, double_click
        target:                    # REQUIRED - Target definition
          image: "file.png"        # Image file (relative to img/ folder)
          # OR
          text: "Button Text"      # Text to find on screen  
          # OR
          position: [x, y]         # Exact coordinates [x, y]
          strategy:                # OPTIONAL - Selection strategy (see strategies section)
            SweepStrategy:
              index: 2
        description: "Action description"  # OPTIONAL but recommended

**DragAction:**

.. code-block:: yaml

    - drag:
        source:                    # REQUIRED - Source target
          image: "file.png"
        destination:               # REQUIRED - Destination target  
          text: "Trash"
        description: "Drag description"    # OPTIONAL but recommended

**GotoAction:**

.. code-block:: yaml

    - goto:
        target:                    # REQUIRED - Target position
          position: [500, 300]     # Usually coordinates for goto
        description: "Move description"    # OPTIONAL but recommended

Keyboard Action Parameters
==========================

.. code-block:: yaml

    - keyboard:
        keys: "text to type"       # OPTIONAL - Text to type
        # OR
        combination: ["ctrl", "c"] # OPTIONAL - Key combination list
        when:                      # OPTIONAL - Conditional execution
          - exists:
              text: "Input Field"
          # OR  
          - not_exists:
              image: "dialog.png"
        description: "Keyboard description"  # OPTIONAL but recommended

**Note:** Either ``keys`` OR ``combination`` must be specified, not both.

Command Action Parameters
=========================

.. code-block:: yaml

    - command:
        name: "Command Name"       # OPTIONAL - Display name
        description: "What it does" # OPTIONAL but recommended
        cmd: "echo hello"          # OPTIONAL - Command string
        # OR
        command: "curl -o file"    # OPTIONAL - Alternative to cmd  
        tool: "curl"               # OPTIONAL - Executable name/path
        cwd: "/working/directory"  # OPTIONAL - Working directory
        env:                       # OPTIONAL - Environment variables
          VAR1: "value1"
          VAR2: "value2"
        timeout: 30.0              # OPTIONAL - Command timeout (seconds)
        shell: true                # OPTIONAL - Run in shell (default: false)

**Note:** Either ``cmd`` OR ``command`` must be specified. Use ``tool`` + ``command`` for specific executables.

Utility Action Parameters
=========================

**IdleAction:**

.. code-block:: yaml

    - idle:
        duration: 3.0              # REQUIRED - Wait time in seconds
        description: "Wait description"  # OPTIONAL but recommended

**ScrollAction:**

.. code-block:: yaml

    - scroll:
        direction: "down"          # REQUIRED - "up", "down", "left", "right"
        amount: 5                  # REQUIRED - Number of scroll steps
        description: "Scroll description"  # OPTIONAL but recommended

**ScreenshotAction:**

.. code-block:: yaml

    - screenshot:
        description: "Screenshot description"  # OPTIONAL but recommended
        x: 100                     # OPTIONAL - Top-left X coordinate
        y: 200                     # OPTIONAL - Top-left Y coordinate
        width: 400                 # OPTIONAL - Width in pixels
        height: 300                # OPTIONAL - Height in pixels

**Note:** If x, y, width, height are omitted, captures full screen.

**SaveTimestampAction:**

.. code-block:: yaml

    - save_timestamp:
        variable: "TIMESTAMP.EVENT"  # REQUIRED - Variable name to store timestamp
        description: "Timestamp description"  # OPTIONAL but recommended

Test Action Parameters
======================

.. code-block:: yaml

    # Inline format
    - test: "test_name"            # REQUIRED - Test name from testset.yml

    # Detailed format
    - test:
        name: "test_name"          # REQUIRED - Test name from testset.yml
        description: "Test description"  # OPTIONAL but recommended

Block Action Parameters
=======================

.. code-block:: yaml

    - block:
        description: "Block description"     # OPTIONAL but recommended
        when:                               # OPTIONAL - Conditional execution
          - exists:                         # Condition type
              text: "Element Text"          # Text to check for
              # OR
              image: "element.png"          # Image to check for
          - not_exists:                     # Multiple conditions (AND logic)
              image: "error.png"
        actions:                            # REQUIRED - List of nested actions
          - click:
              target:
                text: "Button"
          - keyboard:
              keys: "input text"

Target Parameter Details
========================

The ``target`` parameter is used by click, right_click, double_click, drag (source/destination), and goto actions:

.. code-block:: yaml

    target:
      # Choose ONE of these target types:
      image: "filename.png"        # Image file (relative to experiment/img/)
      text: "Visible Text"         # Text visible on screen
      position: [x, y]             # Exact pixel coordinates
      
      # Optional selection strategy:
      strategy:                    # Used when multiple matches found
        # Choose ONE strategy:
        SweepStrategy:
          index: 2                 # Select nth match (1-based)
        BestConfidenceStrategy: {}  # Highest confidence match
        ClosestToStrategy:
          x: 500                   # Select closest to these coordinates
          y: 300
        TopLeftStrategy: {}         # Topmost-leftmost match
        TopRightStrategy: {}        # Topmost-rightmost match
        BottomLeftStrategy: {}      # Bottommost-leftmost match
        BottomRightStrategy: {}     # Bottommost-rightmost match
        LargestStrategy: {}         # Largest bounding box
        SmallestStrategy: {}        # Smallest bounding box

Condition Parameters
====================

Conditions are used in ``when`` clauses for blocks and keyboard actions:

.. code-block:: yaml

    when:
      - exists:                    # Element must be present
          text: "Button Text"      # Check for text
          # OR
          image: "dialog.png"      # Check for image
      - not_exists:                # Element must NOT be present  
          text: "Error Message"
          # OR
          image: "loading.png"

**Note:** Multiple conditions use AND logic - all must be true.

Parameter Data Types
====================

- **String**: Text values in quotes: ``"text value"``
- **Integer**: Whole numbers: ``42``, ``100``
- **Float**: Decimal numbers: ``3.14``, ``1.0`` 
- **Boolean**: ``true`` or ``false``
- **List**: Array of values: ``[1, 2, 3]`` or ``["ctrl", "c"]``
- **Dictionary**: Key-value pairs with indentation:

.. code-block:: yaml

    env:
      KEY1: "value1" 
      KEY2: "value2"

Action Reference Summary
************************

**GUI Actions:**
- ``click`` - Left mouse click (target, description)
- ``right_click`` - Right mouse click (target, description)  
- ``double_click`` - Double mouse click (target, description)
- ``drag`` - Drag and drop (source, destination, description)
- ``goto`` - Move mouse cursor (target, description)

**Keyboard Actions:**
- ``keyboard`` - Type text or key combinations (keys/combination, when, description)

**System Actions:**
- ``command`` - Execute system commands (name, cmd/command, tool, cwd, env, timeout, shell, description)
- ``idle`` - Wait/pause (duration, description)
- ``screenshot`` - Capture screen images (x, y, width, height, description)
- ``save_timestamp`` - Record timestamps (variable, description)

**Test Actions:**
- ``test`` - Execute validation tests (name, description)

**Control Actions:**
- ``block`` - Group actions with optional conditions (actions, when, description)

**Target Types:**
- ``image`` - Match by image template
- ``text`` - Match by text content
- ``position`` - Use exact coordinates

**Selection Strategies:**
- ``SweepStrategy`` - Select nth match
- ``BestConfidenceStrategy`` - Highest confidence match
- ``ClosestToStrategy`` - Closest to coordinates
- ``TopLeftStrategy``, ``TopRightStrategy`` - By corner position
- ``BottomLeftStrategy``, ``BottomRightStrategy`` - By corner position
- ``LargestStrategy``, ``SmallestStrategy`` - By bounding box size

**Condition Types:**
- ``exists`` - Element is present
- ``not_exists`` - Element is not present

This complete reference covers all available playbook features and parameters in ADARE. For specific use cases and examples, refer to the sample experiments and test files in the project.