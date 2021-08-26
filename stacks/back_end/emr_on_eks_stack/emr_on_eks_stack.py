from aws_cdk import aws_eks as _eks
from aws_cdk import aws_ec2 as _ec2
from aws_cdk import aws_iam as _iam
from aws_cdk import aws_emrcontainers as _emrc
from aws_cdk import aws_logs as _logs
from aws_cdk import core as cdk

import yaml
import requests

from stacks.miztiik_global_args import GlobalArgs


# aws_ec2 as ec2,
# aws_eks as eks, core,
# aws_emrcontainers as _emrc,
# aws__iam. as _iam.,
# aws_logs as logs,
# custom_resources as custom


class EmrOnEksStack(cdk.Stack):
    def __init__(
        self,
        scope: cdk.Construct,
        construct_id: str,
        stack_log_level: str,
        stack_uniqueness: str,
        eks_cluster,
        clust_oidc_provider_arn,
        clust_oidc_issuer,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Add your stack resources below):

        #################################
        #######                   #######
        #######   EMR Namespace   #######
        #######                   #######
        #################################

        emr_01_name = "spark"
        self.emr_01_ns_name = f"{emr_01_name}-ns"

        emr_01_ns_manifest = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": f"{self.emr_01_ns_name}",
                        "labels": {
                            "name": f"{self.emr_01_ns_name}",
                            "app": f"{emr_01_name}",
                            "role": "data_aggregator",
                            "project": "emr-on-eks",
                            "owner": "miztiik-automation",
                            "compute_provider": "on_demand",
                            "dept": "engineering",
                            "team": "red-shirts"
                        },
                "annotations": {
                            "contact": "github.com/miztiik"
                        }
            }
        }

        # Create the App 01 (Spark Namespace)
        emr_01_ns = _eks.KubernetesManifest(
            self,
            f"{emr_01_name}-ns",
            cluster=eks_cluster,
            manifest=[
                emr_01_ns_manifest
            ]
        )

        # Enable cluster access for Amazon EMR on EKS
        # Create k8s cluster role for EMR
        # https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/setting-up-cluster-access.html

        emr_01_clust_role_manifest = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "Role",
            "metadata": {"name": "emr-containers", "namespace": f'{self.emr_01_ns_name}'},
            "rules": [
                {"apiGroups": [""], "resources":[
                    "namespaces"], "verbs":["get"]},
                {"apiGroups": [""], "resources":["serviceaccounts", "services", "configmaps", "events", "pods", "pods/log"], "verbs":[
                    "get", "list", "watch", "describe", "create", "edit", "delete", "deletecollection", "annotate", "patch", "label"]},
                {"apiGroups": [""], "resources":["secrets"],
                    "verbs":["create", "patch", "delete", "watch"]},
                {"apiGroups": ["apps"], "resources":["statefulsets", "deployments"], "verbs":[
                    "get", "list", "watch", "describe", "create", "edit", "delete", "annotate", "patch", "label"]},
                {"apiGroups": ["batch"], "resources":["jobs"], "verbs":[
                    "get", "list", "watch", "describe", "create", "edit", "delete", "annotate", "patch", "label"]},
                {"apiGroups": ["extensions"], "resources":["ingresses"], "verbs":[
                    "get", "list", "watch", "describe", "create", "edit", "delete", "annotate", "patch", "label"]},
                {"apiGroups": ["rbac.authorization.k8s.io"], "resources":["roles", "rolebindings"], "verbs":[
                    "get", "list", "watch", "describe", "create", "edit", "delete", "deletecollection", "annotate", "patch", "label"]}
            ]
        }

        emr_01_clust_role = _eks.KubernetesManifest(
            self,
            "emr01ClusterRole",
            cluster=eks_cluster,
            manifest=[
                emr_01_clust_role_manifest]
        )

        # Make sure the namespace is available before creating cluster role
        emr_01_clust_role.node.add_dependency(emr_01_ns)

        # Bind cluster role to user
        emr_01_clust_role_binding_manifest = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {"name": "emr-containers", "namespace": f'{self.emr_01_ns_name}'},
            "subjects": [{"kind": "User", "name": "emr-containers", "apiGroup": "rbac.authorization.k8s.io"}],
            "roleRef": {"kind": "Role", "name": "emr-containers", "apiGroup": "rbac.authorization.k8s.io"}
        }

        emr_01_clust_role_binding = _eks.KubernetesManifest(
            self,
            "emr01ClusterRoleBinding",
            cluster=eks_cluster,
            manifest=[
                emr_01_clust_role_binding_manifest
            ]
        )

        # Make sure the cluster role exists before creating role binding
        emr_01_clust_role_binding.node.add_dependency(emr_01_clust_role)

        #######################################
        #######                         #######
        #######   EMR Execution Role    #######
        #######                         #######
        #######################################

        #######################################
        #######                         #######
        #######   EMR Service Account   #######
        #######                         #######
        #######################################

        # Modify trust policy
        # To make resolution of LHS during runtime, pre built the string.
        oidc_issuer_condition_str = cdk.CfnJson(
            self,
            "ConditionJsonEmr01",
            value={
                f"{clust_oidc_issuer}:sub": f"system:serviceaccount:{self.emr_01_ns_name}:emr-containers-sa-*-*-{self.account}-*"
            }
        )

        emr_01_execution_role = _iam.Role(
            self,
            f"emr01ExecutionRole{stack_uniqueness}",
            assumed_by=_iam.FederatedPrincipal(
                federated=f"{clust_oidc_provider_arn}",
                conditions={"StringLike": oidc_issuer_condition_str},
                assume_role_action="sts:AssumeRoleWithWebIdentity"
            )
        )

        string_aud = cdk.CfnJson(
            self,
            "ConditionJsonAudEmr01",
            value={
                f"{clust_oidc_issuer}:aud": "sts.amazon.com"
            }
        )

        emr_01_execution_role.assume_role_policy.add_statements(
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=["sts:AssumeRoleWithWebIdentity"],
                principals=[_iam.FederatedPrincipal(
                    federated=f"{clust_oidc_provider_arn}",
                    conditions={"StringLike": string_aud}
                )]
            )
        )

        emr_01_execution_role.assume_role_policy.add_statements(
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=["sts:AssumeRole"],
                principals=[
                    _iam.ServicePrincipal(
                        "elasticmapreduce.amazonaws.com")
                ]
            )
        )

        emr_01_execution_role.add_to_policy(
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=[
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:ListBucket"
                ],
                resources=["*"]
            )
        )
        emr_01_execution_role.add_to_policy(
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=[
                    "logs:PutLogEvents",
                    "logs:CreateLogStream",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams"
                ],
                resources=["arn:aws:logs:*:*:*"]
            )
        )

        # managed_policies=[
        #     _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess"),
        #     _iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2FullAccess"),
        #     _iam.ManagedPolicy.from_aws_managed_policy_name("AWSGlueConsoleFullAccess"),
        #     _iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchFullAccess")]

        ######################################
        #######                        #######
        #######   EMR Cluster Server   #######
        #######                        #######
        ######################################

        # EMR virtual cluster
        self.emr_vc = _emrc.CfnVirtualCluster(
            scope=self,
            id="emrVirtualCluster01",
            container_provider=_emrc.CfnVirtualCluster.ContainerProviderProperty(
                id=eks_cluster.cluster_name,
                info=_emrc.CfnVirtualCluster.ContainerInfoProperty(
                    eks_info=_emrc.CfnVirtualCluster.EksInfoProperty(namespace=self.emr_01_ns_name)),
                type="EKS"
            ),
            name="miztiikVirtualEmrCluster01"
        )
        self.emr_vc.node.add_dependency(emr_01_execution_role)
        self.emr_vc.node.add_dependency(emr_01_ns)
        self.emr_vc.node.add_dependency(emr_01_clust_role_binding)

        ###########################################
        ################# OUTPUTS #################
        ###########################################
        output_0 = cdk.CfnOutput(
            self,
            "AutomationFrom",
            value=f"{GlobalArgs.SOURCE_INFO}",
            description="To know more about this automation stack, check out our github page.",
        )

        output_1 = cdk.CfnOutput(
            self,
            "EmrNamespace",
            value=f"{self.emr_01_ns_name}",
            description="EMR Namespace",
        )
        output_2 = cdk.CfnOutput(
            self,
            "EmrExecutionRoleArn",
            value=f"{emr_01_execution_role.role_arn}",
            description="EMR Execution Role Arn",
        )

        output_3 = cdk.CfnOutput(
            self,
            "EmrVirtualClusterId",
            value=f"{self.emr_vc.attr_id}",
            description="EMR Virtual Cluster Id",
        )
