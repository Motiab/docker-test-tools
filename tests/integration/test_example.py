import os
import httplib
import logging
import requests

from docker_test_tools.base_test import BaseDockerTest
from docker_test_tools.wiremock import WiremockController
from docker_test_tools.utils import get_curl_health_check


class ExampleTest(BaseDockerTest):
    """Usage example test for docker-test-tools."""

    # [OPTIONAL] User defined health checks, once defined the test setUp will wait for them to pass.
    REQUIRED_HEALTH_CHECKS = [
        get_curl_health_check(service_name='consul.service', url='http://consul.service:8500'),
        get_curl_health_check(service_name='mocked.service', url='http://mocked.service:9999/__admin')
    ]

    # [OPTIONAL] User defined health checks timeout
    CHECKS_TIMEOUT = 60

    def setUp(self):
        """Create a wiremock controller and ad a cleanup for it."""
        super(ExampleTest, self).setUp()

        self.wiremock = WiremockController(url='http://mocked.service:9999')
        self.addCleanup(self.wiremock.reset_mapping)

    def test_services_sanity(self):
        """Validate services are responsive once the test start."""
        logging.info('Validating consul container is responsive')
        self.assertEquals(requests.get('http://consul.service:8500').status_code, httplib.OK)

        logging.info('Validating wiremock container is responsive')
        self.assertEquals(requests.get('http://mocked.service:9999/__admin').status_code, httplib.OK)

    def test_service_down(self):
        """Validate service down scenario."""
        logging.info('Validating consul container is responsive')
        self.assertEquals(requests.get('http://consul.service:8500').status_code, httplib.OK)

        logging.info('Validating consul container is unresponsive while in `container_down` context')
        with self.controller.container_down(name='consul.service'):
            with self.assertRaises(requests.ConnectionError):
                requests.get('http://consul.service:8500')

        logging.info('Validating consul container has recovered and is responsive')
        self.assertEquals(requests.get('http://consul.service:8500').status_code, httplib.OK)

    def test_service_paused(self):
        """Validate service paused scenario."""
        logging.info('Validating consul container is responsive')
        self.assertEquals(requests.get('http://consul.service:8500', timeout=2).status_code, httplib.OK)

        logging.info('Validating consul container is unresponsive while in `container_paused` context')
        with self.controller.container_paused(name='consul.service'):
            with self.assertRaises(requests.Timeout):
                requests.get('http://consul.service:8500', timeout=2)

        logging.info('Validating consul container has recovered and is responsive')
        self.assertEquals(requests.get('http://consul.service:8500', timeout=2).status_code, httplib.OK)

    def test_mocked_service_configuration(self):
        """Validate wiremock service."""
        logging.info('Validating mocked service fail to find `test` endpoint')
        self.assertEquals(requests.post('http://mocked.service:9999/test').status_code, httplib.NOT_FOUND)

        logging.info('Use WiremockController to stub the service `test` endpoint')
        stubs_dir_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'wiremock_stubs')
        self.wiremock.set_mapping_from_dir(stubs_dir_path)

        logging.info('Validating mocked service response on `test` endpoint')
        self.assertEquals(requests.post('http://mocked.service:9999/test').status_code, httplib.OK)

    def test_mocked_service_request_journal(self):
        """Validate wiremock request journal."""
        logging.info('Validating first request reaches the journal')
        requests.post('http://mocked.service:9999/some-unique-request-33452')
        journal = self.wiremock.get_request_journal()
        inner_url = journal[-1]['request']['url']
        self.assertEquals(inner_url, "/some-unique-request-33452")

        logging.info('Validating filtering of specific requests from the journal')
        requests.post('http://mocked.service:9999/test2')
        requests.post('http://mocked.service:9999/test2')
        filtered = self.wiremock.get_matching_requests('/test2')
        self.assertEquals(len(filtered), 2)
        self.assertEquals(filtered[0]['request']['url'], "/test2")
        self.assertEquals(filtered[1]['request']['url'], "/test2")

        logging.info('Validating the deletion of requests from the journal')
        self.wiremock.delete_request_journal()
        journal = self.wiremock.get_matching_requests('/test2')
        self.assertEquals(len(journal), 0)