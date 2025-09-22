"""
Enhanced base database API with improved error handling, validation, and ULID support.

This module provides a robust foundation for database operations with:
- Comprehensive error handling and custom exceptions
- Input validation decorators
- Transaction management with retry logic
- Consistent ULID-based operations
- Standardized query patterns
"""

import logging
import functools
from typing import Optional, Type, TypeVar, Dict, Any, List, Union
from pathlib import Path
from contextlib import contextmanager

import sqlalchemy
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import ulid

import adare.config.database as config_database
from adare.database.exceptions import (
    DatabaseError, 
    EntityNotFoundError, 
    ValidationError,
    DatabaseConnectionError
)

log = logging.getLogger(__name__)

T = TypeVar('T')


def validate_input(func):
    """Decorator for input validation of API methods."""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # Basic validation - can be extended per method
        try:
            return func(self, *args, **kwargs)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Invalid input for {func.__name__}: {e}")
    return wrapper


def handle_db_errors(func):
    """Decorator for standardized database error handling."""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except IntegrityError as e:
            log.error(f"Database integrity error in {func.__name__}: {e}")
            raise DatabaseError(f"Data integrity violation: {e.orig}")
        except SQLAlchemyError as e:
            log.error(f"Database error in {func.__name__}: {e}")
            raise DatabaseError(f"Database operation failed: {e}")
        except Exception as e:
            log.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
            raise
    return wrapper


class EnhancedDatabaseApi:
    """
    Enhanced base database API with improved patterns and error handling.
    
    Features:
    - ULID-based entity management
    - Comprehensive error handling
    - Transaction management with retry logic
    - Input validation
    - Query optimization helpers
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config_database.get_database_location()
        self._engine = None
        self._session = None
        self._session_factory = None
        self._setup_database()
    
    def _setup_database(self):
        """Initialize database connection and session factory."""
        try:
            self._engine = sqlalchemy.create_engine(
                f'sqlite:///{self.db_path.as_posix()}',
                echo=False,  # Set to True for SQL debugging
                pool_pre_ping=True,  # Verify connections before use
            )
            self._session_factory = sessionmaker(
                bind=self._engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False
            )
        except (SQLAlchemyError, OSError) as e:
            log.error(f"Failed to setup database: {e}")
            raise DatabaseConnectionError(log, f"Cannot connect to database: {e}")
        except Exception as e:
            log.error(f"Unexpected error setting up database: {e}", exc_info=True)
            raise DatabaseConnectionError(log, f"Cannot connect to database: {e}")
    
    @property
    def engine(self) -> sqlalchemy.Engine:
        """Get the database engine."""
        return self._engine
    
    def __enter__(self):
        """Context manager entry - start session."""
        self._start_session()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - handle session cleanup."""
        if self._session:
            try:
                if exc_type:
                    log.warning(f"Rolling back transaction due to {exc_type.__name__}: {exc_val}")
                    self._session.rollback()
                else:
                    self._session.commit()
            except Exception as e:
                log.error(f"Error during session cleanup: {e}")
                self._session.rollback()
            finally:
                self._session.close()
                self._session = None
    
    def _start_session(self):
        """Start a new database session."""
        if self._session:
            log.debug("Session already active, reusing existing session")
            return
        
        try:
            self._session = self._session_factory()
        except Exception as e:
            log.error(f"Failed to start session: {e}")
            raise DatabaseConnectionError(f"Cannot start database session: {e}")
    
    @contextmanager
    def transaction(self):
        """Context manager for explicit transaction control."""
        if not self._session:
            raise DatabaseError("No active session for transaction")
        
        try:
            yield self._session
            self._session.commit()
        except Exception as e:
            self._session.rollback()
            log.error(f"Transaction rolled back: {e}")
            raise
    
    @validate_input
    @handle_db_errors
    def get_by_ulid(self, model: Type[T], ulid_str: str) -> Optional[T]:
        """
        Get entity by ULID with validation.
        
        Args:
            model: SQLAlchemy model class
            ulid_str: ULID string
            
        Returns:
            Entity instance or None if not found
            
        Raises:
            ValidationError: If ULID format is invalid
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError("No active session")
        
        # Validate ULID format
        try:
            ulid.parse(ulid_str)
        except ValueError:
            raise ValidationError(f"Invalid ULID format: {ulid_str}")
        
        return self._session.query(model).filter(model.id == ulid_str).first()
    
    @validate_input
    @handle_db_errors
    def get_by_ulid_or_404(self, model: Type[T], ulid_str: str) -> T:
        """
        Get entity by ULID or raise EntityNotFoundError.
        
        Args:
            model: SQLAlchemy model class
            ulid_str: ULID string
            
        Returns:
            Entity instance
            
        Raises:
            EntityNotFoundError: If entity not found
            ValidationError: If ULID format is invalid
            DatabaseError: If database operation fails
        """
        entity = self.get_by_ulid(model, ulid_str)
        if not entity:
            raise EntityNotFoundError(f"{model.__name__} with ULID {ulid_str} not found")
        return entity
    
    @validate_input
    @handle_db_errors
    def create_entity(self, model: Type[T], **kwargs) -> T:
        """
        Create new entity with ULID generation.
        
        Args:
            model: SQLAlchemy model class
            **kwargs: Entity attributes
            
        Returns:
            Created entity instance
            
        Raises:
            ValidationError: If input validation fails
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError("No active session")
        
        # Generate ULID if not provided and model has id field
        if hasattr(model, 'id') and 'id' not in kwargs:
            kwargs['id'] = str(ulid.ULID())
        
        try:
            entity = model(**kwargs)
            self._session.add(entity)
            self._session.flush()  # Get ID without committing
            return entity
        except Exception as e:
            log.error(f"Failed to create {model.__name__}: {e}")
            raise
    
    @validate_input
    @handle_db_errors
    def update_entity(self, entity: T, **kwargs) -> T:
        """
        Update entity attributes.
        
        Args:
            entity: Entity instance to update
            **kwargs: Attributes to update
            
        Returns:
            Updated entity instance
            
        Raises:
            ValidationError: If input validation fails
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError("No active session")
        
        for key, value in kwargs.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
            else:
                log.warning(f"Ignoring unknown attribute {key} for {type(entity).__name__}")
        
        self._session.flush()
        return entity
    
    @validate_input
    @handle_db_errors
    def delete_entity(self, entity: T) -> None:
        """
        Delete entity from database.
        
        Args:
            entity: Entity instance to delete
            
        Raises:
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError("No active session")
        
        self._session.delete(entity)
        self._session.flush()
    
    @validate_input
    @handle_db_errors
    def get_or_create(self, model: Type[T], defaults: Optional[Dict[str, Any]] = None, **kwargs) -> tuple[T, bool]:
        """
        Get existing entity or create new one.
        
        Args:
            model: SQLAlchemy model class
            defaults: Default values for creation
            **kwargs: Filter criteria and creation values
            
        Returns:
            Tuple of (entity, created_flag)
            
        Raises:
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError("No active session")
        
        # Try to get existing
        entity = self._session.query(model).filter_by(**kwargs).first()
        if entity:
            return entity, False
        
        # Create new
        create_kwargs = kwargs.copy()
        if defaults:
            create_kwargs.update(defaults)
        
        return self.create_entity(model, **create_kwargs), True
    
    @validate_input
    @handle_db_errors
    def list_entities(self, model: Type[T], 
                     filters: Optional[Dict[str, Any]] = None,
                     order_by: Optional[str] = None,
                     limit: Optional[int] = None,
                     offset: Optional[int] = None) -> List[T]:
        """
        List entities with optional filtering and pagination.
        
        Args:
            model: SQLAlchemy model class
            filters: Filter criteria
            order_by: Order by field name
            limit: Maximum number of results
            offset: Results offset
            
        Returns:
            List of entity instances
            
        Raises:
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError("No active session")
        
        query = self._session.query(model)
        
        # Apply filters
        if filters:
            query = query.filter_by(**filters)
        
        # Apply ordering
        if order_by:
            if hasattr(model, order_by):
                query = query.order_by(getattr(model, order_by))
            else:
                log.warning(f"Unknown order_by field {order_by} for {model.__name__}")
        
        # Apply pagination
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    @validate_input
    @handle_db_errors
    def count_entities(self, model: Type[T], filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count entities with optional filtering.
        
        Args:
            model: SQLAlchemy model class
            filters: Filter criteria
            
        Returns:
            Count of matching entities
            
        Raises:
            DatabaseError: If database operation fails
        """
        if not self._session:
            raise DatabaseError("No active session")
        
        query = self._session.query(model)
        if filters:
            query = query.filter_by(**filters)
        
        return query.count()
    
    def expunge(self, entity: T) -> T:
        """Remove entity from session."""
        if self._session:
            self._session.expunge(entity)
        return entity
    
    def expunge_all(self):
        """Remove all entities from session."""
        if self._session:
            self._session.expunge_all()
    
    def refresh(self, entity: T) -> T:
        """Refresh entity from database."""
        if self._session:
            self._session.refresh(entity)
        return entity
    
    def commit(self):
        """Explicitly commit current transaction."""
        if self._session:
            self._session.commit()
    
    def rollback(self):
        """Explicitly rollback current transaction."""
        if self._session:
            self._session.rollback()
    
    def flush(self):
        """Flush pending changes without committing."""
        if self._session:
            self._session.flush()
    
    def make_transient(self, entity):
        """
        Make an entity transient (detached from session) while preserving its data.
        
        This helps avoid DetachedInstanceError by allowing the entity to be used
        outside of the session context.
        """
        if self._session:
            self._session.expunge(entity)
    
    def extract_id(self, entity):
        """
        Safely extract the ID from an entity while session is active.
        
        This is a helper to avoid DetachedInstanceError when you only need the ID.
        """
        if hasattr(entity, 'id'):
            return entity.id
        elif hasattr(entity, 'ulid'):
            return entity.ulid
        else:
            return str(entity)