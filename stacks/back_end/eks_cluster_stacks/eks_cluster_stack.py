from aws_cdk import aws_iam as _iam
from aws_cdk import aws_eks as _eks
from aws_cdk import aws_ec2 as _ec2
from aws_cdk import core as cdk

import yaml
import requests

from stacks.miztiik_global_args import GlobalArgs


class EksClusterStack(cdk.Stack):
    def __init__(
        self,
        scope: cdk.Construct,
        construct_id: str,
        stack_log_level,
        stack_uniqueness: str,
        vpc,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create EKS Cluster Role
        # Apparently Cluster Admin Role should be defined in the scope of the eks cluster stack stack to prevent circular dependencies!?!?
        # https://docs.aws.amazon.com/eks/latest/userguide/getting-started-console.html
        self._eks_cluster_svc_role = _iam.Role(
            self,
            "c_SvcRole",
            assumed_by=_iam.ServicePrincipal(
                "eks.amazonaws.com"),
            managed_policies=[
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKSClusterPolicy"
                ),
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKS_CNI_Policy"
                ),
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKSVPCResourceController"
                )
            ]
        )

        self._eks_node_role = _iam.Role(
            self,
            "c_NodeRole",
            assumed_by=_iam.ServicePrincipal(
                "ec2.amazonaws.com"),
            managed_policies=[
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKSWorkerNodePolicy"
                ),
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEC2ContainerRegistryReadOnly"
                ),
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonEKS_CNI_Policy"
                ),
                _iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ]
        )

        # Allow to use Cloudwatch
        # sa.role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy"))

        c_admin_role = _iam.Role(
            self,
            "c_AdminRole",
            assumed_by=_iam.CompositePrincipal(
                _iam.AccountRootPrincipal(),
                _iam.ServicePrincipal(
                    "ec2.amazonaws.com")
            )
        )
        c_admin_role.add_to_policy(
            _iam.PolicyStatement(
                effect=_iam.Effect.ALLOW,
                actions=[
                    "eks:DescribeCluster"
                ],
                resources=["*"]
            )
        )

        # Create Security Group for EKS Cluster SG
        # eks.connections.allow_to(rds_cluster, ec2.Port.tcp(3306))
        self.eks_cluster_sg = _ec2.SecurityGroup(
            self,
            "eksClusterSG",
            vpc=vpc,
            description="EKS Cluster security group",
            allow_all_outbound=True,
        )
        cdk.Tags.of(self.eks_cluster_sg).add("Name", "eks_cluster_sg")

        # https://docs.aws.amazon.com/eks/latest/userguide/sec-group-reqs.html
        self.eks_cluster_sg.add_ingress_rule(
            peer=self.eks_cluster_sg,
            connection=_ec2.Port.all_traffic(),
            description="Allow incoming within SG"
        )
        ##################################
        ######    CLUSTER NAME   #########
        ##################################
        clust_name = f"c_{stack_uniqueness}_event_processor"

        self.eks_cluster_1 = _eks.Cluster(
            self,
            f"{clust_name}",
            cluster_name=f"{clust_name}",
            version=_eks.KubernetesVersion.V1_20,
            vpc=vpc,
            vpc_subnets=[
                _ec2.SubnetSelection(
                    subnet_type=_ec2.SubnetType.PUBLIC),
                _ec2.SubnetSelection(
                    subnet_type=_ec2.SubnetType.PRIVATE)
            ],
            default_capacity=0,
            masters_role=c_admin_role,
            role=self._eks_cluster_svc_role,
            security_group=self.eks_cluster_sg,
            endpoint_access=_eks.EndpointAccess.PUBLIC
            # endpoint_access=_eks.EndpointAccess.PUBLIC_AND_PRIVATE
        )

        # Setup OIDC Provider
        clust_oidc_provider = _eks.OpenIdConnectProvider(
            self,
            f"{clust_name}_OIDCProvider",
            url=self.eks_cluster_1.cluster_open_id_connect_issuer_url
        )

        self.add_cluster_admin()

        #####################################
        #######                       #######
        #######   Enable EMR on EKS   #######
        #######                       #######
        #####################################

        # Map user to IAM role
        self.emr_svc_role_arn = f"arn:aws:iam::{self.account}:role/AWSServiceRoleForAmazonEMRContainers"
        emr_svc_role = _iam.Role.from_role_arn(
            self, "EmrSvcRole",
            self.emr_svc_role_arn,
            mutable=False
        )
        self.eks_cluster_1.aws_auth.add_role_mapping(
            emr_svc_role, groups=[], username="emr-containers")

        # Adding Node groups
        self.add_on_demand_ng(clust_name, desired_no=3)
        # self.add_spot_ng(clust_name,desired_no=2)
        # self.add_fargate_profile(clust_name, fargate_ns_name="fargate-ns-01", create_fargate_ns=True)

        # We like to use the Kubernetes Dashboard
        # self.enable_dashboard_with_helm()
        # self.enable_dashboard_with_yaml()

        # OIDC Issuer
        self.clust_oidc_issuer = clust_oidc_provider.open_id_connect_provider_issuer
        # OIDC Provider ARN
        self.clust_oidc_provider_arn = clust_oidc_provider.open_id_connect_provider_arn

        ###########################################
        ################# OUTPUTS #################
        ###########################################
        output_0 = cdk.CfnOutput(
            self,
            "AutomationFrom",
            value=f"{GlobalArgs.SOURCE_INFO}",
            description="To know more about this automation stack, check out our github page."
        )

        output_1 = cdk.CfnOutput(
            self,
            "eksClusterAdminRole",
            value=f"{c_admin_role.role_name}",
            description="EKS Cluster Admin Role"
        )

        output_2 = cdk.CfnOutput(
            self,
            "eksClusterSvcRole",
            value=f"{self._eks_cluster_svc_role.role_name}",
            description="EKS Cluster Service Role"
        )

        output_3 = cdk.CfnOutput(
            self,
            "eksClusterOIDCIssuer",
            value=f"{self.clust_oidc_issuer}",
            description="EKS Cluster OIDC Issuer"
        )
        output_4 = cdk.CfnOutput(
            self,
            "eksClusterOIDCProviderArn",
            value=f"{self.clust_oidc_provider_arn}",
            description="EKS Cluster OIDC Issuer Url"
        )

    def add_on_demand_ng(self, clust_name, desired_no=2):
        on_demand_n_g_1 = self.eks_cluster_1.add_nodegroup_capacity(
            f"on_demand_n_g_1_{clust_name}",
            nodegroup_name=f"on_demand_n_g_1_{clust_name}",
            instance_types=[
                # _ec2.InstanceType("t3.medium"),
                # _ec2.InstanceType("t3.large"),
                _ec2.InstanceType("m5.xlarge"),
            ],
            disk_size=20,
            min_size=1,
            max_size=6,
            desired_size=desired_no,
            labels={"app": "miztiik_on_demand_ng",
                    "lifecycle": "on_demand",
                    "compute_provider": "ec2"
                    },
            subnets=_ec2.SubnetSelection(
                subnet_type=_ec2.SubnetType.PUBLIC),
            ami_type=_eks.NodegroupAmiType.AL2_X86_64,
            # remote_access=_eks.NodegroupRemoteAccess(ssh_key_name="eks-ssh-keypair"),
            capacity_type=_eks.CapacityType.ON_DEMAND,
            node_role=self._eks_node_role
            # bootstrap_options={"kubelet_extra_args": "--node-labels=node.kubernetes.io/lifecycle=spot,daemonset=active,app=general --eviction-hard imagefs.available<15% --feature-gates=CSINodeInfo=true,CSIDriverRegistry=true,CSIBlockVolume=true,ExpandCSIVolumes=true"}
        )

    def add_spot_ng(self, clust_name, desired_no=1):
        spot_n_g_1 = self.eks_cluster_1.add_nodegroup_capacity(
            f"spot_n_g_1_{clust_name}",
            nodegroup_name=f"spot_n_g_1_{clust_name}",
            instance_types=[
                _ec2.InstanceType("t3.medium"),
                _ec2.InstanceType("t3.large")
            ],
            disk_size=20,
            min_size=1,
            max_size=6,
            desired_size=desired_no,
            labels={"app": "miztiik_spot_ng",
                    "lifecycle": "spot",
                    "compute_provider": "ec2"
                    },
            subnets=_ec2.SubnetSelection(
                subnet_type=_ec2.SubnetType.PUBLIC),
            ami_type=_eks.NodegroupAmiType.AL2_X86_64,
            capacity_type=_eks.CapacityType.SPOT,
            node_role=self._eks_node_role
            # bootstrap_options={"kubelet_extra_args": "--node-labels=node.kubernetes.io/lifecycle=spot,daemonset=active,app=general --eviction-hard imagefs.available<15% --feature-gates=CSINodeInfo=true,CSIDriverRegistry=true,CSIBlockVolume=true,ExpandCSIVolumes=true"}
        )

    def add_fargate_profile(self, clust_name, fargate_ns_name="fargate-ns-01", create_fargate_ns: bool = True):

        if create_fargate_ns:
            _eks.KubernetesManifest(
                self,
                f"{fargate_ns_name}-01",
                cluster=self.eks_cluster_1,
                manifest=[{
                    "apiVersion": "v1",
                    "kind": "Namespace",
                    "metadata": {
                            "name": f"{fargate_ns_name}",
                            "labels": {
                                "name": f"{fargate_ns_name}"
                            }
                    }
                }]
            )

        # This code block will provision worker nodes with Fargate Profile configuration
        fargate_profile_1 = self.eks_cluster_1.add_fargate_profile(
            f"fargate_profile_01_{clust_name}",
            # fargate_profile_name=f"fargate_profile_01_{clust_name}",
            # FARGATE PRFOFILES ARE IMMUTABLE, TO ALLOW FOR UPDATES,
            # LET US NOT SPECIFY A NAMD AND LET CFN DO ITS JOB
            selectors=[
                _eks.Selector(
                    namespace=f"{fargate_ns_name}",
                    labels={
                        "owner": "miztiik_automation",
                        "compute_provider": "fargate",
                        # "run_on_fargate": "true"
                    }
                )
            ]
        )

    """
    # https://github.com/adamjkeller/cdk-eks-demo/blob/f9181a1362af9a28854fd1631f965884a9b04577/eks_cluster/alb_ingress.py
    # https://github.com/kloia/aws-cdk-samples/blob/69cb2bb45aab23e08d19d5ace24915893fe92360/python/eks-simple-fargate/eks_simple_fargate/alb_ingress.py
    def add_alb_ingress_controller(self):
        # Add ALB ingress controller to EKS
        _alb_chart = eks_cluster.add_helm_chart(
            "ALBChart",
            chart="aws-load-balancer-controller",
            repository="https://aws.github.io/eks-charts",
            release="alb",
            create_namespace=False,
            namespace="kube-system",
            values=loadYamlReplaceVarLocal("../app_resources/alb-values.yaml",
                                           fields={
                                               "{{region_name}}": region,
                                               "{{cluster_name}}": eks_cluster.cluster_name,
                                               "{{vpc_id}}": eks_cluster.vpc.vpc_id
                                           }
                                           )
        )

    def add_lb_ingress_controller(self, name=eks_cluster.cluster_name):
        ingress = cluster.add_helm_chart("LBIngress", chart="aws-load-balancer-controller",
                                release="aws-load-balancer-controller",
                                repository="https://aws.github.io/eks-charts",
                                namespace="kube-system", 
                                values={
                                    "clusterName": clust_name,
                                    "serviceAccount.name": "aws-load-balancer-controller",
                                    "serviceAccount.create": "false"
                                }
                                )

    """

    def add_cluster_admin(self, name="eks-admin"):
        # Add admin privileges so we can sign in to the dashboard as the service account
        sa = self.eks_cluster_1.add_manifest(
            "eks-admin-sa",
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {
                    "name": name,
                    "namespace": "kube-system",
                },
            },
        )
        binding = self.eks_cluster_1.add_manifest(
            "eks-admin-rbac",
            {
                "apiVersion": "rbac.authorization.k8s.io/v1beta1",
                "kind": "ClusterRoleBinding",
                "metadata": {"name": name},
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "ClusterRole",
                    "name": "cluster-admin",
                },
                "subjects": [
                    {
                        "kind": "ServiceAccount",
                        "name": name,
                        "namespace": "kube-system",
                    }
                ],
            },
        )

    # https://docs.aws.amazon.com/eks/latest/userguide/dashboard-tutorial.html
    # https://kubernetes.io/docs/tasks/access-application-cluster/web-ui-dashboard/

    # CleanUp from CLI
    # kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/master/aio/deploy/recommended.yaml
    # kubectl delete deployment kubernetes-dashboard

    def enable_dashboard_with_helm(self, namespace: str = "kubernetes-dashboard"):
        chart = self.eks_cluster_1.add_helm_chart(
            "kubernetes-dashboard",
            namespace=namespace,
            chart="kubernetes-dashboard",
            repository="https://kubernetes.github.io/dashboard",
            values={
                # This must be set to acccess the UI via `kubectl proxy`
                "fullnameOverride": "kubernetes-dashboard",
                "extraArgs": ["--token-ttl=0"],
            },
            wait=True
        )

    def enable_dashboard_with_yaml(self, namespace: str = "kubernetes-dashboard"):
        # Ref:
        # https://kubernetes.io/docs/tasks/access-application-cluster/web-ui-dashboard/

        k8s_dashboard_manifest_url = "https://raw.githubusercontent.com/kubernetes/dashboard/v2.2.0/aio/deploy/recommended.yaml"
        k8s_dashboard_manifest = list(yaml.safe_load_all(
            requests.get(k8s_dashboard_manifest_url).text))

        for i, doc in enumerate(k8s_dashboard_manifest):
            # apply a Metrics Server manifest to the cluster
            _eks.KubernetesManifest(
                self,
                f"miztMetricsServerManifest{str(i)}",
                cluster=self.eks_cluster_1,
                manifest=[
                    doc
                ]
            )
