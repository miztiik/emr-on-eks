from aws_cdk import aws_eks as _eks
from aws_cdk import core as cdk
import yaml
import requests

from stacks.miztiik_global_args import GlobalArgs


class EksMetricsServerStack(cdk.Stack):
    def __init__(
        self,
        scope: cdk.Construct,
        construct_id: str,
        stack_log_level: str,
        eks_cluster,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Add your stack resources below):

        ##################################
        #######                    #######
        #######   Metrics Server   #######
        #######                    #######
        ##################################

        # Ref:
        # 1: https://docs.aws.amazon.com/eks/latest/userguide/metrics-server.html
        # 2: https://github.com/kubernetes-sigs/metrics-server

        metrics_server_manifest_url = "https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml"
        metrics_server_manifest = list(yaml.safe_load_all(
            requests.get(metrics_server_manifest_url).text))

        for i, doc in enumerate(metrics_server_manifest):
            # apply a Metrics Server manifest to the cluster
            _eks.KubernetesManifest(
                self,
                f"miztMetricsServerManifest{str(i)}",
                cluster=eks_cluster,
                manifest=[
                    doc
                ]
            )

        # self.enable_metrics_server

    def enable_metrics_server(self, namespace: str = "tools"):
        metrics_server = self.eks_cluster.add_helm_chart(
            "MetricsServer",
            namespace=namespace,
            chart="metrics-server",
            repository='https://charts.helm.sh/stable',
        )

        ###########################################
        ################# OUTPUTS #################
        ###########################################
        output_0 = cdk.CfnOutput(
            self,
            "AutomationFrom",
            value=f"{GlobalArgs.SOURCE_INFO}",
            description="To know more about this automation stack, check out our github page.",
        )
