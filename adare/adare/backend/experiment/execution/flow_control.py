"""
Executors for control flow actions (block, loop, wait_until, pause).

These actions control the flow of playbook execution with conditionals,
loops, waits, and interactive pauses.
"""

import logging
import time
import asyncio
import functools
from typing import Optional

from adare.types.playbook import (
    BlockAction, LoopAction, WaitUntilAction, PauseAction,
    StopAction, ContinueAction, VariableCondition
)
from adare.backend.events.emitters import emit_action
from .base import ActionResult
from adare.helperfunctions.image import calculate_pixel_change

log = logging.getLogger(__name__)

MIN_PIXEL_POLL_INTERVAL = 0.5



class FlowControlExecutor:
    """Handles execution of control flow actions (block, loop, wait_until, pause)."""

    def __init__(self, websocket_client, target_resolution_executor, condition_checker,
                 experiment_run_id: Optional[str] = None, execution_context: dict = None,
                 flow_console = None):
        """
        Initialize flow control executor.

        Args:
            websocket_client: Connected WebSocket client to adarevm
            target_resolution_executor: Target resolution executor for screenshots/targets
            condition_checker: Condition checker for evaluating conditions
            experiment_run_id: Experiment run ID for event emission
            execution_context: Execution context for variable resolution
            flow_console: Flow console for interactive display and input
        """
        self.client = websocket_client
        self.target_resolution = target_resolution_executor
        self.condition_checker = condition_checker
        self.experiment_run_id = experiment_run_id
        self.execution_context = execution_context if execution_context is not None else {}
        self.flow_console = flow_console

    async def execute_block(self, action: BlockAction, parent_event_id: str = None,
                           event_emitter = None, variable_resolver = None,
                           action_executor = None) -> ActionResult:
        """Execute conditional block action with MCP-based condition checking."""
        # Check conditions if present
        screenshot_path = None  # Track screenshot path for result data
        if hasattr(action, 'when') and action.when:
            try:
                # Get screenshot for condition checking
                screenshot_base64, screenshot_path = await self.target_resolution.get_current_screenshot_with_path()
                conditions_met = await self.condition_checker.check_conditions(action.when, screenshot_base64)
                if not conditions_met:
                    # Include screenshot path in skipped result
                    data = {}
                    if screenshot_path:
                        data['screenshot_path'] = screenshot_path
                    return ActionResult(
                        success=True,
                        message="Block conditions not met, skipping",
                        data=data if data else None
                    )
            except Exception as e:
                log.error(f"Error checking block conditions: {e}")
                return ActionResult(
                    success=False,
                    message=f"Condition check failed: {str(e)}"
                )

        # Use the block's parent_event_id as parent context for sub-actions
        block_parent_event_id = parent_event_id

        # Execute all actions in block
        results = []
        for i, block_action in enumerate(action.actions):
            # Create sub-action ID
            sub_action_id = f"block_sub_{i}_{int(time.time()*1000)}"

            # Emit sub-action start event
            if self.experiment_run_id and event_emitter:
                try:
                    sub_start_event = event_emitter.create_action_start_event(block_action, i, sub_action_id, parent_event_id=block_parent_event_id)
                    emit_action(self.experiment_run_id, sub_start_event, sub_action_id)
                except Exception as e:
                    log.error(f"Failed to emit sub-action start event: {e}")

            # Execute the sub-action with variable resolution
            start_time = time.time()
            result = await action_executor.execute_action(block_action, parent_event_id=block_parent_event_id, event_emitter=event_emitter, variable_resolver=variable_resolver)
            execution_time = time.time() - start_time
            result.execution_time = execution_time

            # Emit sub-action complete event
            if self.experiment_run_id and event_emitter:
                try:
                    sub_complete_event = event_emitter.create_action_complete_event(block_action, i, sub_action_id, result, parent_event_id=block_parent_event_id)
                    emit_action(self.experiment_run_id, sub_complete_event, sub_action_id)
                except Exception as e:
                    log.error(f"Failed to emit sub-action complete event: {e}")

            results.append(result)

            # Check for continue signal (skip remaining actions in block)
            if result.success and result.data and result.data.get('should_continue', False):
                log.info(f"Continue triggered - skipping remaining actions in block")
                break  # Break out of block action loop

            if not result.success:
                # Handle testset-related errors specifically
                if "No testset loaded" in result.message:
                    return ActionResult(
                        success=False,
                        message=f"Block action failed: {result.message}"
                    )
                return ActionResult(
                    success=False,
                    message=f"Block action failed: {result.message}"
                )

        # Include screenshot path in final result data
        data = {'actions_executed': len(results)}
        if screenshot_path:
            data['screenshot_path'] = screenshot_path

        return ActionResult(
            success=True,
            message=f"Block executed successfully ({len(results)} actions)",
            data=data
        )

    async def execute_loop(self, action: LoopAction, parent_event_id: str = None,
                          event_emitter = None, variable_resolver = None,
                          action_executor = None) -> ActionResult:
        """Execute loop action - iterate N times or over a list.

        Automatic variables available in loop body:
        - index: Current iteration (0-based)
        - total: Total number of iterations
        - item: Current item (list iteration only, or custom via item_var)
        """
        try:
            # Determine iteration count and items
            if action.times is not None:
                # Simple N-times iteration
                iteration_count = action.times
                items = None
                log.info(f"Starting simple loop: {iteration_count} iterations")
            else:
                # List iteration - resolve items variable
                items_value = action.items
                if isinstance(items_value, str) and '{{' in items_value:
                    # Resolve variable reference
                    resolved = variable_resolver.replace_variables(items_value, self.execution_context)

                    # Handle different resolved types
                    if isinstance(resolved, list):
                        items = resolved
                    elif isinstance(resolved, str):
                        # Try parsing as JSON list
                        import json
                        try:
                            items = json.loads(resolved)
                            if not isinstance(items, list):
                                items = [items]
                        except json.JSONDecodeError:
                            # Treat as single item
                            items = [resolved]
                    else:
                        items = [resolved]
                elif isinstance(items_value, list):
                    items = items_value
                else:
                    items = [items_value]

                iteration_count = len(items)
                log.info(f"Starting list loop: {iteration_count} items")

            # Determine item variable name
            item_var_name = action.item_var if action.item_var else 'item'

            # Execute loop iterations
            results = []
            for i in range(iteration_count):
                # Create loop-specific execution context with automatic variables
                loop_context = self.execution_context.copy()
                loop_context['index'] = i           # 0-based index
                loop_context['total'] = iteration_count

                # Add item variable for list iteration
                if items is not None:
                    loop_context[item_var_name] = items[i]
                    log.debug(f"Loop iteration {i}/{iteration_count}: {item_var_name}={items[i]}")
                else:
                    log.debug(f"Loop iteration {i}/{iteration_count}")

                # Set execution context to loop context for entire iteration
                # This ensures loop variables are scoped to the iteration and captured
                # variables persist across actions within the same iteration
                saved_flow_context = self.execution_context
                saved_action_context = action_executor.execution_context
                saved_simple_actions_context = action_executor.simple_actions.execution_context
                self.execution_context = loop_context
                action_executor.execution_context = loop_context
                action_executor.simple_actions.execution_context = loop_context

                try:
                    # Execute each action in the loop body
                    for j, loop_action in enumerate(action.actions):
                        # Create sub-action ID
                        sub_action_id = f"loop_{i}_action_{j}_{int(time.time()*1000)}"

                        # Resolve variables in the loop action with loop context
                        resolved_loop_action = variable_resolver.resolve_action_variables(
                            loop_action, loop_context
                        )

                        # Emit sub-action start event (use resolved action for display)
                        if self.experiment_run_id and event_emitter:
                            try:
                                sub_start_event = event_emitter.create_action_start_event(
                                    resolved_loop_action, j, sub_action_id, parent_event_id=parent_event_id
                                )
                                emit_action(self.experiment_run_id, sub_start_event, sub_action_id)
                            except Exception as e:
                                log.error(f"Failed to emit loop sub-action start event: {e}")

                        # Execute the sub-action
                        start_time = time.time()
                        result = await action_executor.execute_action(
                            loop_action,  # Pass original, will be re-resolved in execute_action
                            parent_event_id=parent_event_id,
                            event_emitter=event_emitter,
                            variable_resolver=variable_resolver
                        )
                        execution_time = time.time() - start_time
                        result.execution_time = execution_time

                        # Emit sub-action complete event
                        if self.experiment_run_id and event_emitter:
                            try:
                                sub_complete_event = event_emitter.create_action_complete_event(
                                    resolved_loop_action, j, sub_action_id, result,
                                    parent_event_id=parent_event_id
                                )
                                emit_action(self.experiment_run_id, sub_complete_event, sub_action_id)
                            except Exception as e:
                                log.error(f"Failed to emit loop sub-action complete event: {e}")

                        results.append(result)

                        # Check for continue signal (skip remaining actions in current iteration)
                        if result.success and result.data and result.data.get('should_continue', False):
                            log.info(f"Continue triggered - skipping remaining actions in iteration {i}")
                            break  # Break out of inner action loop, continue to next iteration

                        # Stop loop on failure
                        if not result.success:
                            log.error(f"Loop failed at iteration {i}/{iteration_count}, action {j}")
                            return ActionResult(
                                success=False,
                                message=f"Loop failed at iteration {i}, action {j}: {result.message}",
                                data={'completed_iterations': i, 'total_iterations': iteration_count}
                            )

                finally:
                    # Merge new variables from loop iteration back to parent contexts
                    # This preserves variables created by save_timestamp, command capture, etc.
                    # while ensuring loop control variables (index, total, item) don't leak
                    loop_control_vars = {'index', 'total', action.item_var if action.item_var else 'item'}
                    new_vars = {k: v for k, v in loop_context.items()
                                if k not in loop_control_vars and k not in saved_flow_context}

                    if new_vars:
                        log.debug(f"Merging {len(new_vars)} new variables from loop iteration {i}: {list(new_vars.keys())}")
                        saved_flow_context.update(new_vars)
                        saved_action_context.update(new_vars)
                        saved_simple_actions_context.update(new_vars)

                    # Restore contexts with merged variables
                    self.execution_context = saved_flow_context
                    action_executor.execution_context = saved_action_context
                    action_executor.simple_actions.execution_context = saved_simple_actions_context

            log.info(f"Loop completed successfully: {iteration_count} iterations, {len(results)} total actions")
            return ActionResult(
                success=True,
                message=f"Loop completed ({iteration_count} iterations, {len(results)} actions)",
                data={'iterations': iteration_count, 'actions_executed': len(results)}
            )

        except Exception as e:
            log.error(f"Loop action failed: {e}", exc_info=True)
            return ActionResult(success=False, message=str(e))

    async def execute_wait_until(self, action: WaitUntilAction, parent_event_id: str = None,
                                event_emitter = None) -> ActionResult:
        """Execute wait until action - wait for condition to be satisfied with timeout and check interval."""
        try:
            log.info(f"Starting wait until action with timeout={action.timeout}s, check_interval={action.check_interval}s, initial_delay={action.initial_delay}s")

            check_count = 0
            last_screenshot_path = None  # Track last screenshot for timeout result
            last_screenshot_base64 = None  # Track previous screenshot for pixel change check

            # Apply initial delay if specified to let UI stabilize (doesn't count towards timeout)
            if action.initial_delay > 0:
                log.info(f"Applying initial delay of {action.initial_delay}s to let UI stabilize")
                await asyncio.sleep(action.initial_delay)

            # Start timeout counting AFTER initial delay
            start_time = time.time()

            # Always do at least one check, then continue until timeout
            pixel_constraint_satisfied = False
            while True:
                check_count += 1
                log.debug(f"Wait until check #{check_count} (elapsed: {time.time() - start_time:.1f}s)")

                # Take screenshot for condition evaluation
                screenshot_base64, screenshot_path = await self.target_resolution.get_current_screenshot_with_path()
                if screenshot_path:
                    last_screenshot_path = screenshot_path  # Keep track for timeout case
                if not screenshot_base64:
                    log.debug(f"Failed to get screenshot on check #{check_count}")
                    continue

                # --- Pixel Change Optimization ---
                should_skip_check = False
                
                # Check if we should evaluate pixel constraints
                # We evaluate if:
                # 1. We have pixel change options configured
                # 2. AND we have a previous screenshot
                # 3. AND (we haven't satisfied the constraint yet OR strategy is 'continuous')
                
                should_evaluate_pixel_constraint = False
                if action.skip and action.skip.pixel_change and last_screenshot_base64:
                    if action.skip.pixel_change.strategy == 'continuous':
                        should_evaluate_pixel_constraint = True
                    elif not pixel_constraint_satisfied:
                        should_evaluate_pixel_constraint = True
                        
                if should_evaluate_pixel_constraint:
                    try:
                        change_percent = calculate_pixel_change(last_screenshot_base64, screenshot_base64)
                        constraint = action.skip.pixel_change
                        
                        if constraint.above is not None and change_percent > constraint.above:
                            log.debug(f"Skipping wait_until check: Pixel change {change_percent:.2f}% > {constraint.above}% (waiting for stability)")
                            should_skip_check = True
                        elif constraint.below is not None and change_percent < constraint.below:
                            log.debug(f"Skipping wait_until check: Pixel change {change_percent:.2f}% < {constraint.below}% (waiting for activity)")
                            should_skip_check = True
                        log.debug(f"Pixel change evaluated: {change_percent:.2f}% > {constraint.above}%, < {constraint.below}%")
                        # If we didn't skip, and we evaluated, marks as satisfied
                        if not should_skip_check:
                            pixel_constraint_satisfied = True
                            if constraint.strategy == 'once':
                                log.info("Pixel change constraint satisfied (latched) - proceeding with condition checks")
                            
                    except Exception as e:
                        # If optimization fails, fallback to normal check (fail open)
                        log.warning(f"Failed to calculate pixel change: {e}. Proceeding with standard check.")
                
                # Update last screenshot tracking
                last_screenshot_base64 = screenshot_base64

                # Evaluate the condition tree (unless skipped)
                try:
                    condition_result = False
                    if not should_skip_check:
                        condition_result = await self._evaluate_wait_condition(action.condition, screenshot_base64)

                    if condition_result:
                        elapsed_time = time.time() - start_time
                        log.info(f"Wait until condition satisfied after {elapsed_time:.1f}s")

                        # Include screenshot path in success result
                        data = {}
                        if screenshot_path:
                            data['screenshot_path'] = screenshot_path

                        return ActionResult(
                            success=True,
                            message=f"Condition satisfied after {elapsed_time:.1f}s ({check_count} checks)",
                            execution_time=elapsed_time,
                            data=data if data else None
                        )
                except Exception as e:
                    if isinstance(e, FileNotFoundError):
                        raise
                    log.debug(f"Condition evaluation failed on check #{check_count}: {e}")

                # Check timeout AFTER each evaluation attempt
                elapsed_time = time.time() - start_time
                if elapsed_time >= action.timeout:
                    log.info(f"Wait until timeout reached after {elapsed_time:.1f}s ({check_count} checks)")

                    # Include last screenshot in timeout result
                    data = {}
                    if last_screenshot_path:
                        data['screenshot_path'] = last_screenshot_path

                    return ActionResult(
                        success=False,
                        message=f"Timeout waiting for condition after {elapsed_time:.1f}s ({check_count} checks)",
                        execution_time=elapsed_time,
                        data=data if data else None
                    )

                # Sleep for check_interval before next attempt (only if check_interval > 0)
                # Sleep for check_interval before next attempt (only if check_interval > 0)
                # If we skipped due to pixel change optimization, enforce a minimum poll interval
                interval = action.check_interval
                if should_skip_check and interval < MIN_PIXEL_POLL_INTERVAL:
                    # Enforce minimum sleep to prevent busy-wait on pixel checks
                    interval = MIN_PIXEL_POLL_INTERVAL

                if interval > 0:
                    remaining_time = action.timeout - elapsed_time
                    if remaining_time > interval:
                        await asyncio.sleep(interval)
                    elif remaining_time > 0:
                        # Sleep for the remaining time if it's less than interval
                        await asyncio.sleep(remaining_time)
                        # After this sleep we'll definitely timeout on next iteration
                # If interval is 0, don't sleep - let the natural processing time be the interval

        except Exception as e:
            log.error(f"Wait until action failed: {e}", exc_info=True)
            return ActionResult(success=False, message=str(e))

    async def _evaluate_wait_condition(self, condition, screenshot_base64: str) -> bool:
        """
        Recursively evaluate a WaitCondition tree.

        Args:
            condition: WaitCondition object to evaluate
            screenshot_base64: Screenshot data for target resolution

        Returns:
            bool: True if condition is satisfied, False otherwise
        """
        try:
            # Leaf conditions: exists/not_exists
            if condition.exists is not None:
                # Apply smart defaults if no strategy specified
                target = condition.exists
                if target.strategy is None:
                    from adare.types.playbook import BestConfidenceStrategy, TopLeftStrategy
                    if target.image:
                        target.strategy = BestConfidenceStrategy()
                        log.debug("Applied default BestConfidence strategy for image target")
                    elif target.text:
                        target.strategy = TopLeftStrategy()
                        log.debug("Applied default TopLeft strategy for text target")

                target_match = await self.target_resolution.target_resolver.resolve_target(target, screenshot_base64)
                return target_match is not None

            elif condition.not_exists is not None:
                # Apply smart defaults if no strategy specified
                target = condition.not_exists
                if target.strategy is None:
                    from adare.types.playbook import BestConfidenceStrategy, TopLeftStrategy
                    if target.image:
                        target.strategy = BestConfidenceStrategy()
                        log.debug("Applied default BestConfidence strategy for image target")
                    elif target.text:
                        target.strategy = TopLeftStrategy()
                        log.debug("Applied default TopLeft strategy for text target")

                target_match = await self.target_resolution.target_resolver.resolve_target(target, screenshot_base64)
                return target_match is None

            # Boolean operators: all/any/not
            elif condition.all is not None:
                # AND logic: all conditions must be true
                for sub_condition in condition.all:
                    if not await self._evaluate_wait_condition(sub_condition, screenshot_base64):
                        return False
                return True

            elif condition.any is not None:
                # OR logic: at least one condition must be true
                for sub_condition in condition.any:
                    if await self._evaluate_wait_condition(sub_condition, screenshot_base64):
                        return True
                return False

            elif condition.negate is not None:
                # NOT logic: invert the result
                return not await self._evaluate_wait_condition(condition.negate, screenshot_base64)

            else:
                log.error("WaitCondition has no valid field set")
                return False

        except Exception as e:
            if isinstance(e, FileNotFoundError):
                raise
            log.error(f"Error evaluating wait condition: {e}")
            return False

    async def execute_pause(self, action: PauseAction, parent_event_id: str = None,
                           event_emitter = None) -> ActionResult:
        """Execute pause action - wait for user input to continue."""
        try:
            pause_message = action.message or action.name or "Execution paused"

            # If we have a flow console, use the integrated interactive pause
            if self.flow_console and not self.flow_console.disable:
                pause_id = f"pause_{int(time.time()*1000)}"

                # Run the pause in a thread pool to avoid blocking the asyncio loop
                # This prevents timeout issues with long pauses
                loop = asyncio.get_event_loop()
                user_input = await loop.run_in_executor(
                    None,
                    functools.partial(self.flow_console.log_interactive_pause, pause_id, pause_message)
                )

                if user_input == 'c':
                    log.info("PAUSE: User continued execution")
                    return ActionResult(
                        success=True,
                        message="Execution resumed by user",
                        data={"user_input": user_input}
                    )
                elif user_input == 'interrupted':
                    log.info("PAUSE: User interrupted with Ctrl+C")
                    return ActionResult(
                        success=False,
                        message="Pause action interrupted by user",
                        data={"user_input": "interrupted"}
                    )
                else:
                    log.warning(f"PAUSE: Unexpected input '{user_input}'")
                    return ActionResult(
                        success=False,
                        message=f"Pause action failed with input: {user_input}",
                        data={"user_input": user_input}
                    )
            else:
                # Fallback to simple input if no flow console available
                pause_symbol = "⏸️"
                display_message = f"{pause_symbol} {pause_message} - Press 'c' + Enter to continue"
                log.info(f"PAUSE: {display_message}")

                # Keep asking for input until we get 'c'
                while True:
                    try:
                        user_input = input(f"\n{display_message}: ").strip().lower()
                        if user_input == 'c':
                            log.info("PAUSE: User continued execution")
                            return ActionResult(
                                success=True,
                                message="Execution resumed by user",
                                data={"user_input": user_input}
                            )
                        else:
                            print("Please press 'c' + Enter to continue execution")
                    except (EOFError, KeyboardInterrupt):
                        # Handle Ctrl+C or EOF gracefully
                        log.info("PAUSE: User interrupted with Ctrl+C")
                        return ActionResult(
                            success=False,
                            message="Pause action interrupted by user",
                            data={"user_input": "interrupted"}
                        )
                    except Exception as e:
                        log.error(f"Error during pause input: {e}")
                        return ActionResult(
                            success=False,
                            message=f"Pause action failed: {str(e)}"
                        )

        except Exception as e:
            log.error(f"Error in pause action: {e}")
            return ActionResult(
                success=False,
                message=f"Pause action failed: {str(e)}"
            )

    def _evaluate_variable_condition(self, condition: VariableCondition) -> bool:
        """
        Evaluate a variable condition locally (on host) using execution context.

        Args:
            condition: VariableCondition specifying variable and operator

        Returns:
            bool: True if condition is met, False otherwise

        Raises:
            ValueError: If variable is not found or condition evaluation fails
        """
        import re

        # Get variable value from execution context
        if condition.variable not in self.execution_context:
            raise ValueError(f"Variable '{condition.variable}' not found in execution context")

        value = self.execution_context[condition.variable]
        log.debug(f"Evaluating condition for variable '{condition.variable}' with value: {value}")

        # Evaluate based on operator
        try:
            if condition.equals is not None:
                # Direct equality comparison (case-sensitive)
                result = value == condition.equals
                log.debug(f"Equals check: {value} == {condition.equals} -> {result}")
                return result

            elif condition.contains is not None:
                # Substring check (convert to string)
                value_str = str(value)
                result = condition.contains in value_str
                log.debug(f"Contains check: '{condition.contains}' in '{value_str}' -> {result}")
                return result

            elif condition.matches is not None:
                # Regex match check
                value_str = str(value)
                result = bool(re.search(condition.matches, value_str))
                log.debug(f"Matches check: pattern '{condition.matches}' in '{value_str}' -> {result}")
                return result

            elif condition.greater_than is not None:
                # Numeric comparison (convert to number)
                if isinstance(value, (int, float)):
                    num_value = value
                else:
                    num_value = float(value)
                result = num_value > condition.greater_than
                log.debug(f"Greater than check: {num_value} > {condition.greater_than} -> {result}")
                return result

            elif condition.less_than is not None:
                # Numeric comparison (convert to number)
                if isinstance(value, (int, float)):
                    num_value = value
                else:
                    num_value = float(value)
                result = num_value < condition.less_than
                log.debug(f"Less than check: {num_value} < {condition.less_than} -> {result}")
                return result

            elif condition.is_empty is not None:
                # Empty/None check
                if condition.is_empty:
                    # Check if variable is empty/None
                    result = value is None or (isinstance(value, str) and len(value.strip()) == 0)
                    log.debug(f"Is empty check: {value} -> {result}")
                else:
                    # Check if variable is NOT empty/None
                    result = value is not None and not (isinstance(value, str) and len(value.strip()) == 0)
                    log.debug(f"Is not empty check: {value} -> {result}")
                return result

            else:
                raise ValueError("No operator specified in VariableCondition")

        except (ValueError, TypeError) as e:
            raise ValueError(f"Failed to evaluate condition: {e}")

    async def execute_stop(self, action: StopAction, parent_event_id: str = None,
                          event_emitter = None) -> ActionResult:
        """
        Execute stop action - conditionally halt playbook execution.

        If condition is present, only stops when condition evaluates to True.
        If no condition, always stops (unconditional stop).

        Returns:
            ActionResult with special 'should_stop' flag in data dict
        """
        try:
            # Evaluate condition if present
            if action.condition:
                try:
                    condition_met = self._evaluate_variable_condition(action.condition)
                    log.info(f"Stop condition evaluated to: {condition_met}")

                    if condition_met:
                        # Condition is true - stop execution
                        log.info("Stop condition met - halting playbook execution")
                        return ActionResult(
                            success=True,
                            message="Stop condition met - execution halted",
                            data={
                                'should_stop': True,
                                'condition_met': True,
                                'variable': action.condition.variable
                            }
                        )
                    else:
                        # Condition is false - continue execution
                        log.info("Stop condition not met - continuing execution")
                        return ActionResult(
                            success=True,
                            message="Stop condition not met - continuing",
                            data={
                                'should_stop': False,
                                'condition_met': False,
                                'variable': action.condition.variable
                            }
                        )

                except ValueError as e:
                    # Condition evaluation failed
                    log.error(f"Stop condition evaluation failed: {e}")
                    return ActionResult(
                        success=False,
                        message=f"Stop condition evaluation failed: {str(e)}"
                    )
            else:
                # No condition - unconditional stop
                log.info("Unconditional stop - halting playbook execution")
                return ActionResult(
                    success=True,
                    message="Unconditional stop - execution halted",
                    data={'should_stop': True, 'condition_met': None}
                )

        except Exception as e:
            log.error(f"Stop action failed: {e}", exc_info=True)
            return ActionResult(success=False, message=str(e))

    async def execute_continue(self, action: ContinueAction, parent_event_id: str = None,
                              event_emitter = None) -> ActionResult:
        """
        Execute continue action - conditionally skip remaining actions in loop/block.

        If condition is present, only continues when condition evaluates to True.
        If no condition, always continues (unconditional continue).

        Returns:
            ActionResult with special 'should_continue' flag in data dict
        """
        try:
            # Evaluate condition if present
            if action.condition:
                try:
                    condition_met = self._evaluate_variable_condition(action.condition)
                    log.info(f"Continue condition evaluated to: {condition_met}")

                    if condition_met:
                        # Condition is true - skip remaining actions
                        log.info("Continue condition met - skipping remaining actions in loop/block")
                        return ActionResult(
                            success=True,
                            message="Continue condition met - skipping remaining actions",
                            data={
                                'should_continue': True,
                                'condition_met': True,
                                'variable': action.condition.variable
                            }
                        )
                    else:
                        # Condition is false - continue normally
                        log.info("Continue condition not met - proceeding with remaining actions")
                        return ActionResult(
                            success=True,
                            message="Continue condition not met - proceeding normally",
                            data={
                                'should_continue': False,
                                'condition_met': False,
                                'variable': action.condition.variable
                            }
                        )

                except ValueError as e:
                    # Condition evaluation failed
                    log.error(f"Continue condition evaluation failed: {e}")
                    return ActionResult(
                        success=False,
                        message=f"Continue condition evaluation failed: {str(e)}"
                    )
            else:
                # No condition - unconditional continue
                log.info("Unconditional continue - skipping remaining actions in loop/block")
                return ActionResult(
                    success=True,
                    message="Unconditional continue - skipping remaining actions",
                    data={'should_continue': True, 'condition_met': None}
                )

        except Exception as e:
            log.error(f"Continue action failed: {e}", exc_info=True)
            return ActionResult(success=False, message=str(e))
