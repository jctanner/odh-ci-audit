"""Entry point for Flask API server."""

import os
import logging
from ci_audit.api import create_app
from ci_audit.config import Config

if __name__ == '__main__':
    # Load configuration
    config_path = os.getenv('CONFIG_PATH', 'config/config.yaml')
    config = Config(config_path)

    # Create Flask app
    app = create_app(config)

    # Get Flask configuration from environment
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_ENV', 'production') == 'development'

    logging.info(f"Starting CI Audit API server on {host}:{port}")

    # Run the app
    app.run(host=host, port=port, debug=debug)
