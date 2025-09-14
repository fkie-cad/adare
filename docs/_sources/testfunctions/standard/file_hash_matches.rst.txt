file_hash_matches
=================

.. role:: status-tested
   :class: status-tested

:Status: :status-tested:`● Tested`
:Category: File System
:Function Name: ``file_hash_matches``

**Tests if file hash matches expected value.**

This test function calculates the cryptographic hash of a file and compares it to an expected value. It's essential for file integrity verification and detecting unauthorized modifications.

Parameters
----------

.. list-table::
   :widths: 20 15 65
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``dst``
     - string
     - **Required.** The file path to hash and test. Supports glob patterns for dynamic path resolution.
   * - ``expected_hash``
     - string
     - **Required.** The expected hash value to compare against (case-insensitive).
   * - ``hash_type``
     - string
     - **Optional.** Hash algorithm to use. Default: "sha256". Options: "md5", "sha1", "sha256", "sha512".

Usage Example
-------------

File Integrity Verification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_config_integrity
       function: file_hash_matches
       parameter:
         dst: "/etc/important_config.conf"
         expected_hash: "a1b2c3d4e5f6789012345678901234567890abcdef"
         hash_type: "sha256"
       description: "Verify configuration file has not been modified"

Download Verification
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   tests:
     - name: verify_download_integrity
       function: file_hash_matches
       parameter:
         dst: "/tmp/downloaded_file.zip"
         expected_hash: "d41d8cd98f00b204e9800998ecf8427e"
         hash_type: "md5"
       description: "Verify downloaded file matches expected checksum"

Generated File Validation
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   actions:
     - click:
         target:
           text: "Generate Report"

   tests:
     - name: verify_report_content
       function: file_hash_matches
       parameter:
         dst: "/home/user/reports/monthly_report.pdf"
         expected_hash: "2fd4e1c67a2d28fced849ee1bb76e7391b93eb12"
         hash_type: "sha1"
       description: "Verify generated report matches expected content"

Common Use Cases
----------------

**File Integrity Verification**
  Ensure critical files haven't been modified or corrupted

**Download Verification**
  Verify downloaded files match their published checksums

**Backup Validation**
  Confirm backup files are identical to original files

**Generated Content Verification**
  Ensure automated processes produce consistent, expected output

**Security Monitoring**
  Detect unauthorized modifications to important system files

**Version Control**
  Verify file versions match expected content

**Forensic Analysis**
  Confirm file authenticity and detect tampering

Supported Hash Algorithms
--------------------------

.. list-table::
   :widths: 15 25 60
   :header-rows: 1

   * - Algorithm
     - Hash Length
     - Use Case
   * - ``md5``
     - 32 characters (128 bit)
     - Fast checksums, non-cryptographic use
   * - ``sha1``
     - 40 characters (160 bit)
     - Legacy systems, git commits
   * - ``sha256``
     - 64 characters (256 bit)
     - **Recommended** - secure, widely supported
   * - ``sha512``
     - 128 characters (512 bit)
     - High security requirements

Hash Format
-----------

**Case Insensitive**
  Hash values are compared case-insensitively, so both uppercase and lowercase are accepted

**Hexadecimal Only**
  Hash values must be provided in hexadecimal format (0-9, a-f, A-F)

**No Prefix Required**
  Don't include "0x" or other prefixes - just the hex digits

Performance Considerations
--------------------------

**Large Files**
  The function reads files in 4KB chunks to handle large files efficiently without excessive memory usage

**Hash Algorithm Speed**
  - MD5: Fastest, but not cryptographically secure
  - SHA1: Fast, but deprecated for security
  - SHA256: **Recommended balance** of speed and security
  - SHA512: Slower but more secure

Return Values
-------------

**Success**
  Returns success when the calculated hash matches the expected hash

**Failure**
  Returns failure when:

  - The calculated hash doesn't match the expected hash
  - Shows both expected and actual hash values for comparison

**Execution Error**
  Returns execution error when:

  - The file cannot be found or read
  - Invalid hash algorithm specified
  - Permission denied reading the file
  - Path resolution fails due to glob pattern ambiguity

Example Results
---------------

.. code-block:: yaml

   # Success case
   result: success
   details:
     - "SHA256 hash matches: a1b2c3d4e5f6789012345678901234567890abcdef"

   # Failure case
   result: failed
   details:
     - "SHA256 hash mismatch. Expected: a1b2c3d4e5f6789012345678901234567890abcdef, Got: f1e2d3c4b5a6987012345678901234567890fedcba"

   # Execution error case
   result: execution_error
   error: "ValueError: Unsupported hash type: blake2b"
   context: "Hash calculation error"

