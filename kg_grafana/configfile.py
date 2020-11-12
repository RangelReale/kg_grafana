from typing import Any, Optional, Mapping, Sequence

from kubragen.configfile import ConfigFileOutput, ConfigFile_Extend, \
    ConfigFileExtensionData, ConfigFileExtension, ConfigFileOutput_DictDualLevel
from kubragen.merger import Merger
from kubragen.option import OptionDef
from kubragen.options import OptionGetter, Options, option_root_get


class GrafanaConfigFileOptions(Options):
    """
    Options for Grafana config file.

    .. list-table::
        :header-rows: 1

        * - option
          - description
          - allowed types
          - default value
        * - config.merge_config
          - extra config to merge to config file
          - Mapping
          - ```{}```
    """
    def define_options(self) -> Optional[Any]:
        """
        Declare the options for the Grafana config file.

        :return: The supported options
        """
        return {
            'config': {
                'merge_config': OptionDef(default_value={}, allowed_types=[Mapping]),
            },
        }


class GrafanaConfigFile(ConfigFile_Extend):
    """
    Grafana main configuration file in INI format.
    """
    options: GrafanaConfigFileOptions

    def __init__(self, options: Optional[GrafanaConfigFileOptions] = None,
                 extensions: Optional[Sequence[ConfigFileExtension]] = None):
        super().__init__(extensions)
        if options is None:
            options = GrafanaConfigFileOptions()
        self.options = options

    def option_get(self, name: str):
        return option_root_get(self.options, name)

    def init_value(self, options: OptionGetter) -> ConfigFileExtensionData:
        ret = ConfigFileExtensionData({
            'analytics': {
                'check_for_updates': 'false',
            },
            'log': {
                'mode': 'console',
            }
        })
        return ret

    def finish_value(self, options: OptionGetter, data: ConfigFileExtensionData) -> ConfigFileOutput:
        if self.option_get('config.merge_config') is not None:
            Merger.merge(data.data, self.option_get('config.merge_config'))
        return ConfigFileOutput_DictDualLevel(data.data)
