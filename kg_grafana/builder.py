from typing import Optional, Sequence

from kubragen import KubraGen
from kubragen.builder import Builder
from kubragen.data import ValueData
from kubragen.exception import InvalidNameError
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
        * - BUILD_SERVICE
          - creates StatefulSet and Services

    .. list-table::
        :header-rows: 1

        * - build item
          - description
        * - BUILDITEM_DEPLOYMENT
          - StatefulSet
        * - BUILDITEM_SERVICE
          - Service

    .. list-table::
        :header-rows: 1

        * - object name
          - description
          - default value
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

    BUILD_SERVICE: TBuild = 'service'

    BUILDITEM_DEPLOYMENT: TBuildItem = 'deployment'
    BUILDITEM_SERVICE: TBuildItem = 'service'

    def __init__(self, kubragen: KubraGen, options: Optional[GrafanaOptions] = None):
        super().__init__(kubragen)
        if options is None:
            options = GrafanaOptions()
        self.options = options

        self.object_names_update({
            'service': self.basename(),
            'deployment': self.basename(),
            'pod-label-app': self.basename(),
        })
        self._namespace = self.option_get('namespace')

    def option_get(self, name: str):
        return self.kubragen.option_root_get(self.options, name)

    def basename(self, suffix: str = ''):
        return '{}{}'.format(self.option_get('basename'), suffix)

    def namespace(self):
        return self._namespace

    def build_names(self) -> Sequence[TBuild]:
        return [self.BUILD_SERVICE]

    def build_names_required(self) -> Sequence[TBuild]:
        return [self.BUILD_SERVICE]

    def builditem_names(self) -> Sequence[TBuildItem]:
        return [
            self.BUILDITEM_DEPLOYMENT,
            self.BUILDITEM_SERVICE,
        ]

    def internal_build(self, buildname: TBuild) -> Sequence[ObjectItem]:
        if buildname == self.BUILD_SERVICE:
            return self.internal_build_service()
        else:
            raise InvalidNameError('Invalid build name: "{}"'.format(buildname))

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
                            'volumeMounts': [{
                                'mountPath': '/var/lib/grafana',
                                'name': 'data',
                            }],
                            'resources': ValueData(value=self.option_get('kubernetes.resources.deployment'), disabled_if_none=True),
                        }],
                        'restartPolicy': 'Always',
                        'volumes': [
                            KDataHelper_Volume.info(base_value={
                                'name': 'data',
                            }, value=self.option_get('kubernetes.volumes.data')),
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
