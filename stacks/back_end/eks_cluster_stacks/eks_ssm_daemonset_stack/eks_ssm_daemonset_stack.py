from aws_cdk import aws_eks as _eks
from aws_cdk import core as cdk

from stacks.miztiik_global_args import GlobalArgs


class EksSsmDaemonSetStack(cdk.Stack):
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

        #################################
        #######                   #######
        #######   SSM DaemonSet   #######
        #######                   #######
        #################################

        # Ref: https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/install-ssm-agent-on-amazon-eks-worker-nodes-by-using-kubernetes-daemonset.html
        app_grp_name = "ssm-installer"
        app_grp_label = {"k8s-app": f"{app_grp_name}"}

        app_01_daemonset = {
            "apiVersion": "apps/v1",
            "kind": "DaemonSet",
            "metadata": {
                "name": f"{app_grp_name}",
                "namespace": "default"
            },
            "spec": {
                "selector": {"matchLabels": app_grp_label},
                "template": {
                    "metadata": {"labels": app_grp_label},
                    "spec": {
                        "containers": [
                            {
                                "name": f"{app_grp_name}",
                                "image": "amazonlinux",
                                "command": ["/bin/bash"],
                                "args": [
                                    "-c",
                                    "echo '* * * * * root yum install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm & cat >>/var/log/miztiik.log <<< `date`:ssm_installation_success;rm -rf /etc/cron.d/ssmstart' > /etc/cron.d/ssmstart && /bin/sleep 60m"
                                ],
                                "env":
                                [
                                    {
                                        "name": "Miztiik_Automation",
                                        "value": "True"
                                    }
                                ],
                                "imagePullPolicy": "Always",
                                "securityContext": {
                                    "allowPrivilegeEscalation": True
                                },
                                "volumeMounts": [
                                    {
                                        "mountPath": "/etc/cron.d",
                                        "name": "cronfile"
                                    }
                                ],
                                "terminationMessagePath": "/dev/termination-log",
                                "terminationMessagePolicy": "File"
                            }
                        ],
                        "volumes": [
                            {
                                "name": "cronfile",
                                "hostPath": {
                                    "path": "/etc/cron.d",
                                    "type": "Directory"
                                }
                            }
                        ],
                        "dnsPolicy": "ClusterFirst",
                        "restartPolicy": "Always",
                        "schedulerName": "default-scheduler",
                        "terminationGracePeriodSeconds": 30
                    }
                }
            }
        }

        # apply a kubernetes manifest to the cluster
        app_01_manifest = _eks.KubernetesManifest(
            self,
            "miztSsmAgentInstallerDaemon",
            cluster=eks_cluster,
            manifest=[
                app_01_daemonset
            ]
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
