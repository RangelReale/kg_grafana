from kubragen import KubraGen
from kubragen.consts import PROVIDER_GOOGLE, PROVIDERSVC_GOOGLE_GKE
from kubragen.object import Object
from kubragen.option import OptionRoot
from kubragen.options import Options
from kubragen.output import OutputProject, OD_FileTemplate, OutputFile_ShellScript, OutputFile_Kubernetes, \
    OutputDriver_Print
from kubragen.provider import Provider

from kg_grafana import GrafanaBuilder, GrafanaOptions

kg = KubraGen(provider=Provider(PROVIDER_GOOGLE, PROVIDERSVC_GOOGLE_GKE), options=Options({
    'namespaces': {
        'mon': 'app-monitoring',
    },
}))

out = OutputProject(kg)

shell_script = OutputFile_ShellScript('create_gke.sh')
out.append(shell_script)

shell_script.append('set -e')

#
# OUTPUTFILE: app-namespace.yaml
#
file = OutputFile_Kubernetes('app-namespace.yaml')

file.append([
    Object({
        'apiVersion': 'v1',
        'kind': 'Namespace',
        'metadata': {
            'name': 'app-monitoring',
        },
    }, name='ns-monitoring', source='app', instance='app')
])

out.append(file)
shell_script.append(OD_FileTemplate(f'kubectl apply -f ${{FILE_{file.fileid}}}'))

shell_script.append(f'kubectl config set-context --current --namespace=app-monitoring')

#
# SETUP: grafana
#
grafana_config = GrafanaBuilder(kubragen=kg, options=GrafanaOptions({
    'namespace': OptionRoot('namespaces.mon'),
    'basename': 'mygrafana',
    'config': {
        'service_port': 80,
        'provisioning': {
            'datasources': [{
                'name': 'Prometheus',
                'type': 'prometheus',
                'access': 'proxy',
                'url': 'http://prometheus:9090',
            }, {
                'name': 'Loki',
                'type': 'loki',
                'access': 'proxy',
                'url': 'http://loki:3100',
            }],
        },
    },
    'kubernetes': {
        'volumes': {
            'data': {
                'persistentVolumeClaim': {
                    'claimName': 'grafana-storage-claim'
                }
            }
        },
        'resources': {
            'deployment': {
                'requests': {
                    'cpu': '150m',
                    'memory': '300Mi'
                },
                'limits': {
                    'cpu': '300m',
                    'memory': '450Mi'
                },
            },
        },
    }
}))

grafana_config.ensure_build_names(grafana_config.BUILD_CONFIG, grafana_config.BUILD_SERVICE)


if grafana_config.BUILD_CONFIG in grafana_config.build_names_required():
    #
    # OUTPUTFILE: grafana-config.yaml
    #
    file = OutputFile_Kubernetes('grafana-config.yaml')
    out.append(file)

    file.append(grafana_config.build(grafana_config.BUILD_CONFIG))

    shell_script.append(OD_FileTemplate(f'kubectl apply -f ${{FILE_{file.fileid}}}'))

#
# OUTPUTFILE: grafana.yaml
#
file = OutputFile_Kubernetes('grafana.yaml')
out.append(file)

file.append(grafana_config.build(grafana_config.BUILD_SERVICE))

shell_script.append(OD_FileTemplate(f'kubectl apply -f ${{FILE_{file.fileid}}}'))

#
# Write files
#
out.output(OutputDriver_Print())
# out.output(OutputDriver_Directory('/tmp/build-gke'))
