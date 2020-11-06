import unittest

from kubragen import KubraGen
from kubragen.jsonpatch import FilterJSONPatches_Apply, ObjectFilter, FilterJSONPatch
from kubragen.provider import Provider_Generic

from kg_grafana import GrafanaBuilder, GrafanaOptions


class TestBuilder(unittest.TestCase):
    def setUp(self):
        self.kg = KubraGen(provider=Provider_Generic())

    def test_empty(self):
        grafana_config = GrafanaBuilder(kubragen=self.kg)
        self.assertEqual(grafana_config.object_name('service'), 'grafana')
        self.assertEqual(grafana_config.object_name('deployment'), 'grafana')

    def test_basedata(self):
        grafana_config = GrafanaBuilder(kubragen=self.kg, options=GrafanaOptions({
            'namespace': 'myns',
            'basename': 'mygrafana',
            'kubernetes': {
                'volumes': {
                    'data': {
                        'emptyDir': {},
                    }
                }
            }
        }))
        self.assertEqual(grafana_config.object_name('service'), 'mygrafana')
        self.assertEqual(grafana_config.object_name('deployment'), 'mygrafana')

        FilterJSONPatches_Apply(items=grafana_config.build(grafana_config.BUILD_SERVICE), jsonpatches=[
            FilterJSONPatch(filters=ObjectFilter(names=[grafana_config.BUILDITEM_SERVICE]), patches=[
                {'op': 'check', 'path': '/metadata/name', 'cmp': 'equals', 'value': 'mygrafana'},
                {'op': 'check', 'path': '/metadata/namespace', 'cmp': 'equals', 'value': 'myns'},
            ]),
        ])
