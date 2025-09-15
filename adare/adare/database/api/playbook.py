"""API for playbook database operations."""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from adare.database.models.playbook import Playbook, PlaybookItem, ActionExecution
from adare.types.playbook import parse_playbook, Playbook as PlaybookType, ActionType
from adare.database.models.experiment import Experiment
from adare.database.api.database import DatabaseApi
from datetime import datetime, timezone
import adare.config.database as config_database

log = logging.getLogger(__name__)


class PlaybookApi(DatabaseApi):
    """API for playbook database operations."""
    
    def __init__(self, db_path: Path = None):
        if db_path is None:
            db_path = config_database.get_database_location()
        super().__init__(db_path)
    
    def populate_playbook_from_file(self, experiment: Experiment, playbook_file_path: Path) -> Playbook:
        """Parse YAML playbook file and populate database models."""
        try:
            # Read original YAML content for storage
            original_yaml_content = playbook_file_path.read_text(encoding='utf-8')

            # CLAUDE: Extract VM OS and user from experiment's environment for automatic variables
            vm_os = None
            vm_user = None
            if experiment.environments:
                # Use first environment's OS info
                env = experiment.environments[0]
                if env.vm and env.vm.osinfo:
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
        elif hasattr(value, '__dict__'):
            # Handle action objects and other custom classes
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
    
    def load_playbook_from_database(self, experiment_id: str) -> PlaybookType:
        """Load Playbook object from stored YAML in database (no file parsing needed).

        Args:
            experiment_id: The experiment ID to load the playbook for

        Returns:
            Parsed Playbook object from stored YAML (automatic variables added during execution)

        Raises:
            ValueError: If no playbook found for experiment
        """
        playbook = self.get_playbook_by_experiment_id(experiment_id)
        if not playbook:
            raise ValueError(f"No playbook found for experiment {experiment_id}")
        
        if not playbook.original_yaml_content:
            raise ValueError(f"No original YAML content stored for experiment {experiment_id} (legacy data)")
        
        # Parse YAML directly from memory
        import yaml
        import cattrs
        from typing import Union, Optional
        from adare.types.playbook import (
            Playbook as PlaybookType, ActionType, ExistsCondition, NotExistsCondition, TargetStrategyType,
            _structure_action, _structure_condition, _structure_strategy, _register_strict_hooks
        )
        
        # Parse YAML content using custom loader for tags like !re
        from adarelib.testset.yaml.customloader import get_custom_loader
        data = yaml.load(playbook.original_yaml_content, Loader=get_custom_loader())

        # Convert variables to VariableRegistry if present (automatic variables added during execution)
        if 'variables' in data and data['variables']:
            from adarelib.common.variables import VariableRegistry
            data['variables'] = VariableRegistry.from_dict(data['variables'])
        # Note: automatic variables will be merged during variable resolution, not during parsing

        # Set up cattrs converter (same as in parse_playbook)
        converter = cattrs.Converter()
        converter.forbid_extra_keys = True
        
        # Register structure hooks
        converter.register_structure_hook(ActionType, lambda obj, _: _structure_action(obj, converter))
        converter.register_structure_hook(Union[ExistsCondition, NotExistsCondition], lambda obj, _: _structure_condition(obj, converter))
        converter.register_structure_hook(Optional[TargetStrategyType], lambda obj, _: _structure_strategy(obj, converter) if obj is not None else None)
        
        _register_strict_hooks(converter)
        
        return converter.structure(data, PlaybookType)