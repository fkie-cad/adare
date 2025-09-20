********************************************************
Create your own testfunction collection (in development)
********************************************************

This guide explains how to create custom test functions for ADARE to extend its testing capabilities beyond the built-in test function collections.

Architecture Overview
======================

Test Function Structure
-----------------------

Every test function consists of:

1. **Parameter Class**: Defines input fields using attrs
2. **Test Class**: Inherits from BasicTest, implements the test logic
3. **Class Variables**: ``testname`` and ``testdescription`` for identification
4. **test() Method**: Core logic returning a TestResult

.. code-block:: python

   import attrs
   from typing import ClassVar, Optional

   from adarelib.testset.basictest import BasicTest, Parameter
   from adarelib.event.event import TestResult

   @attrs.define
   class MyTestParameter(Parameter):
       input_field: str
       optional_field: Optional[int] = None

   @attrs.define
   class MyTest(BasicTest):
       testname: ClassVar[str] = 'my_test'
       testdescription: ClassVar[str] = 'Description of what this test does'

       name: str
       parameter: MyTestParameter
       description: Optional[str] = ''
       variable_metadata: Optional[dict] = None

       def test(self):
           # Implementation here
           return TestResult.success()

Core Concepts
-------------

**BasicTest Class**
  Base class providing file resolution, variable handling, and placeholder comparison

**Parameter Classes**
  Attrs-decorated classes defining input parameters for test functions

**TestResult System**
  Standardized result objects: ``success()``, ``failed()``, ``execution_error()``

**Module Organization**
  Test functions grouped in collections (standard, json, xml, windows, etc.)

Step-by-Step Development
========================

1. Create the Module Structure
------------------------------

Create a new directory anywhere on your system for your test collection. You can organize it as follows:

.. code-block:: bash

   mkdir /path/to/your/testfunctions/mycollection
   touch /path/to/your/testfunctions/mycollection/mycollection.py
   touch /path/to/your/testfunctions/mycollection/requirements.txt

Then load your custom test functions using:

.. code-block:: bash

   adare testfunction load /path/to/your/testfunctions

2. Define Parameter Classes
---------------------------

Start with simple parameter definitions using attrs:

.. code-block:: python

   # /path/to/your/testfunctions/mycollection/mycollection.py
   import attrs
   from pathlib import Path
   from typing import ClassVar, Optional

   from adarelib.testset.basictest import BasicTest, Parameter
   from adarelib.event.event import TestResult

   @attrs.define
   class FileContentContainsWordParameter(Parameter):
       dst: str               # File path (supports glob patterns)
       word: str             # Word to search for
       case_sensitive: Optional[bool] = True

3. Implement the Test Class
---------------------------

Create the test class with proper error handling:

.. code-block:: python

   @attrs.define
   class FileContentContainsWord(BasicTest):
       testname: ClassVar[str] = 'file_content_contains_word'
       testdescription: ClassVar[str] = 'tests if file content contains specified word'

       name: str
       parameter: FileContentContainsWordParameter
       description: Optional[str] = ''
       variable_metadata: Optional[dict] = None

       def test(self):
           try:
               # Use resolve_globfilepath for file resolution
               dst, status = self.resolve_globfilepath(self.parameter.dst)
               if not dst:
                   return TestResult.error([f'File {self.parameter.dst} not found ({status})'])

               # Read file with proper error handling
               try:
                   with open(dst, 'r', encoding='utf-8') as f:
                       content = f.read()
               except FileNotFoundError:
                   return TestResult.failed([f'File {dst} does not exist'])
               except (PermissionError, OSError) as e:
                   return TestResult.execution_error(e, f"Cannot read file {dst}")

               # Perform the test logic
               word = self.parameter.word
               if not self.parameter.case_sensitive:
                   content = content.lower()
                   word = word.lower()

               if word in content:
                   return TestResult.success([f'Word "{self.parameter.word}" found in file'])
               else:
                   return TestResult.failed([f'Word "{self.parameter.word}" not found in file'])

           except Exception as e:
               return TestResult.execution_error(e, "Unexpected error in word search test")

Core BasicTest Methods
======================

File Resolution
---------------

Use ``resolve_globfilepath()`` for all file operations:

.. code-block:: python

   # Handles both exact paths and glob patterns
   dst, status = self.resolve_globfilepath(self.parameter.dst)
   if not dst:
       return TestResult.error([f'File resolution failed: {status}'])

Variable and Placeholder Handling
---------------------------------

For advanced template support with variables:

.. code-block:: python

   expected_content = self.parameter.expected_content

   # Check if content has placeholder variables
   if self.has_placeholders(expected_content):
       # Use placeholder comparison system
       success, message = self._handle_placeholders_comparison(actual_content, expected_content)
       if success:
           return TestResult.success([message])
       else:
           return TestResult.failed([message])
   else:
       # Direct comparison
       if actual_content == expected_content:
           return TestResult.success(['Content matches'])
       else:
           return TestResult.failed(['Content does not match'])

Advanced Features
=================

Timestamp Tolerance
-------------------

For timestamp validation with tolerance ranges:

.. code-block:: python

   # In your parameter class
   @attrs.define
   class TimestampTestParameter(Parameter):
       dst: str
       expected_timestamp: str
       tolerance_seconds: Optional[int] = 5

   # In your test method
   if self.has_placeholders(expected_timestamp):
       # Extract placeholder name and use tolerance comparison
       placeholders = self.get_placeholders(expected_timestamp)
       if len(placeholders) == 1:
           success, message = self.compare_with_placeholder(placeholders[0], actual_timestamp)
           return TestResult.success([message]) if success else TestResult.failed([message])

Regex Pattern Matching
-----------------------

For regex-based validation:

.. code-block:: python

   import re

   def _validate_pattern(self, actual_value, pattern):
       try:
           compiled_pattern = re.compile(pattern)
           if compiled_pattern.search(actual_value):
               return True, f'Value matches pattern: {pattern}'
           else:
               return False, f'Value does not match pattern: {pattern}'
       except re.error as e:
           return False, f'Invalid regex pattern: {pattern} - {e}'

Error Handling Patterns
=======================

Standard Error Types
--------------------

Use consistent error handling for common scenarios:

.. code-block:: python

   try:
       # File operations
       with open(file_path, 'r') as f:
           data = f.read()
   except FileNotFoundError:
       return TestResult.failed([f'File {file_path} does not exist'])
   except (PermissionError, OSError) as e:
       return TestResult.execution_error(e, f"Cannot access file {file_path}")
   except UnicodeDecodeError as e:
       return TestResult.execution_error(e, f"Cannot decode file {file_path}")

Test Result Guidelines
----------------------

- **TestResult.success()**: Test passed, condition met
- **TestResult.failed()**: Test ran but condition not met (expected behavior)
- **TestResult.execution_error()**: Test couldn't run due to errors (unexpected)

.. code-block:: python

   # Success with details
   return TestResult.success([f'Found {count} matching entries'])

   # Failure with explanation
   return TestResult.failed([f'Expected value {expected}, got {actual}'])

   # Error with context
   return TestResult.execution_error(exception, "Database connection failed")

Module Organization
===================

Directory Structure
-------------------

Organize your test functions in logical collections anywhere on your system:

.. code-block::

   /path/to/your/testfunctions/
   ├── mycollection/
   │   ├── mycollection.py      # Main test functions
   │   └── requirements.txt     # Python dependencies
   └── anothercollection/
       ├── anothercollection.py
       └── requirements.txt

Dependencies
------------

List any additional Python packages in ``requirements.txt``:

.. code-block:: text

   # requirements.txt
   lxml>=4.9.0
   requests>=2.28.0

Loading Custom Test Functions
-----------------------------

Load your custom test functions into ADARE:

.. code-block:: bash

   # Load from any directory
   adare testfunction load /path/to/your/testfunctions

   # Verify loaded functions
   adare testfunction list

Real-World Example
==================

Complete Custom Test Function
-----------------------------

Here's a complete example testing JSON API responses:

.. code-block:: python

   # /path/to/your/testfunctions/api/api.py
   import attrs
   import requests
   import json
   from typing import ClassVar, Optional

   from adarelib.testset.basictest import BasicTest, Parameter
   from adarelib.event.event import TestResult

   @attrs.define
   class ApiResponseParameter(Parameter):
       url: str
       expected_status: int = 200
       expected_json_key: Optional[str] = None
       expected_json_value: Optional[str] = None
       timeout_seconds: Optional[int] = 30

   @attrs.define
   class ApiResponse(BasicTest):
       testname: ClassVar[str] = 'api_response'
       testdescription: ClassVar[str] = 'tests API endpoint response and JSON content'

       name: str
       parameter: ApiResponseParameter
       description: Optional[str] = ''
       variable_metadata: Optional[dict] = None

       def test(self):
           try:
               url = self.parameter.url
               expected_status = self.parameter.expected_status
               timeout = self.parameter.timeout_seconds

               # Make HTTP request
               try:
                   response = requests.get(url, timeout=timeout)
               except requests.RequestException as e:
                   return TestResult.execution_error(e, f"HTTP request failed for {url}")

               # Check status code
               if response.status_code != expected_status:
                   return TestResult.failed([
                       f'HTTP status mismatch. Expected: {expected_status}, Got: {response.status_code}'
                   ])

               # Check JSON content if specified
               if self.parameter.expected_json_key:
                   try:
                       json_data = response.json()
                   except json.JSONDecodeError as e:
                       return TestResult.execution_error(e, "Response is not valid JSON")

                   if self.parameter.expected_json_key not in json_data:
                       return TestResult.failed([
                           f'JSON key "{self.parameter.expected_json_key}" not found'
                       ])

                   if self.parameter.expected_json_value:
                       actual_value = json_data[self.parameter.expected_json_key]
                       expected_value = self.parameter.expected_json_value

                       # Support placeholder comparison for dynamic values
                       if self.has_placeholders(expected_value):
                           success, message = self._handle_placeholders_comparison(
                               str(actual_value), expected_value
                           )
                           if not success:
                               return TestResult.failed([f'JSON value comparison failed: {message}'])
                       else:
                           if str(actual_value) != expected_value:
                               return TestResult.failed([
                                   f'JSON value mismatch. Expected: {expected_value}, Got: {actual_value}'
                               ])

               return TestResult.success([
                   f'API response valid: HTTP {response.status_code}',
                   f'Response size: {len(response.content)} bytes'
               ])

           except Exception as e:
               return TestResult.execution_error(e, "Unexpected error in API response test")

Usage in Playbooks
------------------

Use your custom test function in experiment playbooks:

.. code-block:: yaml

   # experiment/playbook.yml
   tests:
     - name: check_api_status
       function: api.api_response
       parameter:
         url: "https://api.example.com/status"
         expected_status: 200
         expected_json_key: "status"
         expected_json_value: "healthy"
         timeout_seconds: 10

Best Practices
==============

Performance Considerations
--------------------------

- **Minimize file I/O**: Cache file contents when testing multiple aspects
- **Efficient patterns**: Use appropriate data structures for large datasets
- **Resource cleanup**: Close files and connections properly
- **Timeout handling**: Set reasonable timeouts for network operations

Logging Guidelines
------------------

Use structured logging for debugging:

.. code-block:: python

   import logging
   log = logging.getLogger(__name__)

   def test(self):
       log.debug(f'Starting test {self.name} with parameter: {self.parameter.dst}')

       # Test implementation
       result = self._perform_test()

       log.info(f'Test {self.name} completed with status: {result.status}')
       return result

Cross-Platform Considerations
-----------------------------

Handle platform differences gracefully:

.. code-block:: python

   import platform

   def test(self):
       if platform.system() == 'Windows':
           # Windows-specific logic
           return self._test_windows()
       elif platform.system() == 'Linux':
           # Linux-specific logic
           return self._test_linux()
       else:
           return TestResult.execution_error(
               None, f"Unsupported platform: {platform.system()}"
           )

Testing Your Test Functions
===========================

Unit Testing
------------

Create unit tests for your test functions:

.. code-block:: python

   # tests/test_mycollection.py
   import unittest
   from adarelib.testset.basictest import TestResult
   from mycollection.mycollection import (
       FileContentContainsWord, FileContentContainsWordParameter
   )

   class TestFileContentContainsWord(unittest.TestCase):
       def test_word_found(self):
           # Create test instance
           test_instance = FileContentContainsWord(
               name="test_word_search",
               parameter=FileContentContainsWordParameter(
                   dst="/path/to/test/file.txt",
                   word="hello",
                   case_sensitive=True
               )
           )

           # Mock file content and test
           # ... test implementation

Integration Testing
--------------------

Test with actual playbooks in controlled environments:

.. code-block:: yaml

   tests:
     - name: test_custom_function
       function: mycollection.file_content_contains_word
       parameter:
         dst: "/tmp/test_file.txt"
         word: "test_content"
         case_sensitive: false

Common Pitfalls
===============

- **Forgetting glob resolution**: Always use ``resolve_globfilepath()`` for file paths
- **Inconsistent error handling**: Use the three-tier result system consistently
- **Missing variable support**: Consider placeholder integration for dynamic content
- **Platform assumptions**: Test on target operating systems
- **Resource leaks**: Properly close files and network connections
- **Overly complex tests**: Keep test functions focused and single-purpose

Sharing Your Test Functions
===========================

Once you've created useful test functions that could benefit the ADARE community, consider sharing them!

Create a pull request to the `ADARE Web repository <https://github.com/adareweb/adareweb>`_ to make your test functions available to other users. This helps build a comprehensive library of test functions for various forensic analysis scenarios.

When submitting your test functions:

- Include comprehensive documentation
- Provide example usage in playbooks
- Test across multiple platforms if applicable
- Follow the coding standards outlined in this guide

This comprehensive guide provides the foundation for creating robust, maintainable test functions that integrate seamlessly with the ADARE framework. Start with simple examples and gradually incorporate advanced features as needed.