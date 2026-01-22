"""GCS HTTP XML API client for accessing Prow test artifacts."""

import logging
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict, Any
from pathlib import Path

from ..utils.http_client import RetryHTTPClient


logger = logging.getLogger(__name__)


class GCSCollector:
    """Client for accessing Google Cloud Storage via HTTP XML API.

    This client uses the public GCS HTTP XML API to access test artifacts
    without requiring authentication for public buckets.
    """

    BASE_URL = "https://storage.googleapis.com"
    XML_NAMESPACE = "{http://doc.s3.amazonaws.com/2006-03-01}"

    def __init__(self, http_client: Optional[RetryHTTPClient] = None):
        """Initialize GCS collector.

        Args:
            http_client: HTTP client for requests (creates default if None)
        """
        self.http_client = http_client or RetryHTTPClient()

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        delimiter: str = "",
        max_results: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """List objects in a GCS bucket.

        Args:
            bucket: GCS bucket name
            prefix: Prefix to filter objects
            delimiter: Delimiter for hierarchical listing (e.g., "/" for directories)
            max_results: Maximum number of results to return

        Returns:
            List of object metadata dictionaries with keys:
            - key: Object path
            - size: Object size in bytes
            - last_modified: Last modification timestamp
            - etag: ETag value
        """
        url = f"{self.BASE_URL}/{bucket}/"
        params = {}

        if prefix:
            params["prefix"] = prefix
        if delimiter:
            params["delimiter"] = delimiter
        if max_results:
            params["max-keys"] = str(max_results)

        try:
            response = self.http_client.get(url, params=params)
            return self._parse_list_response(response.content)
        except Exception as e:
            logger.error(f"Failed to list objects in gs://{bucket}/{prefix}: {e}")
            return []

    def list_prefixes(
        self,
        bucket: str,
        prefix: str = "",
        delimiter: str = "/"
    ) -> List[str]:
        """List prefixes (directories) in a GCS bucket.

        Args:
            bucket: GCS bucket name
            prefix: Prefix to filter
            delimiter: Delimiter for hierarchical listing

        Returns:
            List of prefix strings
        """
        url = f"{self.BASE_URL}/{bucket}/"
        params = {"prefix": prefix, "delimiter": delimiter}

        try:
            response = self.http_client.get(url, params=params)
            return self._parse_prefixes_response(response.content)
        except Exception as e:
            logger.error(f"Failed to list prefixes in gs://{bucket}/{prefix}: {e}")
            return []

    def download_object(
        self,
        bucket: str,
        key: str,
        destination: Optional[Path] = None
    ) -> Optional[bytes]:
        """Download an object from GCS.

        Args:
            bucket: GCS bucket name
            key: Object key (path)
            destination: Optional local file path to save to

        Returns:
            Object content as bytes (if destination is None), otherwise None
        """
        url = f"{self.BASE_URL}/{bucket}/{key}"

        try:
            if destination:
                destination.parent.mkdir(parents=True, exist_ok=True)
                self.http_client.download_file(url, str(destination))
                logger.debug(f"Downloaded gs://{bucket}/{key} to {destination}")
                return None
            else:
                response = self.http_client.get(url)
                logger.debug(f"Downloaded gs://{bucket}/{key} ({len(response.content)} bytes)")
                return response.content
        except Exception as e:
            logger.error(f"Failed to download gs://{bucket}/{key}: {e}")
            return None

    def object_exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists in GCS.

        Args:
            bucket: GCS bucket name
            key: Object key (path)

        Returns:
            True if object exists, False otherwise
        """
        url = f"{self.BASE_URL}/{bucket}/{key}"

        try:
            response = self.http_client.session.head(url, timeout=self.http_client.timeout)
            return response.status_code == 200
        except Exception:
            return False

    def get_object_metadata(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific object.

        Args:
            bucket: GCS bucket name
            key: Object key (path)

        Returns:
            Metadata dictionary or None if object doesn't exist
        """
        url = f"{self.BASE_URL}/{bucket}/{key}"

        try:
            response = self.http_client.session.head(url, timeout=self.http_client.timeout)
            if response.status_code == 200:
                return {
                    'key': key,
                    'size': int(response.headers.get('Content-Length', 0)),
                    'content_type': response.headers.get('Content-Type'),
                    'etag': response.headers.get('ETag'),
                    'last_modified': response.headers.get('Last-Modified'),
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get metadata for gs://{bucket}/{key}: {e}")
            return None

    def _parse_list_response(self, xml_content: bytes) -> List[Dict[str, Any]]:
        """Parse GCS list objects XML response.

        Args:
            xml_content: Raw XML response content

        Returns:
            List of object metadata dictionaries
        """
        objects = []

        try:
            root = ET.fromstring(xml_content)
            ns = self.XML_NAMESPACE

            for contents in root.findall(f".//{ns}Contents"):
                key_elem = contents.find(f"{ns}Key")
                size_elem = contents.find(f"{ns}Size")
                modified_elem = contents.find(f"{ns}LastModified")
                etag_elem = contents.find(f"{ns}ETag")

                if key_elem is not None:
                    obj = {
                        'key': key_elem.text,
                        'size': int(size_elem.text) if size_elem is not None else 0,
                        'last_modified': modified_elem.text if modified_elem is not None else None,
                        'etag': etag_elem.text if etag_elem is not None else None,
                    }
                    objects.append(obj)

        except ET.ParseError as e:
            logger.error(f"Failed to parse GCS XML response: {e}")

        return objects

    def _parse_prefixes_response(self, xml_content: bytes) -> List[str]:
        """Parse GCS list prefixes XML response.

        Args:
            xml_content: Raw XML response content

        Returns:
            List of prefix strings
        """
        prefixes = []

        try:
            root = ET.fromstring(xml_content)
            ns = self.XML_NAMESPACE

            for common_prefix in root.findall(f".//{ns}CommonPrefixes"):
                prefix_elem = common_prefix.find(f"{ns}Prefix")
                if prefix_elem is not None and prefix_elem.text:
                    prefixes.append(prefix_elem.text)

        except ET.ParseError as e:
            logger.error(f"Failed to parse GCS XML response: {e}")

        return prefixes

    def list_job_names(
        self,
        bucket: str,
        base_path: str,
        pr_number: int
    ) -> List[str]:
        """List all job names (job types) for a specific PR.

        Args:
            bucket: GCS bucket name
            base_path: Base path (e.g., "pr-logs/pull/opendatahub-io_opendatahub-operator")
            pr_number: Pull request number

        Returns:
            List of job names (e.g., ["pull-ci-...-e2e", "pull-ci-...-rhoai-e2e"])
        """
        # Path format: pr-logs/pull/opendatahub-io_opendatahub-operator/{PR_NUMBER}/
        prefix = f"{base_path}/{pr_number}/"

        # List "directories" (prefixes) under this path
        prefixes = self.list_prefixes(bucket, prefix, delimiter="/")

        # Extract job names from prefixes
        job_names = []
        for p in prefixes:
            # Remove trailing slash and extract last component (job name)
            job_name = p.rstrip('/').split('/')[-1]
            job_names.append(job_name)

        if job_names:
            # Extract short names for logging
            short_names = [name.split('-')[-1] if '-' in name else name for name in job_names]
            logger.info(f"PR #{pr_number}: Found {len(job_names)} job type(s): {', '.join(short_names)}")
        else:
            logger.warning(f"PR #{pr_number}: No job types found in GCS")

        return job_names

    def list_build_ids(
        self,
        bucket: str,
        base_path: str,
        pr_number: int,
        job_name: str
    ) -> List[str]:
        """List all build IDs for a specific PR and job.

        Args:
            bucket: GCS bucket name
            base_path: Base path (e.g., "pr-logs/pull/opendatahub-io_opendatahub-operator")
            pr_number: Pull request number
            job_name: Prow job name

        Returns:
            List of build IDs (timestamps)
        """
        # Path format: pr-logs/pull/opendatahub-io_opendatahub-operator/{PR_NUMBER}/{JOB_NAME}/
        prefix = f"{base_path}/{pr_number}/{job_name}/"

        # List "directories" (prefixes) under this path
        prefixes = self.list_prefixes(bucket, prefix, delimiter="/")

        # Extract build IDs from prefixes
        build_ids = []
        for p in prefixes:
            # Remove trailing slash and extract last component
            build_id = p.rstrip('/').split('/')[-1]
            build_ids.append(build_id)

        logger.debug(f"Found {len(build_ids)} build(s) for PR #{pr_number} job {job_name}")
        return build_ids

    def get_build_artifacts(
        self,
        bucket: str,
        base_path: str,
        pr_number: int,
        job_name: str,
        build_id: str
    ) -> Dict[str, Optional[bytes]]:
        """Download all standard artifacts for a build.

        Args:
            bucket: GCS bucket name
            base_path: Base path
            pr_number: Pull request number
            job_name: Prow job name
            build_id: Build ID

        Returns:
            Dictionary mapping artifact names to their content (bytes)
        """
        build_path = f"{base_path}/{pr_number}/{job_name}/{build_id}"

        artifacts = {
            'started.json': None,
            'finished.json': None,
            'prowjob.json': None,
            'build-log.txt': None,
        }

        # Download metadata files
        for artifact_name in ['started.json', 'finished.json', 'prowjob.json', 'build-log.txt']:
            key = f"{build_path}/{artifact_name}"
            content = self.download_object(bucket, key)
            if content:
                artifacts[artifact_name] = content

        # List and download junit XML files
        junit_prefix = f"{build_path}/artifacts/"
        junit_objects = self.list_objects(bucket, prefix=junit_prefix)

        for obj in junit_objects:
            if obj['key'].endswith('.xml') and 'junit' in obj['key'].lower():
                content = self.download_object(bucket, obj['key'])
                if content:
                    # Use just the filename as the key
                    filename = obj['key'].split('/')[-1]
                    artifacts[f"junit:{filename}"] = content

        return artifacts

    def download_e2e_log(
        self,
        bucket: str,
        base_path: str,
        pr_number: int,
        job_name: str,
        build_id: str,
        output_path: Path
    ) -> bool:
        """Download e2e test execution log to filesystem.

        This downloads the detailed test execution log (not the ci-operator log)
        which contains fail-fast diagnostics, deletion recovery diagnostics, and
        all test output.

        Args:
            bucket: GCS bucket name
            base_path: Base path
            pr_number: Pull request number
            job_name: Prow job name
            build_id: Build ID
            output_path: Filesystem path to save log

        Returns:
            True if log was downloaded successfully, False otherwise
        """
        # Try multiple possible locations for e2e test logs
        # Different job types have different artifact directory structures
        possible_paths = [
            # Main e2e job location
            f"{base_path}/{pr_number}/{job_name}/{build_id}/artifacts/opendatahub-operator-e2e/e2e/build-log.txt",
            # RHOAI e2e job location
            f"{base_path}/{pr_number}/{job_name}/{build_id}/artifacts/opendatahub-operator-rhoai-e2e/rhoai-e2e/build-log.txt",
            # Hypershift e2e job location
            f"{base_path}/{pr_number}/{job_name}/{build_id}/artifacts/opendatahub-operator-e2e-hypershift/e2e/build-log.txt",
        ]

        for gcs_path in possible_paths:
            try:
                content = self.download_object(bucket, gcs_path)
                if content:
                    # Create parent directory if it doesn't exist
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    # Write log content to file
                    output_path.write_bytes(content)
                    logger.info(f"Downloaded e2e log to {output_path} ({len(content)} bytes)")
                    return True
            except Exception as e:
                logger.debug(f"Failed to download from {gcs_path}: {e}")
                continue

        logger.warning(f"No e2e log found for build {build_id} at any expected location")
        return False
