# Licensed under the Apache License, Version 2.0
# License included at https://github.com/docker/docker-py/blob/master/LICENSE

"""Patch Docker for Python with device-requests."""

from docker.types import base as docker_types_base
from docker.models import containers as docker_models_containers
from docker.types import containers as docker_types_containers
from docker.utils import utils as docker_utils


class DeviceRequest(docker_types_base.DictType):
    """Create a device request to be used with
    :py:meth:`~docker.api.container.ContainerApiMixin.create_host_config`.

    Taken from: https://github.com/docker/docker-py/pull/2471

    Args:

        driver (str): Which driver to use for this device. Optional.
        count (int): Number or devices to request. Optional.
            Set to -1 to request all available devices.
        device_ids (list): List of strings for device IDs. Optional.
            Set either ``count`` or ``device_ids``.
        capabilities (list): List of lists of strings to request
            capabilities. Optional. The global list acts like an OR,
            and the sub-lists are AND. The driver will try to satisfy
            one of the sub-lists.
            Available capabilities for the ``nvidia`` driver can be found
            `here <https://github.com/NVIDIA/nvidia-container-runtime>`_.
        options (dict): Driver-specific options. Optional.
    """

    def __init__(self, **kwargs):
        driver = kwargs.get('driver', kwargs.get('Driver'))
        count = kwargs.get('count', kwargs.get('Count'))
        device_ids = kwargs.get('device_ids', kwargs.get('DeviceIDs'))
        capabilities = kwargs.get('capabilities', kwargs.get('Capabilities'))
        options = kwargs.get('options', kwargs.get('Options'))

        if driver is None:
            driver = ''
        elif not isinstance(driver, docker_types_base.six.string_types):
            raise ValueError('DeviceRequest.driver must be a string')
        if count is None:
            count = 0
        elif not isinstance(count, int):
            raise ValueError('DeviceRequest.count must be an integer')
        if device_ids is None:
            device_ids = []
        elif not isinstance(device_ids, list):
            raise ValueError('DeviceRequest.device_ids must be a list')
        if capabilities is None:
            capabilities = []
        elif not isinstance(capabilities, list):
            raise ValueError('DeviceRequest.capabilities must be a list')
        if options is None:
            options = {}
        elif not isinstance(options, dict):
            raise ValueError('DeviceRequest.options must be a dict')

        super(DeviceRequest, self).__init__({
            'Driver': driver,
            'Count': count,
            'DeviceIDs': device_ids,
            'Capabilities': capabilities,
            'Options': options
        })

    @property
    def driver(self):
        return self['Driver']

    @driver.setter
    def driver(self, value):
        self['Driver'] = value

    @property
    def count(self):
        return self['Count']

    @count.setter
    def count(self, value):
        self['Count'] = value

    @property
    def device_ids(self):
        return self['DeviceIDs']

    @device_ids.setter
    def device_ids(self, value):
        self['DeviceIDs'] = value

    @property
    def capabilities(self):
        return self['Capabilities']

    @capabilities.setter
    def capabilities(self, value):
        self['Capabilities'] = value

    @property
    def options(self):
        return self['Options']

    @options.setter
    def options(self, value):
        self['Options'] = value


class _HostConfig(docker_types_containers.HostConfig):
    """
    Docker host configuration.

    Taken from: https://github.com/docker/docker-py/pull/2471
    """

    def __init__(self, version, *, device_requests=None, **kwargs):
        super().__init__(version, **kwargs)

        if device_requests is not None:
            if docker_utils.version_lt(version, '1.40'):
                raise docker_types_containers.host_config_version_error(
                    'device_requests', '1.40'
                )
            if not isinstance(device_requests, list):
                raise docker_types_containers.host_config_type_error(
                    'device_requests', device_requests, 'list'
                )
            self['DeviceRequests'] = []
            for req in device_requests:
                if not isinstance(req, DeviceRequest):
                    req = DeviceRequest(**req)
                self['DeviceRequests'].append(req)


docker_models_containers.RUN_HOST_CONFIG_KWARGS.insert(
    docker_models_containers.RUN_HOST_CONFIG_KWARGS.index('devices') + 1,
    'device_requests',
)
docker_types_containers.HostConfig = _HostConfig
docker_models_containers.HostConfig = _HostConfig