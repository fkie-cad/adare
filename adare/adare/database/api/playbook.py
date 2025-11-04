"""API for playbook database operations."""

import logging
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from adare.database.models.project_models import Playbook, PlaybookItem, ActionExecution, Experiment
from adare.types.playbook import parse_playbook, Playbook as PlaybookType, ActionType
from adare.database.api.base import ProjectDatabaseApi
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


class PlaybookApi(ProjectDatabaseApi):
    """API for playbook database operations."""

    def __init__(self, project_path: Path):
        super().__init__(project_path)
    
    def populate_playbook_from_file(self, experiment: Experiment, playbook_file_path: Path) -> Playbook:
        """Parse YAML playbook file and populate database models."""
        try:
            # Read original YAML content for storage
            original_yaml_content = playbook_file_path.read_text(encoding='utf-8')

            # CLAUDE: Extract VM OS and user from experiment's environment for automatic variables
            vm_os = None
            vm_user = None
            if experiment.environments:
                # Use first environment's OS info - query from global database
                env_id = experiment.environments[0].id
                from adare.database.api.base import GlobalDatabaseApi
                from adare.database.models.global_models import Environment, Vm
                from sqlalchemy.orm import joinedload
                with GlobalDatabaseApi() as global_api:
                    env = global_api._session.query(Environment).options(
                        joinedload(Environment.vm).joinedload(Vm.osinfo)
                    ).filter(Environment.id == env_id).first()
                    if env and env.vm and env.vm.osinfo:
                        vm_os = env.vm.osinfo.platform  # 'windows' or 'linux'
                        # Get VM user from config - import here to avoid circular imports
                        from adare.config import get_vm_credentials
                        if vm_os:
                            vm_user, _ = get_vm_credentials(vm_os)

            # Parse YAML file using existing parser (automatic variables added during execution)
            config = parse_playbook(playbook_file_path)
            
            # Create or update playbook record
            playbook = self._get_or_create_playbook(experiment, config, original_yaml_content)
            
            # Flush to get the playbook ID assigned before creating items
            self._session.flush()
            
            # Clear existing items (for updates)
            self._session.query(PlaybookItem).filter(
                PlaybookItem.playbook_id == playbook.id
            ).delete()
            
            # Convert actions to database items
            for order, action in enumerate(config.actions):
                self._create_playbook_item(playbook, action, order)
            
            self._session.commit()
            log.info(f"Populated playbook for experiment {experiment.name} with {len(config.actions)} actions")
            return playbook
            
        except Exception as e:
            self._session.rollback()
            log.error(f"Failed to populate playbook from {playbook_file_path}: {e}", exc_info=True)
            raise
    
    def _get_or_create_playbook(self, experiment: Experiment, config: PlaybookType, original_yaml_content: str) -> Playbook:
        """Get existing playbook or create new one."""
        playbook = self._session.query(Playbook).filter(
            Playbook.experiment_id == experiment.id
        ).first()
        
        if playbook:
            # Update existing
            playbook.settings = self._config_to_settings_json(config)
            playbook.original_yaml_content = original_yaml_content
            playbook.version += 1
        else:
            # Create new
            playbook = Playbook(
                experiment_id=experiment.id,
                name=f"{experiment.name} Playbook",
                settings=self._config_to_settings_json(config),
                original_yaml_content=original_yaml_content
            )
            self._session.add(playbook)
        
        return playbook
    
    def _create_playbook_item(self, playbook: Playbook, action: ActionType, sequence_order: int) -> PlaybookItem:
        """Convert action to PlaybookItem."""
        # Determine action type from class name
        action_type = action.__class__.__name__.replace('Action', '').lower()
        
        # Extract target information
        target_json = None
        if hasattr(action, 'target'):
            target_json = self._target_to_json(action.target)
        
        # Extract parameters (all other fields)
        parameters = self._action_to_parameters_json(action)
        
        # Extract conditions
        conditions_json = None
        if hasattr(action, 'when') and action.when:
            conditions_json = {"when": [self._condition_to_json(cond) for cond in action.when]}
        
        item = PlaybookItem(
            playbook_id=playbook.id,
            item_type='action',
            sequence_order=sequence_order,
            action_type=action_type,
            target=target_json,
            parameters=parameters,
            conditions=conditions_json,
            description=getattr(action, 'description', ''),
            is_enabled=True
        )
        
        self._session.add(item)
        return item
    
    def _config_to_settings_json(self, config: PlaybookType) -> Dict[str, Any]:
        """Convert Config.settings to JSON."""
        if not config.settings:
            return {}
        
        result = {
            "idle": config.settings.idle
        }
        
        # Add optional settings if they exist
        if hasattr(config.settings, 'timeout') and config.settings.timeout is not None:
            result["timeout"] = config.settings.timeout
        if hasattr(config.settings, 'screenshot') and config.settings.screenshot is not None:
            result["screenshot"] = config.settings.screenshot
        if hasattr(config.settings, 'continue_on_test_failure'):
            result["continue_on_test_failure"] = config.settings.continue_on_test_failure
        
        return result
    
    def _target_to_json(self, target) -> Dict[str, Any]:
        """Convert Target object to JSON."""
        result = {}
        if target.image:
            result["image"] = target.image
        if target.text:
            result["text"] = target.text  
        if target.position:
            result["position"] = target.position
        if target.strategy:
            result["strategy"] = self._strategy_to_json(target.strategy)
        return result
    
    def _strategy_to_json(self, strategy) -> Dict[str, Any]:
        """Convert strategy object to JSON."""
        import attrs
        from adare.types.playbook import SweepStrategy, BestConfidenceStrategy, ClosestToStrategy
        
        strategy_class = strategy.__class__.__name__
        
        if isinstance(strategy, SweepStrategy):
            return {strategy_class: {"index": strategy.index}}
        elif attrs.has(strategy):
            # For attrs-defined strategies, use attrs.asdict()
            return {strategy_class: attrs.asdict(strategy)}
        elif hasattr(strategy, '__dict__'):
            # For regular classes with attributes, serialize all fields
            return {strategy_class: strategy.__dict__}
        else:
            # For simple strategies with no attributes
            return {strategy_class: {}}
    
    def _condition_to_json(self, condition) -> Dict[str, Any]:
        """Convert condition object to JSON."""
        condition_type = condition.__class__.__name__.replace('Condition', '').lower()
        result = {"type": condition_type}
        
        # Serialize all non-callable attributes
        for attr_name in dir(condition):
            if (not attr_name.startswith('_') and 
                attr_name != '__class__' and
                hasattr(condition, attr_name)):
                
                attr_value = getattr(condition, attr_name)
                if not callable(attr_value) and attr_value is not None:
                    result[attr_name] = self._serialize_value(attr_value)
            
        return result
    
    def _action_to_parameters_json(self, action: ActionType) -> Dict[str, Any]:
        """Extract action-specific parameters to JSON."""
        parameters = {}
        
        # Get all attributes except common ones
        exclude_attrs = {'target', 'when', 'description'}
        
        for attr_name in dir(action):
            if (not attr_name.startswith('_') and 
                attr_name not in exclude_attrs and
                hasattr(action, attr_name)):
                
                value = getattr(action, attr_name)
                if not callable(value):
                    parameters[attr_name] = self._serialize_value(value)
        
        return parameters
    
    def _serialize_wait_condition(self, condition) -> Dict[str, Any]:
        """Serialize WaitCondition to JSON, only including the active field."""
        from adare.types.playbook import WaitCondition

        # Serialize only the non-None field (one must be set per WaitCondition validation)
        if condition.exists is not None:
            return {"exists": self._target_to_json(condition.exists)}
        elif condition.not_exists is not None:
            return {"not_exists": self._target_to_json(condition.not_exists)}
        elif condition.all is not None:
            return {"all": [self._serialize_wait_condition(c) for c in condition.all]}
        elif condition.any is not None:
            return {"any": [self._serialize_wait_condition(c) for c in condition.any]}
        elif condition.negate is not None:
            return {"negate": self._serialize_wait_condition(condition.negate)}
        else:
            raise ValueError(f"Invalid WaitCondition: no active field found")

    def _serialize_value(self, value) -> Any:
        """Recursively serialize complex objects to JSON-compatible format."""
        if value is None:
            return None
        elif isinstance(value, (str, int, float, bool)):
            return value
        elif isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}

        # CRITICAL: Check WaitCondition BEFORE hasattr(__dict__) because attrs classes
        # may not have __dict__ (they use __slots__ by default)
        from adare.types.playbook import WaitCondition
        if isinstance(value, WaitCondition):
            return self._serialize_wait_condition(value)

        # Now check for __dict__ for other object types
        if hasattr(value, '__dict__'):
            # Check if this is an attrs class
            import attrs
            if attrs.has(value):
                # Use attrs.asdict() for attrs-defined classes
                return attrs.asdict(value, recurse=True, filter=lambda attr, val: val is not None)
            else:
                # Handle regular classes with __dict__
                result = {}
                for attr_name in dir(value):
                    if not attr_name.startswith('_') and hasattr(value, attr_name):
                        attr_value = getattr(value, attr_name)
                        if not callable(attr_value):
                            result[attr_name] = self._serialize_value(attr_value)
                return result
        else:
            # Fallback: try to convert to string
            return str(value)
    
    def get_playbook_by_experiment(self, experiment_id: str) -> Optional[Playbook]:
        """Get playbook for an experiment."""
        return self._session.query(Playbook).filter(
            Playbook.experiment_id == experiment_id
        ).first()
    
    def get_playbook_items(self, playbook_id: str, parent_id: Optional[str] = None) -> List[PlaybookItem]:
        """Get playbook items, optionally filtered by parent."""
        query = self._session.query(PlaybookItem).filter(
            PlaybookItem.playbook_id == playbook_id
        )
        
        if parent_id:
            query = query.filter(PlaybookItem.parent_id == parent_id)
        else:
            query = query.filter(PlaybookItem.parent_id.is_(None))
        
        return query.order_by(PlaybookItem.sequence_order).all()
    
    def get_playbook_by_experiment_id(self, experiment_id: str) -> Optional[Playbook]:
        """Get playbook by experiment ID."""
        return self._session.query(Playbook).filter(
            Playbook.experiment_id == experiment_id
        ).first()
    
    def create_action_execution(
        self, 
        playbook_item_id: str, 
        experiment_run_id: str,
        status: str = 'pending'
    ) -> ActionExecution:
        """Create a new action execution record."""
        execution = ActionExecution(
            playbook_item_id=playbook_item_id,
            experiment_run_id=experiment_run_id,
            status=status,
            created_at=datetime.now(timezone.utc)
        )
        self._session.add(execution)
        self._session.flush()  # Get ID assigned
        return execution
    
    def update_action_execution_start(self, execution_id: str) -> None:
        """Mark action execution as started."""
        execution = self._session.query(ActionExecution).filter(
            ActionExecution.id == execution_id
        ).first()
        if execution:
            execution.status = 'running'
            execution.started_at = datetime.now(timezone.utc)
            self._session.flush()
    
    def update_action_execution_complete(
        self,
        execution_id: str,
        success: bool,
        result_data: Optional[Dict] = None,
        error_message: Optional[str] = None,
        attempt_number: int = 1
    ) -> None:
        """Mark action execution as completed."""
        execution = self._session.query(ActionExecution).filter(
            ActionExecution.id == execution_id
        ).first()
        if execution:
            execution.status = 'success' if success else 'failed'
            execution.completed_at = datetime.now(timezone.utc)
            execution.result_data = result_data
            execution.error_message = error_message
            execution.attempt_number = attempt_number
            self._session.flush()
    
    def get_action_executions_by_run(self, experiment_run_id: str) -> List[ActionExecution]:
        """Get all action executions for an experiment run."""
        return self._session.query(ActionExecution).filter(
            ActionExecution.experiment_run_id == experiment_run_id
        ).order_by(ActionExecution.created_at).all()
    
    def recover_playbook_yaml(self, experiment_id: str) -> str:
        """Recover the original playbook YAML from database.

        Args:
            experiment_id: The experiment ID to recover the playbook for

        Returns:
            Original YAML content as string

        Raises:
            ValueError: If no playbook found for experiment
        """
        playbook = self.get_playbook_by_experiment_id(experiment_id)
        if not playbook:
            raise ValueError(f"No playbook found for experiment {experiment_id}")

        if not playbook.original_yaml_content:
            raise ValueError(f"No original YAML content stored for experiment {experiment_id} (legacy data)")

        return playbook.original_yaml_content

    # ============================================================================
    # DESERIALIZATION METHODS (Database models -> Python objects)
    # ============================================================================

    def _json_to_settings(self, settings_json: Dict[str, Any]):
        """Convert settings JSON to Settings object."""
        if not settings_json:
            from adare.types.playbook import Settings
            return Settings()

        from adare.types.playbook import Settings
        return Settings(
            idle=settings_json.get('idle', 0.1),
            timeout=settings_json.get('timeout'),
            screenshot=settings_json.get('screenshot'),
            continue_on_test_failure=settings_json.get('continue_on_test_failure', False),
            auto_pull_on_test_failure=settings_json.get('auto_pull_on_test_failure', True),
            collect_system_info=settings_json.get('collect_system_info', True),
            forensic_logging=settings_json.get('forensic_logging', True)
        )

    def _json_to_target(self, target_json: Optional[Dict[str, Any]]):
        """Convert target JSON to Target object."""
        if not target_json:
            return None

        from adare.types.playbook import Target

        # Reconstruct strategy if present
        strategy = None
        if 'strategy' in target_json and target_json['strategy']:
            strategy = self._json_to_strategy(target_json['strategy'])

        return Target(
            image=target_json.get('image'),
            text=target_json.get('text'),
            position=target_json.get('position'),
            strategy=strategy
        )

    def _json_to_strategy(self, strategy_json: Dict[str, Any]):
        """Convert strategy JSON to strategy object."""
        from adare.types.playbook import (
            SweepStrategy, BestConfidenceStrategy, ClosestToStrategy,
            TopLeftStrategy, TopRightStrategy, BottomLeftStrategy, BottomRightStrategy,
            LargestStrategy, SmallestStrategy
        )

        # Strategy JSON format: {"StrategyClassName": {params...}}
        strategy_class_name = list(strategy_json.keys())[0]
        strategy_params = strategy_json[strategy_class_name]

        strategy_map = {
            'SweepStrategy': SweepStrategy,
            'BestConfidenceStrategy': BestConfidenceStrategy,
            'ClosestToStrategy': ClosestToStrategy,
            'TopLeftStrategy': TopLeftStrategy,
            'TopRightStrategy': TopRightStrategy,
            'BottomLeftStrategy': BottomLeftStrategy,
            'BottomRightStrategy': BottomRightStrategy,
            'LargestStrategy': LargestStrategy,
            'SmallestStrategy': SmallestStrategy
        }

        strategy_class = strategy_map.get(strategy_class_name)
        if not strategy_class:
            raise ValueError(f"Unknown strategy type: {strategy_class_name}")

        return strategy_class(**strategy_params)

    def _json_to_conditions(self, conditions_json: Optional[Dict[str, Any]]):
        """Convert conditions JSON to list of condition objects."""
        if not conditions_json or 'when' not in conditions_json:
            return None

        from adare.types.playbook import ExistsCondition, NotExistsCondition

        conditions = []
        for cond_json in conditions_json['when']:
            cond_type = cond_json.get('type')

            if cond_type == 'exists':
                conditions.append(ExistsCondition(
                    text=cond_json.get('text'),
                    image=cond_json.get('image')
                ))
            elif cond_type == 'notexists':
                conditions.append(NotExistsCondition(
                    text=cond_json.get('text'),
                    image=cond_json.get('image')
                ))
            else:
                log.warning(f"Unknown condition type: {cond_type}")

        return conditions if conditions else None

    def _playbook_item_to_action(self, item: PlaybookItem) -> ActionType:
        """Convert PlaybookItem database model to Action object."""
        from adare.types.playbook import (
            ClickAction, DragAction, KeyboardAction, IdleAction, ScrollAction, GotoAction,
            ActionTestAction, CommandAction, ScreenshotAction, BlockAction, SaveTimestampAction,
            PullAction, PauseAction, WaitUntilAction, WaitCondition, Target
        )

        # Common fields
        description = item.description or ''
        conditions = self._json_to_conditions(item.conditions)

        # Action-specific reconstruction based on action_type
        action_type = item.action_type
        params = item.parameters or {}

        # CLAUDE: Debug logging to diagnose serialization issues
        log.debug(f"CLAUDE: Deserializing {action_type} action")
        log.debug(f"CLAUDE: item.parameters type: {type(item.parameters)}")
        log.debug(f"CLAUDE: params type: {type(params)}")

        # CLAUDE: Defensive JSON parsing - handle case where SQLAlchemy returns string instead of dict
        if isinstance(params, str):
            import json
            log.warning(f"CLAUDE: parameters is a string (double-encoding issue), parsing JSON: {params[:100]}...")
            try:
                params = json.loads(params)
                log.info(f"CLAUDE: Successfully parsed JSON string to dict")
            except json.JSONDecodeError as e:
                log.error(f"CLAUDE: Failed to parse parameters JSON: {e}")
                raise ValueError(f"Invalid JSON in {action_type} action parameters: {params[:200]}")

        if action_type == 'click':
            return ClickAction(
                target=self._json_to_target(item.target),
                type=params.get('type', 'left'),
                description=description
            )

        elif action_type == 'drag':
            # Drag has src and dst targets in parameters
            src_target = self._json_to_target(params.get('src'))
            dst_target = self._json_to_target(params.get('dst'))
            return DragAction(
                src=src_target,
                dst=dst_target,
                description=description
            )

        elif action_type == 'keyboard':
            return KeyboardAction(
                key=params.get('key'),
                text=params.get('text'),
                combination=params.get('combination'),
                when=conditions,
                description=description
            )

        elif action_type == 'idle':
            return IdleAction(
                duration=params.get('duration', 0.0),
                description=description
            )

        elif action_type == 'scroll':
            return ScrollAction(
                direction=params.get('direction', 'down'),
                amount=params.get('amount', 1),
                description=description
            )

        elif action_type == 'goto':
            return GotoAction(
                target=self._json_to_target(item.target),
                description=description
            )

        elif action_type == 'actiontest':
            return ActionTestAction(
                name=params.get('name', ''),
                description=description
            )

        elif action_type == 'command':
            return CommandAction(
                command=params.get('command', ''),
                name=params.get('name'),
                description=description,
                tool=params.get('tool'),
                cwd=params.get('cwd'),
                env=params.get('env'),
                timeout=params.get('timeout'),
                shell=params.get('shell', False),
                admin=params.get('admin', False),
                background=params.get('background', False)
            )

        elif action_type == 'screenshot':
            return ScreenshotAction(
                description=description,
                name=params.get('name'),
                x=params.get('x'),
                y=params.get('y'),
                width=params.get('width'),
                height=params.get('height')
            )

        elif action_type == 'savetimestamp':
            return SaveTimestampAction(
                variable=params.get('variable', ''),
                description=description
            )

        elif action_type == 'pull':
            return PullAction(
                src=params.get('src', ''),
                dst=params.get('dst'),
                description=description
            )

        elif action_type == 'pause':
            return PauseAction(
                message=params.get('message'),
                name=params.get('name'),
                description=description
            )

        elif action_type == 'waituntil':
            # Reconstruct WaitCondition recursively
            condition_data = params.get('condition', {})
            condition = self._json_to_wait_condition(condition_data)
            return WaitUntilAction(
                condition=condition,
                timeout=params.get('timeout', 60.0),
                check_interval=params.get('check_interval', 0.0),
                initial_delay=params.get('initial_delay', 5.0),
                description=description
            )

        elif action_type == 'block':
            # Block actions contain nested actions - reconstruct recursively
            nested_actions = []
            # Note: Nested actions would need to be stored as child PlaybookItems
            # For now, log warning if block actions are encountered
            log.warning(f"Block actions not yet fully supported in database deserialization")
            return BlockAction(
                actions=nested_actions,
                description=description,
                when=conditions
            )

        else:
            raise ValueError(f"Unknown action type in database: {action_type}")

    def _json_to_wait_condition(self, condition_data: Dict[str, Any]):
        """Recursively convert condition JSON to WaitCondition object."""
        from adare.types.playbook import WaitCondition

        # Check which field is set
        if 'exists' in condition_data and condition_data['exists']:
            return WaitCondition(exists=self._json_to_target(condition_data['exists']))
        elif 'not_exists' in condition_data and condition_data['not_exists']:
            return WaitCondition(not_exists=self._json_to_target(condition_data['not_exists']))
        elif 'all' in condition_data and condition_data['all']:
            nested = [self._json_to_wait_condition(c) for c in condition_data['all']]
            return WaitCondition(all=nested)
        elif 'any' in condition_data and condition_data['any']:
            nested = [self._json_to_wait_condition(c) for c in condition_data['any']]
            return WaitCondition(any=nested)
        elif 'negate' in condition_data and condition_data['negate']:
            nested = self._json_to_wait_condition(condition_data['negate'])
            return WaitCondition(negate=nested)
        else:
            raise ValueError(f"Invalid WaitCondition data: {condition_data}")

    def _load_variables_and_tests_from_yaml(self, yaml_content: str):
        """Load variables and tests from YAML content (complex structures)."""
        import yaml
        from adarelib.testset.yaml.customloader import get_custom_loader

        data = yaml.load(yaml_content, Loader=get_custom_loader())

        # Extract variables
        variables = None
        if 'variables' in data and data['variables']:
            from adarelib.common.variables import VariableRegistry
            variables = VariableRegistry.from_dict(data['variables'])

        # Extract tests (keep as-is from YAML parsing)
        tests = data.get('tests', [])

        return variables, tests
    
    def load_playbook_from_database(self, experiment_id: str) -> PlaybookType:
        """Load Playbook object from database models (no YAML parsing for actions).

        Args:
            experiment_id: The experiment ID to load the playbook for

        Returns:
            Playbook object reconstructed from PlaybookItem database models

        Raises:
            ValueError: If no playbook found for experiment
        """
        playbook = self.get_playbook_by_experiment_id(experiment_id)
        if not playbook:
            raise ValueError(f"No playbook found for experiment {experiment_id}")

        # Reconstruct actions from PlaybookItem database models
        log.info(f"CLAUDE: Loading playbook from database models (not parsing YAML for actions)")
        items = self.get_playbook_items(playbook.id)
        log.info(f"CLAUDE: Reconstructing {len(items)} actions from PlaybookItem database models")
        actions = [self._playbook_item_to_action(item) for item in items]

        # Reconstruct settings from JSON
        settings = self._json_to_settings(playbook.settings)

        # Parse variables and tests from original YAML (complex structures, kept as YAML)
        variables = None
        tests = []
        if playbook.original_yaml_content:
            log.info(f"CLAUDE: Parsing variables/tests from stored YAML (not re-parsing actions)")
            variables, tests = self._load_variables_and_tests_from_yaml(playbook.original_yaml_content)

        from adare.types.playbook import Playbook as PlaybookType
        log.info(f"CLAUDE: Playbook reconstruction complete - {len(actions)} actions, {len(tests)} tests")
        return PlaybookType(
            actions=actions,
            settings=settings,
            variables=variables,
            tests=tests
        )