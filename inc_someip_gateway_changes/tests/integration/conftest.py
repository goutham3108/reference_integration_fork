# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************

"""
Pytest configuration and fixtures for integration tests.
"""

import pytest
from typing import Generator
import subprocess
from pathlib import Path
import os


def _stop_process(process: subprocess.Popen, name: str) -> None:
    """Terminate a process and force-kill if it does not exit promptly."""
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture(scope="class")
def someipd_config() -> Path:
    """Provide SOME/IP configuration parameters."""
    return Path("tests/integration/vsomeip-gateway-services.json")


@pytest.fixture(scope="class")
def someipd(someipd_config) -> Generator[None, None, None]:
    """Start someipd before tests and stop it after."""
    someipd = subprocess.Popen(
        [
            "score/someipd/someipd",
            "--configuration",
            str(Path("score/config/mw_someip_config.bin").absolute()),
        ],
        env={**os.environ, "VSOMEIP_CONFIGURATION": str(someipd_config.absolute())},
    )
    yield
    _stop_process(someipd, "someipd")


@pytest.fixture(scope="class")
def gatewayd(someipd) -> Generator[None, None, None]:
    """Start gatewayd after someipd so SOCom IPC subscribers are present."""
    gatewayd = subprocess.Popen(
        [
            "score/gatewayd/gatewayd",
            "--configuration",
            str(Path("score/config/mw_someip_config.bin").absolute()),
            "--service_instance_manifest",
            str(Path("score/gatewayd/etc/mw_com_config.json").absolute()),
        ]
    )
    yield
    _stop_process(gatewayd, "gatewayd")


@pytest.fixture(scope="class")
def tire_pressure_publisher_config() -> Path:
    """Provide the VSOMEIP configuration for the tire-pressure example."""
    return Path("tests/integration/vsomeip-gateway-services.json")


@pytest.fixture(scope="class")
def tire_pressure_publisher(gatewayd, tire_pressure_publisher_config) -> Generator[None, None, None]:
    """Start the tire-pressure SOME/IP publisher."""
    publisher = subprocess.Popen(
        ["tests/integration/tire_pressure_publisher/tire_pressure_publisher"],
        env={**os.environ, "VSOMEIP_CONFIGURATION": str(tire_pressure_publisher_config.absolute())},
    )
    yield
    _stop_process(publisher, "tire_pressure_publisher")


@pytest.fixture(scope="class")
def tire_pressure_consumer_output(gatewayd, tire_pressure_publisher) -> str:
    """Run the tire-pressure consumer example until it receives a sample."""
    consumer = subprocess.Popen(
        [
            "tests/integration/tire_pressure_consumer/tire_pressure_consumer",
            "--configuration",
            str(Path("score/gatewayd/etc/mw_com_config.json").absolute()),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        output, _ = consumer.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        consumer.kill()
        output, _ = consumer.communicate()
        pytest.fail(f"tire_pressure_consumer timed out. Output:\n{output}")

    if consumer.returncode != 0:
        pytest.fail(f"tire_pressure_consumer failed with exit code {consumer.returncode}. Output:\n{output}")

    return output


@pytest.fixture(scope="class")
def headlight_publisher_config() -> Path:
    """Provide the VSOMEIP configuration for the headlight example."""
    return Path("tests/integration/vsomeip-gateway-services.json")


@pytest.fixture(scope="class")
def headlight_publisher(gatewayd, headlight_publisher_config) -> Generator[None, None, None]:
    """Start the headlight SOME/IP publisher."""
    publisher = subprocess.Popen(
        ["tests/integration/headlight_publisher/headlight_publisher"],
        env={**os.environ, "VSOMEIP_CONFIGURATION": str(headlight_publisher_config.absolute())},
    )
    yield
    _stop_process(publisher, "headlight_publisher")


@pytest.fixture(scope="class")
def headlight_consumer_output(gatewayd, headlight_publisher) -> str:
    """Run the headlight consumer example until it receives a sample."""
    consumer = subprocess.Popen(
        [
            "tests/integration/headlight_consumer/headlight_consumer",
            "--configuration",
            str(Path("score/gatewayd/etc/mw_com_config.json").absolute()),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        output, _ = consumer.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        consumer.kill()
        output, _ = consumer.communicate()
        pytest.fail(f"headlight_consumer timed out. Output:\n{output}")

    if consumer.returncode != 0:
        pytest.fail(f"headlight_consumer failed with exit code {consumer.returncode}. Output:\n{output}")

    return output


@pytest.fixture(scope="class")
def all_gateway_publishers(gatewayd) -> Generator[None, None, None]:
    """Start both SOME/IP publishers against the shared vSomeIP router."""
    configuration = Path("tests/integration/vsomeip-gateway-services.json").absolute()
    environment = {**os.environ, "VSOMEIP_CONFIGURATION": str(configuration)}
    tire_pressure_publisher = subprocess.Popen(
        ["tests/integration/tire_pressure_publisher/tire_pressure_publisher"],
        env=environment,
    )
    headlight_publisher = subprocess.Popen(
        ["tests/integration/headlight_publisher/headlight_publisher"],
        env=environment,
    )
    yield
    _stop_process(headlight_publisher, "headlight_publisher")
    _stop_process(tire_pressure_publisher, "tire_pressure_publisher")


@pytest.fixture(scope="class")
def concurrent_consumer_outputs(all_gateway_publishers) -> tuple[str, str]:
    """Run the two mw::com consumers concurrently until each receives a sample."""
    configuration = str(Path("score/gatewayd/etc/mw_com_config.json").absolute())
    tire_pressure_consumer = subprocess.Popen(
        [
            "tests/integration/tire_pressure_consumer/tire_pressure_consumer",
            "--configuration",
            configuration,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    headlight_consumer = subprocess.Popen(
        [
            "tests/integration/headlight_consumer/headlight_consumer",
            "--configuration",
            configuration,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    consumers = [
        ("tire_pressure_consumer", tire_pressure_consumer),
        ("headlight_consumer", headlight_consumer),
    ]
    outputs: list[str] = []
    for name, consumer in consumers:
        try:
            output, _ = consumer.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            consumer.kill()
            output, _ = consumer.communicate()
            pytest.fail(f"{name} timed out. Output:\n{output}")
        if consumer.returncode != 0:
            pytest.fail(f"{name} failed with exit code {consumer.returncode}. Output:\n{output}")
        outputs.append(output)

    return outputs[0], outputs[1]


# Pytest configuration
def pytest_configure(config: pytest.Config) -> None:
    """Pytest configuration hook."""
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "network: mark test as requiring network access")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Modify test items during collection."""
    for item in items:
        # Auto-mark all tests in this directory as integration tests
        item.add_marker(pytest.mark.integration)
