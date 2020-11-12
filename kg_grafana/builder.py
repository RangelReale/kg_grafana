from typing import Optional, Sequence

from kubragen import KubraGen
from kubragen.builder import Builder
from kubragen.configfile import ConfigFile, ConfigFileRenderMulti, ConfigFileRender_Yaml, ConfigFileRender_RawStr, \
    ConfigFileOutput_Dict
from kubragen.data import ValueData
from kubragen.exception import InvalidNameError, InvalidParamError
from kubragen.kdatahelper import KDataHelper_Volume
from kubragen.object import ObjectItem, Object
from kubragen.types import TBuild, TBuildItem

from .option import GrafanaOptions


class GrafanaBuilder(Builder):
    """
    Grafana builder.

    .. list-table::
        :header-rows: 1

        * - build
          - description
        * - BUILD_CONFIG
          - creates configurations
        * - BUILD_SERVICE
          - creates deployments and services

    .. list-table::
        :header-rows: 1

        * - build item
          - description
        * - BUILDITEM_CONFIG_SECRET
          - Secret
        * - BUILDITEM_DEPLOYMENT
          - StatefulSet
        * - BUILDITEM_SERVICE
          - Service

    .. list-table::
        :header-rows: 1

        * - object name
          - description
          - default value
        * - config-secret
          - Secret
          - ```<basename>-config-secret```
        * - service
          - Service
          - ```<basename>```
        * - deployment
          - Deployment
          - ```<basename>```
        * - pod-label-all
          - label *app* to be used by selection
          - ```<basename>```
    """
    options: GrafanaOptions
    _namespace: str

    SOURCE_NAME = 'kg_grafana'

    BUILD_CONFIG = TBuild('config')
    BUILD_SERVICE = TBuild('service')

    BUILDITEM_CONFIG_SECRET = TBuildItem('config-secret')
    BUILDITEM_DEPLOYMENT = TBuildItem('deployment')
    BUILDITEM_SERVICE = TBuildItem('service')

    def __init__(self, kubragen: KubraGen, options: Optional[GrafanaOptions] = None):
        super().__init__(kubragen)
        if options is None:
            options = GrafanaOptions()
        self.options = options

        self._namespace = self.option_get('namespace')

        self.object_names_init({
            'service': self.basename(),
            'deployment': self.basename(),
            'pod-label-app': self.basename(),
        })

        if self.is_config_provisioning():
            self.object_names_init({
                'config-secret': self.basename('-config-secret'),
            })

    def option_get(self, name: str):
        return self.kubragen.option_root_get(self.options, name)

    def is_config_provisioning_item(self, item: str) -> bool:
        itemvalue = self.option_get('config.provisioning.{}'.format(item))
        if itemvalue is None or (isinstance(itemvalue, Sequence) and len(itemvalue) == 0):
            return False
        return True

    def is_config_provisioning(self) -> bool:
        return self.is_config_provisioning_item('datasources') or \
               self.is_config_provisioning_item('plugins') or \
               self.is_config_provisioning_item('dashboards')

    def basename(self, suffix: str = ''):
        return '{}{}'.format(self.option_get('basename'), suffix)

    def namespace(self):
        return self._namespace

    def build_names(self) -> Sequence[TBuild]:
        return [self.BUILD_CONFIG, self.BUILD_SERVICE]

    def build_names_required(self) -> Sequence[TBuild]:
        ret = [self.BUILD_SERVICE]
        if self.is_config_provisioning():
            ret.append(self.BUILD_CONFIG)
        return ret

    def builditem_names(self) -> Sequence[TBuildItem]:
        return [
            self.BUILDITEM_CONFIG_SECRET,
            self.BUILDITEM_DEPLOYMENT,
            self.BUILDITEM_SERVICE,
        ]

    def internal_build(self, buildname: TBuild) -> Sequence[ObjectItem]:
        if buildname == self.BUILD_CONFIG:
            return self.internal_build_config()
        elif buildname == self.BUILD_SERVICE:
            return self.internal_build_service()
        else:
            raise InvalidNameError('Invalid build name: "{}"'.format(buildname))

    def configfile_get(self, filetype: str, optionname: str) -> str:
        ofile = self.option_get(optionname)
        if ofile is None:
            raise InvalidParamError('Config file option "{}" is empty'.format(optionname))

        configfilerender = ConfigFileRenderMulti([
            ConfigFileRender_Yaml(),
            ConfigFileRender_RawStr()
        ])
        if isinstance(ofile, ConfigFile):
            return configfilerender.render(ofile.get_value(self))
        elif isinstance(ofile, str):
            return ofile
        else:
            ogfile = {
                'apiVersion': 1,
                filetype: ofile,
            }
            return configfilerender.render(ConfigFileOutput_Dict(ogfile))

    def internal_build_config(self) -> Sequence[ObjectItem]:
        ret = []

        if self.is_config_provisioning():
            secret_data = {}

            if self.is_config_provisioning_item('datasources'):
                secret_data['datasources.yaml'] = self.kubragen.secret_data_encode(
                    self.configfile_get('datasources', 'config.provisioning.datasources'))
            if self.is_config_provisioning_item('plugins'):
                secret_data['plugins.yaml'] = self.kubragen.secret_data_encode(
                    self.configfile_get('apps', 'config.provisioning.plugins'))
            if self.is_config_provisioning_item('dashboards'):
                secret_data['dashboards.yaml'] = self.kubragen.secret_data_encode(
                    self.configfile_get('providers', 'config.provisioning.dashboards'))

            ret.append(Object({
                'apiVersion': 'v1',
                'kind': 'Secret',
                'metadata': {
                    'name': self.object_name('config-secret'),
                    'namespace': self.namespace(),
                },
                'type': 'Opaque',
                'data': secret_data,
            }, name=self.BUILDITEM_CONFIG_SECRET, source=self.SOURCE_NAME, instance=self.basename()))

        return ret

    def internal_build_service(self) -> Sequence[ObjectItem]:
        ret = [Object({
            'apiVersion': 'apps/v1',
            'kind': 'Deployment',
            'metadata': {
                'name': self.object_name('deployment'),
                'namespace': self.namespace(),
                'labels': {
                    'app': self.object_name('pod-label-app'),
                }
            },
            'spec': {
                'selector': {
                    'matchLabels': {
                        'app': self.object_name('pod-label-app'),
                    }
                },
                'replicas': 1,
                'template': {
                    'metadata': {
                        'labels': {
                            'app': self.object_name('pod-label-app'),
                        }
                    },
                    'spec': {
                        'containers': [{
                            'name': 'grafana',
                            'image': self.option_get('container.grafana'),
                            'ports': [{
                                'containerPort': 3000,
                                'protocol': 'TCP'
                            }],
                            'env': [{
                                'name': 'GF_INSTALL_PLUGINS',
                                'value': ','.join(self.option_get('config.install_plugins')),
                            }],
                            'volumeMounts': [
                                {
                                    'mountPath': '/var/lib/grafana',
                                    'name': 'data',
                                },
                                ValueData(value={
                                    'name': 'provisioning-datasources',
                                    'mountPath': '/etc/grafana/provisioning/datasources',
                                    'readOnly': True,
                                }, enabled=self.is_config_provisioning_item('datasources')),
                                ValueData(value={
                                    'name': 'provisioning-plugins',
                                    'mountPath': '/etc/grafana/provisioning/plugins',
                                    'readOnly': True,
                                }, enabled=self.is_config_provisioning_item('plugins')),
                                ValueData(value={
                                    'name': 'provisioning-dashboards',
                                    'mountPath': '/etc/grafana/provisioning/dashboards',
                                    'readOnly': True,
                                }, enabled=self.is_config_provisioning_item('dashboards')),
                            ],
                            'resources': ValueData(value=self.option_get('kubernetes.resources.deployment'), disabled_if_none=True),
                        }],
                        'restartPolicy': 'Always',
                        'volumes': [
                            KDataHelper_Volume.info(base_value={
                                'name': 'data',
                            }, value=self.option_get('kubernetes.volumes.data')),
                            ValueData(value={
                                'name': 'provisioning-datasources',
                                'secret': {
                                    'secretName': self.object_name('config-secret') if self.object_exists('config-secret') else 'UNDEFINED',
                                    'items': [{
                                        'key': 'datasources.yaml',
                                        'path': 'datasources.yaml',
                                    }]
                                }
                            }, enabled=self.is_config_provisioning_item('datasources')),
                            ValueData(value={
                                'name': 'provisioning-plugins',
                                'secret': {
                                    'secretName': self.object_name('config-secret') if self.object_exists('config-secret') else 'UNDEFINED',
                                    'items': [{
                                        'key': 'plugins.yaml',
                                        'path': 'plugins.yaml',
                                    }]
                                }
                            }, enabled=self.is_config_provisioning_item('plugins')),
                            ValueData(value={
                                'name': 'provisioning-dashboards',
                                'secret': {
                                    'secretName': self.object_name('config-secret') if self.object_exists('config-secret') else 'UNDEFINED',
                                    'items': [{
                                        'key': 'dashboards.yaml',
                                        'path': 'dashboards.yaml',
                                    }]
                                }
                            }, enabled=self.is_config_provisioning_item('dashboards')),
                        ]
                    }
                }
            }
        }, name=self.BUILDITEM_DEPLOYMENT, source=self.SOURCE_NAME, instance=self.basename()), Object({
            'apiVersion': 'v1',
            'kind': 'Service',
            'metadata': {
                'name': self.object_name('service'),
                'namespace': self.namespace(),
            },
            'spec': {
                'selector': {
                    'app': self.object_name('pod-label-app')
                },
                'ports': [{
                    'port': self.option_get('config.service_port'),
                    'protocol': 'TCP',
                    'targetPort': 3000
                }]
            }
        }, name=self.BUILDITEM_SERVICE, source=self.SOURCE_NAME, instance=self.basename())]
        return ret
