import os

import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_rds as rds,
    aws_autoscaling as autoscaling,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as elbv2_targets,
    aws_codedeploy as codedeploy,
    aws_s3 as s3,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    Stack,
    Stage,
    Environment,
    RemovalPolicy
)
from constructs import Construct
from aws_cdk import pipelines as cdk_pipelines

# --- Configuration ---
JUMPBOX_KEY_NAME = "chark-test"

CDK_DEFAULT_ACCOUNT = os.getenv("CDK_DEFAULT_ACCOUNT")
CDK_DEFAULT_REGION = os.getenv("CDK_DEFAULT_REGION")
PROD_ENV = Environment(account=CDK_DEFAULT_ACCOUNT, region=CDK_DEFAULT_REGION)


class BlueGreenCanaryDemoStack(Stack):
    """Defines the Production Environment (Prod-VPC)"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.vpc = ec2.Vpc(
            self, "Prod-VPC", max_azs=2, ip_addresses=ec2.IpAddresses.cidr("10.10.0.0/16"),
            subnet_configuration=[
                ec2.SubnetConfiguration(name="Public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24),
                ec2.SubnetConfiguration(name="Private", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS, cidr_mask=24),
                ec2.SubnetConfiguration(name="Isolated", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=28),
            ], nat_gateways=2
        )
        alb_sg = ec2.SecurityGroup(self, "ALB-SG", vpc=self.vpc, description="Allow HTTP traffic to ALB")
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))
        app_sg = ec2.SecurityGroup(self, "App-SG", vpc=self.vpc, description="Allow traffic from ALB to App")
        app_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(80))
        db_sg = ec2.SecurityGroup(self, "DB-SG", vpc=self.vpc, description="Allow traffic from App to DB")
        db_sg.add_ingress_rule(app_sg, ec2.Port.tcp(3306))
        jumpbox_sg = ec2.SecurityGroup(self, "Jumpbox-SG", vpc=self.vpc, description="Allow SSH to Jumpbox")
        jumpbox_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22))
        ssm_role = iam.Role(
            self, "SSM-Role", assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")]
        )
        # self.db_master = rds.DatabaseInstance(
        #     self, "RDS-MySQL-Master", engine=rds.DatabaseInstanceEngine.mysql(version=rds.MysqlEngineVersion.VER_8_0_35),
        #     instance_type=ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.SMALL),
        #     vpc=self.vpc, vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
        #     security_groups=[db_sg], multi_az=True, database_name="prodDB",
        #     credentials=rds.Credentials.from_generated_secret("ProdDBAdmin"),
        # )


        windows_ami = ec2.MachineImage.latest_windows(
            ec2.WindowsVersion.WINDOWS_SERVER_2019_ENGLISH_FULL_BASE
        )

        user_data = ec2.UserData.for_windows()
        user_data.add_commands(
            "mkdir C:\\temp",
            # Download & install CodeDeploy agent
            "Invoke-WebRequest -Uri https://aws-codedeploy-ap-southeast-1.s3.amazonaws.com/latest/codedeploy-agent.msi -OutFile C:\\temp\\codedeploy-agent.msi",
            "Start-Process -FilePath msiexec.exe -ArgumentList '/i \"C:\\temp\\codedeploy-agent.msi\" /quiet' -Wait",
            "Start-Service codedeployagent",
            # Install IIS
            "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"Install-WindowsFeature Web-Server, Web-Mgmt-Tools, Web-Scripting-Tools, Web-Mgmt-Console, Web-Mgmt-Service -IncludeAllSubFeature -IncludeManagementTools\"",
            "Start-Service W3SVC",
        )
        instance_blm = ec2.Instance(
            self, "Instance-Prod-BLM",
            vpc=self.vpc,
            instance_type=ec2.InstanceType("t3.medium"),
            machine_image=windows_ami,
            security_group=app_sg,
            role=ssm_role,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )


        asg_bis = autoscaling.AutoScalingGroup(
            self, "ASG-Prod-BIS",
            vpc=self.vpc,
            instance_type=ec2.InstanceType("t3.medium"),
            machine_image=windows_ami,
            security_group=app_sg,
            role=ssm_role,
            min_capacity=2,
            max_capacity=4,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            user_data=user_data,
        )


        asg_bis_fence = autoscaling.AutoScalingGroup(
            self, "ASG-Prod-BIS-Fence",
            vpc=self.vpc,
            instance_type=ec2.InstanceType("t3.medium"),
            machine_image=windows_ami,
            security_group=app_sg,
            role=ssm_role,
            min_capacity=2,
            max_capacity=4,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            user_data=user_data,
        )


        alb = elbv2.ApplicationLoadBalancer(
            self, "Prod-ALB",
            vpc=self.vpc,
            internet_facing=True,
            security_group=alb_sg,
        )
        listener = alb.add_listener("Listener", port=80)


        tg_bis = elbv2.ApplicationTargetGroup(
            self, "TG-BIS",
            vpc=self.vpc,
            port=80,
            targets=[asg_bis] 
        )
        
    
        tg_bis_fence = elbv2.ApplicationTargetGroup(
            self, "TG-BIS-Fence",
            vpc=self.vpc,
            port=80,
            targets=[asg_bis_fence] 
        )

      
        listener.add_target_groups("DefaultTarget", target_groups=[tg_bis, tg_bis_fence])

      
        linux_ami = ec2.MachineImage.latest_amazon_linux2()
        ec2.Instance(
            self, "Jumpbox",
            vpc=self.vpc,
            instance_type=ec2.InstanceType("t3.nano"),
            machine_image=linux_ami,
            security_group=jumpbox_sg,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            key_name=JUMPBOX_KEY_NAME,
        )
        
        # CodeDeploy application & deployment group (canary)
        app = codedeploy.ServerApplication(self, "CodeDeployApp", application_name="DemoApp")
        codedeploy_role = iam.Role(
            self, "CodeDeployServiceRole", assumed_by=iam.ServicePrincipal("codedeploy.amazonaws.com")
        )
        codedeploy_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2FullAccess")
        )
        codedeploy_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess")
        )

        deployment_group = codedeploy.ServerDeploymentGroup(
            self,
            "DeploymentGroup",
            application=app,
            auto_scaling_groups=[asg_bis],
            deployment_config=codedeploy.ServerDeploymentConfig.ONE_AT_A_TIME,
            load_balancers=[
                codedeploy.LoadBalancer.application(tg_bis),
                codedeploy.LoadBalancer.application(tg_bis_fence),
            ],
            role=codedeploy_role,
        )

        pipeline_role = iam.Role(
            self,
            "WebAppPipelineRole",
            assumed_by=iam.ServicePrincipal("codepipeline.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodePipeline_FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSCodeDeployFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess"),
            ]
        )

        # CodePipeline Artifact Store
        artifact_store = s3.Bucket(
            self,
            "PipelineArtifacts",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Source Artifact
        source_output = codepipeline.Artifact("SourceOutput")

        deployment_bucket = s3.Bucket(
            self,
            "DeploymentBucket",
            bucket_name="app-pipeline-2025-23",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        
        self.deployment_bucket = deployment_bucket



        
        # 创建webapp CodePipeline
        webapp_pipeline = codepipeline.Pipeline(
            self,
            "WebAppPipeline",
            pipeline_name="webapp",
            role=pipeline_role,
            artifact_bucket=artifact_store,
            stages=[
                # Source Stage - 监控S3存储桶
                codepipeline.StageProps(
                    stage_name="Source",
                    actions=[
                        codepipeline_actions.S3SourceAction(
                            action_name="S3Source",
                            bucket=deployment_bucket,
                            bucket_key="app.zip",
                            output=source_output,
                            trigger=codepipeline_actions.S3Trigger.EVENTS,  # 使用CloudWatch Events触发
                        )
                    ]
                ),
                # Deploy Stage - 使用CodeDeploy
                codepipeline.StageProps(
                    stage_name="Deploy",
                    actions=[
                        codepipeline_actions.CodeDeployServerDeployAction(
                            action_name="CodeDeploy",
                            input=source_output,
                            deployment_group=deployment_group,
                        )
                    ]
                )
            ]
        )
class BlueGreenCanaryDemoStage(Stage):
    """Wraps the ProdStack in a stage so it can be deployed by the pipeline."""
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope,construct_id, **kwargs)
        # Instantiate the ProdStack within this stage
        self.workload_stack = BlueGreenCanaryDemoStack(self, "ProductionStack")


class PipelineStack(Stack):
    """Self-mutating CDK Pipeline."""
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Source from GitHub
        source = cdk_pipelines.CodePipelineSource.git_hub(
            "czmng/test-cloudfomation", # <-- IMPORTANT: Change this to your repo
            "custom2",
            authentication=cdk.SecretValue.secrets_manager("github-token"),
        )
        
        # Synth step
        synth = cdk_pipelines.ShellStep(
            "Synth",
            input=source,
            commands=[
                "npm install -g aws-cdk",
                "python -m pip install -r requirements.txt",
                "cdk synth",
            ],
        )

        # The CDK Pipeline
        pipeline = cdk_pipelines.CodePipeline(
            self,
            "ProdInfrastructurePipeline",
            synth=synth,
            cross_account_keys=False,
        )
        deploy_env = Environment(
            account=os.getenv("CDK_DEFAULT_ACCOUNT"),
            region=os.getenv("CDK_DEFAULT_REGION"),
        )
        # Deploy stage: This is where we add our ProdStack (wrapped in ProdStage)
        deploy_stage = BlueGreenCanaryDemoStage(self, "Prod", env=deploy_env)
        pipeline.add_stage(deploy_stage)


app = cdk.App()

# The entry point of our app is now the pipeline itself.
PipelineStack(
    app,
    "BlueGreenCanaryPipelineStack",
    env=Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
)

app.synth()