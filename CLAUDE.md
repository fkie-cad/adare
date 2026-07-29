# ADARE (Automated Desktop Analysis framework for Reproducible Experiments)

Framework for detecting forensic artifact changes across OS/software versions using automated GUI actions in VMs.

## Architecture
- **adare/** – Host client: manages projects, VMs, experiments
- **adarevm/** – Guest agent: runs inside VM, executes playbooks via WebSocket
- **adare-cv-server/** – External GUI automation server (screenshot analysis with staged detection)
- **adarelib/** – Shared utilities & test functions
- **docsrc/** – Documentation

## CV Server: Multi-Method Aggregated Detection Pipeline

**Goal**: Maximize detection robustness by running all applicable methods and aggregating results, preventing false negatives while maintaining precision.

**Architecture** (6-stage parallel aggregated pipeline):
1. **Stage 0**: Canny edge-based multi-scale template matching (0.85 threshold, 0.1-10.0x scale)
   - Lighting-invariant detection using structural outlines (focuses on shape, not color/intensity)
   - Robust to theme changes (light/dark mode), color variations, tint differences
   - Auto-threshold Canny edge detection (median * 0.66/1.33)
   - Edge dilation (1 iteration) for sub-pixel shift tolerance
   - Same scale range as Stage 1 (0.1-10.0x, 28 scales: fine 0.1 steps below 1.0x, coarse 0.5 steps above)
   - Skips matching if edges too sparse (<5% density)
   - Early termination on high confidence (>0.95)
   - **Returns ALL matches** above fallback threshold (0.75) with NMS deduplication
   - **Weight: 1.0** (highest priority - theme invariant)

2. **Stage 1**: Multi-scale template matching (0.9 threshold, 0.1-10.0x scale)
   - Extended range: 0.1x to 10.0x (28 scales: fine 0.1 steps below 1.0x, coarse 0.5 steps above)
   - Minimum 10x10 pixel constraint prevents sub-10px misdetections
   - Early termination optimization (stops when similarity > 0.95)
   - Acts as precision gate to prevent ORB false positives on text edges
   - **Adaptive mask validation**: Combines absolute minimum (25px) with ratio-based threshold (10% opaque)
   - **Size-invariant variance**: Normalizes by total area (w×h) to enable cross-scale comparison
   - **Degenerate mask detection**: Rejects masks with <5% opaque pixels (safety net)
   - **Returns ALL matches** above fallback threshold (0.8) with NMS deduplication
   - **Weight: 0.95** (high - pixel exact matching)

3. **Stage 2**: Laplacian variance gatekeeper (threshold: 0.5)
   - Analyzes icon texture complexity to determine ORB suitability
   - Flat icons (variance <0.5) skip ORB to avoid matching text edges
   - Textured icons (variance >0.5) proceed to ORB

4. **Stage 3**: ORB feature matching (textured icons only)
   - Handles scaled/rotated complex icons (~30-80ms)
   - Only runs if Stage 2 approves (prevents false positives on flat icons)
   - **Weight: 0.85** (good but prone to text false positives)

5. **Stage 4**: SIFT fallback
   - Most robust for gradient/complex icons (~80-120ms)
   - Match counts normalized to 0.0-1.0 (20+ matches = 1.0 confidence)
   - **Weight: 0.90** (robust for complex icons)

6. **Stage 5**: Template matching at 0.75 threshold (catch-all)
   - Final attempt with relaxed threshold (~10-20ms)
   - **Weight: 0.80** (catch-all with relaxed threshold)

**Aggregation Strategy**:
- **All methods run** (no early exits except ORB gatekeeper at Stage 2)
- **Method weighting**: Canny (1.0) > Multi-scale (0.95) > SIFT (0.90) > ORB (0.85) > Template (0.80)
- **Similarity normalization**: SIFT match counts → 0.0-1.0 range (count/20, capped at 1.0)
- **Weighted similarity**: raw_similarity × method_weight
- **Global NMS**: IoU threshold 0.5, removes cross-method duplicates using weighted similarities
- **Method provenance**: Track contributing methods for each final location
- **Result format**: Returns locations, similarities, primary method, and contributing methods list

**Key Benefits**:
- ✅ **No false negatives from early exit**: All methods run, aggregate results
- ✅ **Method diversity**: Multiple detection principles increase robustness
- ✅ **Forensic auditability**: Track which methods detected each icon
- ✅ **Confidence ranking**: Weighted similarities prioritize reliable detections
- ✅ **Precision maintained**: Global NMS prevents duplicate reporting
- ✅ **Lighting/theme invariant**: Canny edge detection ignores color/intensity variations
- ✅ **Extreme scale handling**: 10% to 1000% of original size

**Performance**:
- **Total pipeline**: ~200ms-1350ms (all applicable methods, deterministic)
- **Acceptable for forensic analysis**: Accuracy prioritized over speed
- **Stage 0** (Canny edge): ~50-560ms (28 scales, early termination on >0.95 match)
- **Stage 1** (Multi-scale template): ~20-560ms (28 scales, early termination on >0.95 match)
- **Stage 3** (ORB): ~30-80ms (textured icons only)
- **Stage 4** (SIFT): ~80-120ms
- **Stage 5** (Template fallback): ~10-20ms

**Implementation** (`adare-cv-server/`):
- `constants.py` - Detection constants, method weights, NMS threshold
- `image_processing.py` - `DetectionMatch` dataclass, `IconComplexityAnalyzer`, `non_maximum_suppression()`
- `feature_matching.py` - All matchers return scale/size metadata in `FeatureMatchingResult`
- `server.py` - `find_icon()` function with aggregation pipeline, helper functions:
  - `_normalize_similarity()` - SIFT match count → 0.0-1.0
  - `_get_method_weight()` - Lookup method weights
  - `_estimate_match_size()` - Compute bounding box from scale
  - `_aggregate_matches()` - Global NMS + method grouping

## Playbook Execution Model
**Database-driven approach** for scalability and forensic auditability:

### On Experiment Load (`adare experiment load`)
1. Parse playbook YAML file
2. Store **original YAML content** in `Playbook.original_yaml_content` (for variables/tests)
3. Serialize actions to `PlaybookItem` database models (JSON format)
4. Hash validation for integrity enforcement

### On Experiment Execution (`adare experiment run`)
1. **Load actions from PlaybookItem database models** (no YAML parsing)
2. Reconstruct action objects via deserialization
3. Parse variables/tests from stored YAML (complex structures kept as YAML)
4. Execute using reconstructed Playbook object

### Benefits
- ✅ No YAML parsing overhead during execution
- ✅ Database-level caching and query optimization
- ✅ Complete audit trail with FK relationships to ActionExecution
- ✅ Integrity validation prevents tampering
- ✅ Scalable for analytics and web interfaces

## Database Schema Migrations

`create_all()` never ALTERs existing tables, so adding a column to an existing model needs a
migration or installs break with `no such column: ...`. `database/migrations/runner.py` applies
pending migrations automatically after every `create_all` (ledger table `schema_migration`);
`adare db migrate` / `db status` are the explicit commands.

Adding one: idempotent `upgrade(conn)` in `database/migrations/<name>.py` (never open a DB API
inside it — that recurses), then append a `Migration(...)` to `MIGRATIONS` — append only, never
reorder. Full recipe: `docsrc/source/architecture/database-migrations.rst`.

## Test Execution Performance

### Testfunction Caching (2026-02-06)
**Problem**: Testfunction discovery ran on every test execution, taking ~32 seconds to load/compile all Python modules.

**Solution**: Instance-level caching in `AdareVMServer._testfunction_cache`
- First test pays 32s discovery cost (one-time per VM session)
- Subsequent tests have zero discovery overhead (instant cache lookup)
- Cache persists for VM lifetime (requires restart to pick up testfunction changes)

**Impact**: Experiments with 20+ tests save ~10 minutes of discovery overhead

### Test Timeouts
Tests support configurable timeouts via the `timeout` field:

**Default**: 120 seconds (2 minutes) - conservative with testfunction caching
- Most cached tests complete in <5 seconds
- Complex operations (Excel parsing, file operations) may need 30-60 seconds
- Default provides safety margin while catching truly hung operations

**YAML Configuration**:
```yaml
tests:
  - name: test_simple_file
    function: standard.file_exists
    # Uses default 120s timeout
    parameter:
      dst: /path/to/file

  - name: test_large_excel
    function: excel.validate_columns
    timeout: 300  # Override for very large files (5 minutes)
    parameter:
      dst: /path/to/huge.xlsx
```

**Timeout Flow**:
1. Action timeout (playbook YAML) overrides Test timeout (testfunction default)
2. WebSocket adds 10-second buffer for communication overhead
3. VM executes test within timeout limit

## Testing
- Manual only (experiment commands, interactive mode) - so never built or perform tests

## Guidelines
- Prefix temp logs with `CLAUDE:`
- Keep files <1000 lines
- Update docs when adding features
- Review flow & fix errors after changes
- never catch generic exception (with except Exception) - use more specific Excpetion that are expected instead