#!/usr/bin/env python
# coding: utf-8
# SPDX-License-Identifier: CC0
#
"""Configuration for running pytest"""

import logging
import os
import pathlib

import pytest
import sqlalchemy
from click.testing import CliRunner
from sqlalchemy.engine import URL as DB_URL
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

os.environ.update({"NLDI_CONFIG": "tests/data/sources_config.yml"})


@pytest.fixture
def runner():
    """Runner for cli-related tests."""
    return CliRunner()


@pytest.fixture(scope="session")
def nldi_db_container():
    """
    Database connection for NLDI database.

    This fixture will start a Docker container with a Postgres database
    from the named container image. That image depends on various
    environment variables to configure the database as part of its boot
    sequence. These are all defined using ``.with_env()`` calls here before
    the container is started.

    """
    dc = DockerContainer("ghcr.io/internetofwater/nldi-db:demo")
    dc.with_exposed_ports(5432)
    dc.with_env("POSTGRES_PASSWORD", "changeMe")
    dc.with_env("NLDI_DATABASE_ADDRESS", "localhost")
    dc.with_env("NLDI_DATABASE_NAME", "nldi")
    dc.with_env("NLDI_DB_OWNER_USERNAME", "nldi")
    dc.with_env("NLDI_DB_OWNER_PASSWORD", "changeMe")
    dc.with_env("NLDI_SCHEMA_OWNER_USERNAME", "nldi_schema_owner")
    dc.with_env("NLDI_SCHEMA_OWNER_PASSWORD", "changeMe")
    dc.with_env("NHDPLUS_SCHEMA_OWNER_USERNAME", "nhdplus")
    dc.with_env("NLDI_READ_ONLY_USERNAME", "read_only_user")
    dc.with_env("NLDI_READ_ONLY_PASSWORD", "changeMe")
    dc.with_volume_mapping("data", "/var/lib/postgresql/data", mode="rw")

    dc.start()
    delay = wait_for_logs(dc, "database system is ready to accept connections")
    logging.info(f"Postgres container started in {delay} seconds")

    client = dc.get_docker_client()
    db_info = {
        "user": "nldi",
        "password": "changeMe",
        "host": client.bridge_ip(dc.get_wrapped_container().short_id),
        "port": 5432,
        "dbname": "nldi",
    }
    yield db_info

    dc.stop()


@pytest.fixture(scope="session")
def nldi_db_connect_string(nldi_db_container):
    """
    Database connection string for NLDI database.

    This fixture will provide a connection string for the NLDI database
    that is running in the Docker container. This is useful for testing
    the connection to the database from the test environment.

    """
    # return (
    #     f"postgresql+psycopg2://{nldi_db_container['user']}:{nldi_db_container['password']}"
    #     f"@{nldi_db_container['host']}:{nldi_db_container['port']}/{nldi_db_container['dbname']}"
    # )
    return DB_URL.create(
        "postgresql+psycopg2",
        username=nldi_db_container["user"],
        password=nldi_db_container["password"],
        host=nldi_db_container["host"],
        port=nldi_db_container["port"],
        database=nldi_db_container["dbname"],
    )


@pytest.fixture(scope="session")
def config_yaml() -> pathlib.Path:
    """Sample configuration file for tests."""
    here = pathlib.Path(__file__).parent
    return here / "data" / "sources_config.yml"


@pytest.fixture(scope="session")
def dummy_db_config():
    return {
        "user": "nldi",
        "password": "changeMe",
        "host": "localhost",
        "port": 5432,
        "dbname": "nldi",
    }


@pytest.fixture(scope="session")
def env_update():
    """
    Update environment variables for tests.

    The current YAML parser will substitute environment variables in the
    configuration file. If an undefined variable is encountered, it will
    raise an exception. This fixture will provide the necessary environment
    variables to the test environment so that the configuration file can be
    loaded.

    These values are not especially meaningful -- but provide defaults suitable
    for testing the loading of the config file.

    Note that this fixture does not modify the current environment... it is
    just the dictionary that a test should use to update the environment prior
    to loading the configuration file.

    >>> import os
    >>> os.environ.update(env_update)
    >>> # now load the configuration file
    """
    return dict(
        NLDI_URL="http://localhost/nldi",
        NLDI_DB_HOST="localhost",
        NLDI_DB_PORT="5432",
        NLDI_DB_NAME="nldi",
        NLDI_DB_USERNAME="nldi",
        NLDI_DB_PASSWORD="changeMe",
    )


@pytest.fixture(scope="session")
def global_config(nldi_db_container, config_yaml, env_update):
    """
    Provide global cofiguration definition for tests.

    This is a dict of general config information. It is composed of information from the
    config file, environemnt variables, and the database connection information.
    """
    from nldi.util import load_yaml

    env_update["NLDI_DB_HOST"] = nldi_db_container["host"]
    os.environ.update(env_update)
    _def = load_yaml(config_yaml)
    #    _def["database"] = nldi_db_container
    _def["base_url"] = "http://localhost/nldi"

    return _def


@pytest.fixture(scope="session")
def mock_source():
    """
    Provide a mock source definition for tests.

    This dict should match what is returned from the database when looking up
    source with suffix 'WQP'.
    """
    return {
        "crawler_source_id": 1,
        "source_name": "Water Quality Portal",
        "source_suffix": "WQP",
        "source_uri": "https://www.waterqualitydata.us/data/Station/search?mimeType=geojson&minactivities=1&counts=no",
        "feature_id": "MonitoringLocationIdentifier",
        "feature_name": "MonitoringLocationName",
        "feature_uri": "siteUrl",
        "feature_reach": None,
        "feature_measure": None,
        "ingest_type": "point",
        "feature_type": "varies",
    }


@pytest.fixture(scope="session")
def prod_env_update():
    """
    Update environment variables for tests.

    The current YAML parser will substitute environment variables in the
    configuration file. If an undefined variable is encountered, it will
    raise an exception. This fixture will provide the necessary environment
    variables to the test environment so that the configuration file can be
    loaded.

    These values are not especially meaningful -- but provide defaults suitable
    for testing the loading of the config file.

    Note that this fixture does not modify the current environment... it is
    just the dictionary that a test should use to update the environment prior
    to loading the configuration file.

    >>> import os
    >>> os.environ.update(env_update)
    >>> # now load the configuration file
    """
    secretfile = pathlib.Path(__file__).parent / "data" / "secret.env"
    returnvalue = dict(NLDI_URL="http://localhost/nldi")
    try:
        with open(secretfile, "r") as f:
            lines = f.readlines()
            for line in lines:
                key, value = line.strip().split("=")
                returnvalue[key] = value.strip('"')
    except FileNotFoundError:
        raise FileNotFoundError(f"Secret file not found: {secretfile}")

    return returnvalue


@pytest.fixture(scope="session")
def prod_db_container(prod_env_update) -> dict:
    """Not really a container, but the naming convention is useful to match local testing setup."""
    db_info = {
        "user": prod_env_update["NLDI_DB_USERNAME"],
        "password": prod_env_update["NLDI_DB_PASSWORD"],
        "host": prod_env_update["NLDI_DB_HOST"],
        "port": int(prod_env_update["NLDI_DB_PORT"]),
        "dbname": prod_env_update["NLDI_DB_NAME"],
    }
    return db_info


@pytest.fixture
def prod_db_connect_string(prod_db_container) -> str:
    return DB_URL.create(
        "postgresql+psycopg2",
        username=prod_db_container["user"],
        password=prod_db_container["password"],
        host=prod_db_container["host"],
        port=prod_db_container["port"],
        database=prod_db_container["dbname"],
    )


@pytest.fixture(scope="session")
def prod_global_config(prod_db_container, config_yaml, prod_env_update):
    """
    Provide global cofiguration definition for tests.

    This is a dict of general config information. It is composed of information from the
    config file, environemnt variables, and the database connection information.
    """
    from nldi.util import load_yaml

    prod_env_update["NLDI_DB_HOST"] = prod_db_container["host"]
    os.environ.update(prod_env_update)
    _def = load_yaml(config_yaml)
    #    _def["database"] = nldi_db_container
    _def["base_url"] = "http://localhost/nldi"

    return _def
