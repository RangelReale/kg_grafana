import copy
import posixpath
import re
from typing import Optional, Sequence, List, Dict, Any
from urllib.request import urlopen

from kubragen import KubraGen
from kubragen.builder import Builder
from kubragen.configfile import ConfigFile, ConfigFileRenderMulti, ConfigFileRender_Yaml, ConfigFileRender_RawStr, \
    ConfigFileRender_Ini, ConfigFileOutput_Dict
from kubragen.data import ValueData
from kubragen.exception import InvalidNameError, InvalidParamError
from kubragen.helper import LiteralStr
from kubragen.kdata import IsKData, KData_Secret, KData_ConfigMap, KData_ConfigMapManual, KData_SecretManual, \
    KData_Value
from kubragen.kdatahelper import KDataHelper_Volume, KDataHelper_Env
from kubragen.merger import Merger
from kubragen.object import ObjectItem, Object
from kubragen.types import TBuild, TBuildItem
from kubragen.util import is_allowed_types

from .configfile import GrafanaConfigFile
from .option import GrafanaOptions, GrafanaDashboardSource_KData, GrafanaDashboardSource, GrafanaDashboardSource_Str, \
    GrafanaDashboardSource_Url, GrafanaDashboardSource_LocalFile, GrafanaDashboardSource_GNet


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
        * - BUILDITEM_CONFIG
          - ConfigMap
        * - BUILDITEM_CONFIG_DASHBOARD
          - ConfigMap with dashboard sources
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
        * - config
          - ConfigMap
          - ```<basename>-config```
        * - config-dashboard
          - ConfigMap
          - ```<basename>-config-dashboard```
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
    configfile: Optional[str]
    _namespace: str

    SOURCE_NAME = 'kg_grafana'

    BUILD_CONFIG = TBuild('config')
    BUILD_SERVICE = TBuild('service')

    BUILDITEM_CONFIG = TBuildItem('config')
    BUILDITEM_CONFIG_DASHBOARD = TBuildItem('config-dashboard')
    BUILDITEM_CONFIG_SECRET = TBuildItem('config-secret')
    BUILDITEM_DEPLOYMENT = TBuildItem('deployment')
    BUILDITEM_SERVICE = TBuildItem('service')

    def __init__(self, kubragen: KubraGen, options: Optional[GrafanaOptions] = None):
        super().__init__(kubragen)
        if options is None:
            options = GrafanaOptions()
        self.options = options
        self.configfile = None

        self._namespace = self.option_get('namespace')

        self.object_names_init({
            'config': self.basename('-config'),
            'config-dashboard': self.basename('-config-dashboard'),
            'config-secret': self.basename('-config-secret'),
            'service': self.basename(),
            'deployment': self.basename(),
            'pod-label-app': self.basename(),
        })

    def option_get(self, name: str):
        return self.kubragen.option_root_get(self.options, name)

    def is_config_provisioning_item(self, item: str) -> bool:
        itemvalue = self.option_get('config.provisioning.{}'.format(item))
        if itemvalue is None or (isinstance(itemvalue, Sequence) and len(itemvalue) == 0):
            return False
        return True

    def basename(self, suffix: str = ''):
        return '{}{}'.format(self.option_get('basename'), suffix)

    def namespace(self):
        return self._namespace

    def build_names(self) -> Sequence[TBuild]:
        return [self.BUILD_CONFIG, self.BUILD_SERVICE]

    def build_names_required(self) -> Sequence[TBuild]:
        return [self.BUILD_CONFIG, self.BUILD_SERVICE]

    def builditem_names(self) -> Sequence[TBuildItem]:
        return [
            self.BUILDITEM_CONFIG,
            self.BUILDITEM_CONFIG_DASHBOARD,
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

    def internal_build_config(self) -> Sequence[ObjectItem]:
        ret: List[ObjectItem] = []

        ret.append(
            Object({
                'apiVersion': 'v1',
                'kind': 'ConfigMap',
                'metadata': {
                    'name': self.object_name('config'),
                    'namespace': self.namespace(),
                },
                'data': {
                    'grafana.ini': LiteralStr(self.configfile_get()),
                },
            }, name=self.BUILDITEM_CONFIG, source=self.SOURCE_NAME, instance=self.basename()),
        )

        if self.option_get('config.dashboards') is not None:
            configd_data = {}

            for dashboard in self.option_get('config.dashboards'):
                if not isinstance(dashboard, GrafanaDashboardSource_KData):
                    configd_data['dashboard-{}-{}.json'.format(dashboard.provider, dashboard.name)] = LiteralStr(self._dashboard_fetch(dashboard))

            ret.append(
                Object({
                    'apiVersion': 'v1',
                    'kind': 'ConfigMap',
                    'metadata': {
                        'name': self.object_name('config-dashboard'),
                        'namespace': self.namespace(),
                    },
                    'data': configd_data,
                }, name=self.BUILDITEM_CONFIG_DASHBOARD, source=self.SOURCE_NAME, instance=self.basename()),
            )

        secret_data = {}

        if not IsKData(self.option_get('config.admin.user')):
            if self.option_get('config.admin.user') is not None:
                secret_data.update({
                    'admin_user': self.kubragen.secret_data_encode(self.option_get('config.admin.user')),
                })

        if not IsKData(self.option_get('config.admin.password')):
            if self.option_get('config.admin.password') is not None:
                secret_data.update({
                    'admin_password': self.kubragen.secret_data_encode(self.option_get('config.admin.password')),
                })

        if self.is_config_provisioning_item('datasources'):
            secret_data['datasources.yaml'] = self.kubragen.secret_data_encode(
                self.configfile_provisioning_get('datasources', 'config.provisioning.datasources'))
        if self.is_config_provisioning_item('plugins'):
            secret_data['plugins.yaml'] = self.kubragen.secret_data_encode(
                self.configfile_provisioning_get('apps', 'config.provisioning.plugins'))
        if self.is_config_provisioning_item('dashboards'):
            secret_data['dashboards.yaml'] = self.kubragen.secret_data_encode(
                self.configfile_provisioning_get('providers', 'config.provisioning.dashboards'))

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
        ret: List[ObjectItem] = []

        extra_volumes = []
        extra_volumemounts = []

        if self.option_get('config.dashboards') is not None:
            # Configure dashboards mounts
            providers: Dict[Any, Any] ={}
            kdata_providers: List[str] = []

            for dashboard in self.option_get('config.dashboards'):
                if not isinstance(dashboard, GrafanaDashboardSource_KData):
                    if dashboard.provider in kdata_providers:
                        raise InvalidParamError('Provider was already used with a KData source')

                    if dashboard.provider not in providers:
                        providers[dashboard.provider] = {
                            'name': 'dashboard-{}'.format(dashboard.provider),
                            'configMap': {
                                'name': self.object_name('config-dashboard'),
                                'items': []
                            }
                        }
                        extra_volumemounts.append({
                            'name': 'dashboard-{}'.format(dashboard.provider),
                            'mountPath': self._dashboard_path(dashboard.provider),
                        })

                    itemkey = 'dashboard-{}-{}.json'.format(dashboard.provider, dashboard.name)
                    if next((k for k in providers[dashboard.provider]['configMap']['items'] if k['key'] == itemkey), None) is not None:
                        raise InvalidParamError('Duplicated name "{}" for provider "{}"'.format(dashboard.name, dashboard.provider))

                    providers[dashboard.provider]['configMap']['items'].append({
                        'key': 'dashboard-{}-{}.json'.format(dashboard.provider, dashboard.name),
                        'path': '{}.json'.format(dashboard.name),
                    })
                else:
                    if not is_allowed_types(dashboard.kdata, [
                        KData_Value, KData_ConfigMap, KData_ConfigMapManual, KData_Secret, KData_SecretManual
                    ]):
                        raise InvalidParamError('Only ConfigMap and Secret KData is allowed')
                    if dashboard.provider in providers:
                        raise InvalidParamError('KData source must be on a separate provider')
                    vname = 'dashboard-{}'.format(dashboard.provider)
                    providers[dashboard.provider] = KDataHelper_Volume.info(base_value={
                        'name': vname,
                    }, value=dashboard.kdata)
                    extra_volumemounts.append({
                        'name': 'dashboard-{}'.format(dashboard.provider),
                        'mountPath': self._dashboard_path(dashboard.provider),
                    })
                    kdata_providers.append(dashboard.provider)

            for prv in providers.values():
                extra_volumes.append(prv)

        ret.extend([
            Object({
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
                                'env': [
                                    KDataHelper_Env.info(base_value={
                                        'name': 'GF_SECURITY_ADMIN_USER',
                                    }, value_if_kdata=self.option_get('config.admin.user'), default_value={
                                        'valueFrom': {
                                            'secretKeyRef': {
                                                'name': self.object_name('config-secret'),
                                                'key': 'admin_user'
                                            }
                                        },
                                    }, disable_if_none=True),
                                    KDataHelper_Env.info(base_value={
                                        'name': 'GF_SECURITY_ADMIN_PASSWORD',
                                    }, value_if_kdata=self.option_get('config.admin.password'), default_value={
                                        'valueFrom': {
                                            'secretKeyRef': {
                                                'name': self.object_name('config-secret'),
                                                'key': 'admin_password'
                                            }
                                        },
                                    }, disable_if_none=True),
                                    ValueData({
                                        'name': 'GF_INSTALL_PLUGINS',
                                        'value': ','.join(self.option_get('config.install_plugins')),
                                    }, enabled=self.option_get('config.install_plugins') is not None and len(self.option_get('config.install_plugins')) > 0),
                                ],
                                'volumeMounts': [
                                    {
                                        'mountPath': '/var/lib/grafana',
                                        'name': 'data',
                                    },
                                    {
                                        'name': 'grafana-config',
                                        'mountPath': '/etc/grafana/grafana.ini',
                                        'subPath': 'grafana.ini',
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
                                    *extra_volumemounts
                                ],
                                'livenessProbe': ValueData(value={
                                    'httpGet': {
                                        'path': '/api/health',
                                        'port': 3000,
                                    },
                                    'initialDelaySeconds': 60,
                                    'timeoutSeconds': 30,
                                    'failureThreshold': 10,
                                }, enabled=self.option_get('config.probes')),
                                'readinessProbe': ValueData(value={
                                    'httpGet': {
                                        'path': '/api/health',
                                        'port': 3000,
                                    },
                                    'initialDelaySeconds': 60,
                                    'timeoutSeconds': 30,
                                }, enabled=self.option_get('config.probes')),
                                'resources': ValueData(value=self.option_get('kubernetes.resources.deployment'), disabled_if_none=True),
                            }],
                            'restartPolicy': 'Always',
                            'volumes': [
                                {
                                    'name': 'grafana-config',
                                    'configMap': {
                                        'name': self.object_name('config'),
                                    },
                                },
                                KDataHelper_Volume.info(base_value={
                                    'name': 'data',
                                }, value=self.option_get('kubernetes.volumes.data')),
                                ValueData(value={
                                    'name': 'provisioning-datasources',
                                    'secret': {
                                        'secretName': self.object_name('config-secret'),
                                        'items': [{
                                            'key': 'datasources.yaml',
                                            'path': 'datasources.yaml',
                                        }]
                                    }
                                }, enabled=self.is_config_provisioning_item('datasources')),
                                ValueData(value={
                                    'name': 'provisioning-plugins',
                                    'secret': {
                                        'secretName': self.object_name('config-secret'),
                                        'items': [{
                                            'key': 'plugins.yaml',
                                            'path': 'plugins.yaml',
                                        }]
                                    }
                                }, enabled=self.is_config_provisioning_item('plugins')),
                                ValueData(value={
                                    'name': 'provisioning-dashboards',
                                    'secret': {
                                        'secretName': self.object_name('config-secret'),
                                        'items': [{
                                            'key': 'dashboards.yaml',
                                            'path': 'dashboards.yaml',
                                        }]
                                    }
                                }, enabled=self.is_config_provisioning_item('dashboards')),
                                *extra_volumes
                            ]
                        }
                    }
                }
            }, name=self.BUILDITEM_DEPLOYMENT, source=self.SOURCE_NAME, instance=self.basename()),
            Object({
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
            }, name=self.BUILDITEM_SERVICE, source=self.SOURCE_NAME, instance=self.basename()),
        ])
        return ret

    def configfile_get(self) -> str:
        if self.configfile is None:
            configfile = self.option_get('config.grafana_config')
            if configfile is None:
                configfile = GrafanaConfigFile()
            if isinstance(configfile, str):
                self.configfile = configfile
            else:
                configfilerender = ConfigFileRenderMulti([
                    ConfigFileRender_Ini(),
                    ConfigFileRender_RawStr()
                ])
                self.configfile = configfilerender.render(configfile.get_value(self))
        return self.configfile

    def configfile_provisioning_get(self, filetype: str, optionname: str) -> str:
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
            if filetype == 'providers':
                newofile = []
                for og in ofile:
                    if 'type' not in og or og['type'] == 'file':
                        # Auto add "options.path" if not set
                        newog = copy.deepcopy(og)
                        if 'options' not in newog or 'path' not in newog['options']:
                            Merger.merge(newog, {
                                'options': {
                                    'path': self._dashboard_path(newog['name']),
                                },
                            })
                        newofile.append(newog)
                    else:
                        newofile.append(og)
                ofile = newofile
            ogfile = {
                'apiVersion': 1,
                filetype: ofile,
            }
            return configfilerender.render(ConfigFileOutput_Dict(ogfile))

    def _dashboard_path(self, name: str):
        return posixpath.join(self.option_get('config.dashboards_path'), name)

    def _dashboard_fetch(self, source: GrafanaDashboardSource):
        if isinstance(source, GrafanaDashboardSource_Str):
            return source.source
        if isinstance(source, GrafanaDashboardSource_Url):
            try:
                with urlopen(source.url) as u:
                    return u.read().decode('utf-8')
            except Exception as e:
                raise InvalidParamError('Error downloading url: {}'.format(str(e))) from e
        if isinstance(source, GrafanaDashboardSource_LocalFile):
            with open(source.filename, mode='r', encoding='utf-8') as f:
                return f.read()
        if isinstance(source, GrafanaDashboardSource_GNet):
            try:
                with urlopen(f'https://grafana.com/api/dashboards/{source.gnetId}/revisions/{source.revision}/download') as u:
                    src = u.read().decode('utf-8')
                    if source.datasource is not None:
                        return re.sub(r'"datasource":.*,', '"datasource": "{}",'.format(source.datasource), src)
                    return src
            except Exception as e:
                raise InvalidParamError('Error downloading url: {}'.format(str(e))) from e
        raise InvalidParamError('Unsupported dashboard source: "{}"'.format(repr(source)))
