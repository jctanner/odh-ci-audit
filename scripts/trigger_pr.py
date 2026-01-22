#!/usr/bin/env python3
"""Trigger force collection for a specific PR via API."""

import sys
import logging
import requests
import click


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@click.command()
@click.argument('pr_number', type=int)
@click.option('--repo-owner', default='opendatahub-io', help='Repository owner')
@click.option('--repo-name', default='opendatahub-operator', help='Repository name')
@click.option('--api-url', default='http://localhost:5000', help='API base URL')
@click.option('--force/--no-force', default=True, help='Force re-collection even if completed')
def main(pr_number, repo_owner, repo_name, api_url, force):
    """Trigger collection for a PR.

    Examples:

        # Trigger force collection for PR 3048 (default repo)
        python scripts/trigger_pr.py 3048

        # Trigger for different repo
        python scripts/trigger_pr.py 1234 --repo-owner myorg --repo-name myrepo

        # Trigger without force (only if not already completed)
        python scripts/trigger_pr.py 3048 --no-force
    """
    logger.info(f"Triggering collection for PR #{pr_number} ({repo_owner}/{repo_name})")
    logger.info(f"Force: {force}")

    # Make API request
    url = f"{api_url}/api/queue/trigger"
    payload = {
        'pr_number': pr_number,
        'repo_owner': repo_owner,
        'repo_name': repo_name,
        'force': force
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        result = response.json()
        logger.info(f"✓ Success: {result.get('message', 'Collection triggered')}")
        logger.info(f"  Status: {result.get('status', 'unknown')}")

        # Show queue stats
        logger.info("\nFetching queue stats...")
        stats_response = requests.get(f"{api_url}/api/queue/stats", timeout=10)
        stats_response.raise_for_status()
        stats = stats_response.json()

        logger.info(f"  Pending: {stats.get('pending', 0)}")
        logger.info(f"  In Progress: {stats.get('claimed', 0)}")
        logger.info(f"  Completed: {stats.get('completed', 0)}")
        logger.info(f"  Failed: {stats.get('failed', 0)}")

        return 0

    except requests.exceptions.ConnectionError:
        logger.error(f"✗ Error: Could not connect to API at {api_url}")
        logger.error("  Make sure the API server is running (podman-compose up -d api)")
        return 1

    except requests.exceptions.HTTPError as e:
        logger.error(f"✗ HTTP Error: {e}")
        try:
            error_data = response.json()
            logger.error(f"  Message: {error_data.get('error', 'Unknown error')}")
        except:
            pass
        return 1

    except Exception as e:
        logger.error(f"✗ Error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
