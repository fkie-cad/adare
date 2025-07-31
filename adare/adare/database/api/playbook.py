"""API for playbook database operations."""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from adare.database.models.playbook import Playbook, PlaybookItem
from adare.types.playbook import parse_playbook, Config, ActionType
from adare.database.models.experiment import Experiment

log = logging.getLogger(__name__)


class PlaybookApi:
    """API for playbook database operations."""
    
    def __init__(self, session: Session):
        self._session = session
    
    def populate_playbook_from_file(self, experiment: Experiment, playbook_file_path: Path) -> Playbook:
        """Parse YAML playbook file and populate database models."""
        try:
            # Parse YAML file using existing parser
            config = parse_playbook(playbook_file_path)
            
            # Create or update playbook record
            playbook = self._get_or_create_playbook(experiment, config)
            
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
    
    def _get_or_create_playbook(self, experiment: Experiment, config: Config) -> Playbook:
        """Get existing playbook or create new one."""
        playbook = self._session.query(Playbook).filter(
            Playbook.experiment_id == experiment.id
        ).first()
        
        if playbook:
            # Update existing
            playbook.settings = self._config_to_settings_json(config)
            playbook.version += 1
        else:
            # Create new
            playbook = Playbook(
                experiment_id=experiment.id,
                name=f"{experiment.name} Playbook",
                settings=self._config_to_settings_json(config)
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
    
    def _config_to_settings_json(self, config: Config) -> Dict[str, Any]:
        """Convert Config.settings to JSON."""
        if not config.settings:
            return {}
        
        return {
            "idle": config.settings.idle
        }
    
    def _target_to_json(self, target) -> Dict[str, Any]:
        """Convert Target object to JSON."""
        result = {}
        if target.image:
            result["image"] = target.image
        if target.text:
            result["text"] = target.text  
        if target.position:
            result["position"] = target.position
        return result
    
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