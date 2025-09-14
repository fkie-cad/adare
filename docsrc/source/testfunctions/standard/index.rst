Standard 
================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Functions: 11
:Category: File System Operations

The **Standard** testset provides fundamental file system testing capabilities for ADARE experiments. This testset focuses on file and directory operations, content validation, permissions, and metadata verification.

Overview
--------

The Standard testset is the core foundation for ADARE testing, providing essential functions for validating file system state and content. 
It includes functions to check for the existence of files and directories, validate file contents using various matching strategies, verify file metadata such as timestamps and permissions, and ensure file integrity through hashing.

Test Functions
--------------

.. csv-table::
   :file: ../../_static/tables/testfunctions_standard.csv
   :widths: 20, 10, 40, 30
   :header-rows: 1
   :class: sdtable
   :name: standard-functions-table



.. toctree::
   :maxdepth: 1
   :hidden:

   file_exists
   file_does_not_exist
   dir_exists
   dir_does_not_exist
   file_content_equals
   file_content_contains
   file_content_matches_regex
   dir_content
   file_hash_matches
   file_timestamps
   file_permissions

