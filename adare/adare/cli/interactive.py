"""CLI commands for interactive experiment development."""

import logging
from pathlib import Path

from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError

log = logging.getLogger(__name__)


def exec_experiment_interactive(arguments):
    """Execute interactive experiment development mode."""
    from adare.frontend.interactive.dev_server import InteractiveDevelopmentServer
    
    if project_directory := determine_projectdirectory(arguments.project):
        # Start interactive development server
        server = InteractiveDevelopmentServer(
            project_path=project_directory,
            experiment_name=arguments.experiment,
            environment=arguments.environment,
            port=arguments.port or 8080
        )
        
        try:
            log.info(f"Starting interactive development for experiment '{arguments.experiment}'")
            log.info(f"Environment: {arguments.environment}")
            log.info(f"Web interface will be available at http://127.0.0.1:{server.port}")
            
            server.run_server()
            
        except KeyboardInterrupt:
            log.info("Interactive development server stopped by user")
        except Exception as e:
            log.error(f"Error running interactive development server: {e}")
            raise
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_experiment_dev(arguments):
    """Alias for interactive development (shorter command)."""
    exec_experiment_interactive(arguments)