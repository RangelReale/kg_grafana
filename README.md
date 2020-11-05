# KubraGen Builder: Grafana

[![PyPI version](https://img.shields.io/pypi/v/kg_grafana.svg)](https://pypi.python.org/pypi/kg_grafana/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/kg_grafana.svg)](https://pypi.python.org/pypi/kg_grafana/)

kg_grafana is a builder for [KubraGen](https://github.com/RangelReale/kubragen) that deploys 
a [Grafana](https://www.grafana.com/) server in Kubernetes.

[KubraGen](https://github.com/RangelReale/kubragen) is a Kubernetes YAML generator library that makes it possible to generate
configurations using the full power of the Python programming language.

* Website: https://github.com/RangelReale/kg_grafana
* Repository: https://github.com/RangelReale/kg_grafana.git
* Documentation: https://kg_grafana.readthedocs.org/
* PyPI: https://pypi.python.org/pypi/kg_grafana

## Example

```python
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

grafana_config.ensure_build_names(grafana_config.BUILD_SERVICE)

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
```

Output:

```text
****** BEGIN FILE: 001-app-namespace.yaml ********
apiVersion: v1
kind: Namespace
metadata:
  name: app-monitoring

****** END FILE: 001-app-namespace.yaml ********
****** BEGIN FILE: 002-grafana.yaml ********
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mygrafana
  namespace: app-monitoring
  labels:
    app: mygrafana
spec:
  selector:
    matchLabels:
      app: mygrafana
  replicas: 1
  template:
    metadata:
      labels:
        app: mygrafana
    spec:
      containers:
      - name: grafana
        image: grafana/grafana:7.2.0
        ports:
        - containerPort: 3000
          protocol: TCP
        env:
        - name: GF_INSTALL_PLUGINS
          value: ''
        volumeMounts:
        - mountPath: /var/lib/grafana
          name: data
        resources:
          requests:
            cpu: 150m
            memory: 300Mi
          limits:
            cpu: 300m
            memory: 450Mi
      restartPolicy: Always
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: grafana-storage-claim
---
apiVersion: v1
kind: Service
metadata:
  name: mygrafana
  namespace: app-monitoring
spec:
  selector:
    app: mygrafana
  ports:
  - port: 80
    protocol: TCP
    targetPort: 3000

****** END FILE: 002-grafana.yaml ********
****** BEGIN FILE: create_gke.sh ********
#!/bin/bash

set -e
kubectl apply -f 001-app-namespace.yaml
kubectl config set-context --current --namespace=app-monitoring
kubectl apply -f 002-grafana.yaml

****** END FILE: create_gke.sh ********
```

## Credits

## Author

Rangel Reale (rangelspam@gmail.com)
