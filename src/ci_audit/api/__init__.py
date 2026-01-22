"""Flask API for CI Audit system."""

from flask import Flask, jsonify
from flask_cors import CORS
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
import logging

from ci_audit.database.models import Base
from ci_audit.config import Config

# Global database session
db_session = None


def create_app(config: Config = None):
    """Create and configure the Flask application."""
    app = Flask(__name__, static_folder='static', static_url_path='')

    # Enable CORS for development
    CORS(app)

    # Load configuration
    if config is None:
        config = Config()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Initialize database connection
    init_db(config)

    # Register blueprints
    from ci_audit.api.routes import test_runs, logs, queue, stats
    app.register_blueprint(test_runs.bp)
    app.register_blueprint(logs.bp)
    app.register_blueprint(queue.bp)
    app.register_blueprint(stats.bp)

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500

    # Serve index.html at root
    @app.route('/')
    def index():
        return app.send_static_file('index.html')

    return app


def init_db(config: Config):
    """Initialize database connection."""
    global db_session

    # Get database URL from config (handles both PostgreSQL and SQLite)
    db_url = config.database_url

    engine = create_engine(db_url, pool_size=10, max_overflow=20)
    session_factory = sessionmaker(bind=engine)
    db_session = scoped_session(session_factory)

    # Verify connection
    try:
        connection = engine.connect()
        connection.close()
        logging.info("Database connection established")
    except Exception as e:
        logging.error(f"Failed to connect to database: {e}")
        raise


def get_db_session():
    """Get the database session."""
    return db_session
