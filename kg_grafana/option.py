from typing import Sequence, Mapping, Any, Optional

from kubragen.configfile import ConfigFile
from kubragen.data import Data
from kubragen.kdata import KData_Secret, KData
from kubragen.kdatahelper import KDataHelper_Volume, KDataHelper_Env
from kubragen.option import OptionDef, OptionDefFormat
from kubragen.options import Options


class GrafanaOptions(Options):
    """
    Options for the Grafana builder.

    .. list-table::
        :header-rows: 1

        * - option
          - description
          - allowed types
          - default value
        * - basename
          - object names prefix
          - str
          - ```grafana```
        * - namespace
          - namespace
          - str
          - ```default```
        * - config |rarr| grafana_config
          - Grafana INI config file
          - str, :class:`kubragen.configfile.ConfigFile`
          - :class:`kg_grafana.GrafanaConfigFile`
        * - config |rarr| install_plugins
          - install plugins
          - Sequence
          - ```[]```
        * - config |rarr| service_port
          - service port
          - int
          - 3000
        * - config |rarr| provisioning |rarr| datasources
          - Grafana datasource provisioning
          - str, Sequence, ConfigFile
          -
        * - config |rarr| provisioning |rarr| plugins
          - Grafana plugins provisioning
          - str, Sequence, ConfigFile
          -
        * - config |rarr| provisioning |rarr| dashboards
          - Grafana dashboards provisioning. ```options.path``` will be set automatically if it is not set
          - str, Sequence, ConfigFile
          -
        * - config |rarr| dashboards
          - Grafana dashboards to pre install
          - :class:`Sequence[GrafanaDashboardSource]`
          -
        * - config |rarr| dashboards_path
          - The root path where dashboards will be installed on the container.
          - ```/var/lib/grafana/dashboards```
          -
        * - config |rarr| admin |rarr| user
          - admin user name
          - str, :class:`KData_Value`, :class:`KData_ConfigMap`, :class:`KData_Secret`
          -
        * - config |rarr| admin |rarr| password
          - admin password
          - str, :class:`KData_Secret`
          -
        * - container |rarr| grafana
          - grafana container image
          - str
          - ```grafana/grafana:<version>```
        * - kubernetes |rarr| volumes |rarr| data
          - Kubernetes data volume
          - Mapping, :class:`KData_Value`, :class:`KData_ConfigMap`, :class:`KData_Secret`
          - ```{'emptyDir': {}}```
        * - kubernetes |rarr| resources |rarr| deployment
          - Kubernetes Deployment resources
          - Mapping
          -
    """
    def define_options(self):
        """
        Declare the options for the Grafana builder.

        :return: The supported options
        """
        return {
            'basename': OptionDef(required=True, default_value='grafana', allowed_types=[str]),
            'namespace': OptionDef(required=True, default_value='default', allowed_types=[str]),
            'config': {
                'grafana_config': OptionDef(allowed_types=[str, ConfigFile]),
                'install_plugins': OptionDef(default_value=[], allowed_types=[Sequence]),
                'service_port': OptionDef(required=True, default_value=3000, allowed_types=[int]),
                'probes': OptionDef(required=True, default_value=False, allowed_types=[bool]),
                'provisioning': {
                    'datasources': OptionDef(allowed_types=[str, Sequence, ConfigFile]),
                    'plugins': OptionDef(allowed_types=[str, Sequence, ConfigFile]),
                    'dashboards': OptionDef(allowed_types=[str, Sequence, ConfigFile]),
                },
                'dashboards': OptionDef(allowed_types=[Sequence]),
                'dashboards_path': OptionDef(required=True, default_value='/var/lib/grafana/dashboards', allowed_types=[str]),
                'admin': {
                    'user': OptionDef(format=OptionDefFormat.KDATA_ENV, allowed_types=[str, *KDataHelper_Env.allowed_kdata()]),
                    'password': OptionDef(format=OptionDefFormat.KDATA_ENV, allowed_types=[str, KData_Secret]),
                },
            },
            'container': {
                'grafana': OptionDef(required=True, default_value='grafana/grafana:7.2.0', allowed_types=[str]),
            },
            'kubernetes': {
                'volumes': {
                    'data': OptionDef(required=True, format=OptionDefFormat.KDATA_VOLUME,
                                      default_value={'emptyDir': {}},
                                      allowed_types=[Mapping, *KDataHelper_Volume.allowed_kdata()]),
                },
                'resources': {
                    'deployment': OptionDef(allowed_types=[Mapping]),
                }
            },
        }


class GrafanaDashboardSource:
    """
    Grafana dashboard source base class.

    :param provider: provider name (must be in config.provisioning.dashboards)
    :param name: item name (will become a filename)
    """
    provider: str
    name: str

    def __init__(self, provider: str, name: str):
        self.provider = provider
        self.name = name


class GrafanaDashboardSource_Str(GrafanaDashboardSource):
    """
    Grafana dashboard source from a raw string.

    :param source: string containing the dashboard source code
    """
    source: str

    def __init__(self, provider: str, name: str, source: str):
        super().__init__(provider, name)
        self.source = source


class GrafanaDashboardSource_KData(GrafanaDashboardSource):
    """
    Grafana dashboard source from a :class:`kubragen.kdata.KData`.

    Use this to load dashboards from other sources, like ConfigMap, Secret, or event PersistentVolumeClaims.

    **WARNING**: this item should be on an exclusive provider, it cannot be mixed with other sources.

    :param kdata: kdata
    """
    kdata: KData

    def __init__(self, provider: str, kdata: KData):
        super().__init__(provider, '')
        self.kdata = kdata


class GrafanaDashboardSource_Url(GrafanaDashboardSource):
    """
    Grafana dashboard source from an url.

    :param url: url to download
    """
    url: str

    def __init__(self, provider: str, name: str, url: str):
        super().__init__(provider, name)
        self.url = url


class GrafanaDashboardSource_LocalFile(GrafanaDashboardSource):
    """
    Grafana dashboard source from a local file.

    :param filename: filename to read
    """
    filename: str

    def __init__(self, provider: str, name: str, filename: str):
        super().__init__(provider, name)
        self.filename = filename


class GrafanaDashboardSource_GNet(GrafanaDashboardSource):
    """
    Grafana dashboard source from GNet (Grafana dashboards site).

    :param gnetId: dashboard id
    :param revision: dashboard revision
    :param datasource: the datasource to use. If None, will keep the default.
    """
    gnetId: int
    revision: int
    datasource: Optional[str]

    def __init__(self, provider: str, name: str, gnetId: int, revision: int, datasource: Optional[str] = None):
        super().__init__(provider, name)
        self.gnetId = gnetId
        self.revision = revision
        self.datasource = datasource


class GrafanaOptions_Default_Resources_Deployment(Data):
    """
    Default option value for:

    ```kubernetes.resources.deployment```
    """
    def is_enabled(self) -> bool:
        return True

    def get_value(self) -> Any:
        return {
            'requests': {
                'cpu': '100m',
                'memory': '128Mi'
            },
            'limits': {
                'cpu': '100m',
                'memory': '128Mi'
            },
        }
