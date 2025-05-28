#!/usr/bin/env python3
"""CDK Pipeline deploying a blue/green Windows IIS demo with canary releases.

This script defines:
1. **BlueGreenCanaryDemoStack** – the workload (unchanged from your original example).
2. **BlueGreenCanaryDemoStage** – wraps the workload in a Stage so it can be
   deployed by CDK Pipelines.
3. **PipelineStack** – a self‑mutating CodePipeline that
   * pulls source from GitHub (replace placeholders as needed),
   * synthesises the CDK app, and
   * deploys the stage.

Run   `cdk deploy PipelineStack`   once; subsequent commits automatically trigger
CloudFormation updates via the pipeline.
"""

import os

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stage,
    Environment,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_autoscaling as autoscaling,
    aws_elasticloadbalancingv2 as elbv2,
    aws_rds as rds,
    aws_elasticache as elasticache,
    aws_codedeploy as codedeploy,
    aws_cloudwatch as cloudwatch,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
)
from constructs import Construct
from aws_cdk import pipelines as pipelines  # CDK v2 alias


class BlueGreenCanaryDemoStack(cdk.Stack):
    """Workload stack (unchanged – trimmed for brevity)."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC spanning two AZs
        vpc = ec2.Vpc(self, "DemoVPC", max_azs=2)

        # ALB security group – allow inbound HTTP
        alb_sg = ec2.SecurityGroup(
            self, "ALBSecurityGroup", vpc=vpc, allow_all_outbound=True
        )
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))

        # ASG security group – allow HTTP only from ALB
        asg_sg = ec2.SecurityGroup(
            self, "ASGSecurityGroup", vpc=vpc, allow_all_outbound=True
        )
        asg_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(80))

        # Blue & green target groups
        blue_tg = elbv2.ApplicationTargetGroup(
            self,
            "BlueTG",
            vpc=vpc,
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.INSTANCE,
            health_check=elbv2.HealthCheck(path="/", interval=Duration.seconds(30)),
        )

        green_tg = elbv2.ApplicationTargetGroup(
            self,
            "GreenTG",
            vpc=vpc,
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.INSTANCE,
            health_check=elbv2.HealthCheck(path="/", interval=Duration.seconds(30)),
        )

        # Public ALB
        public_alb = elbv2.ApplicationLoadBalancer(
            self,
            "PublicALB",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_sg,
        )

        listener = public_alb.add_listener(
            "Listener", port=80, open=True, default_target_groups=[blue_tg]
        )

        # Windows AMI
        ami = ec2.MachineImage.latest_windows(
            ec2.WindowsVersion.WINDOWS_SERVER_2019_ENGLISH_FULL_BASE
        )

        # UserData installs CodeDeploy agent & IIS
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

        # AutoScalingGroup
        asg = autoscaling.AutoScalingGroup(
            self,
            "WindowsASG",
            vpc=vpc,
            instance_type=ec2.InstanceType("t3.medium"),
            machine_image=ami,
            min_capacity=2,
            max_capacity=2,
            desired_capacity=2,
            security_group=asg_sg,
            associate_public_ip_address=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            user_data=user_data,
            key_name="chark-test",
        )
        asg.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess")
        )
        blue_tg.add_target(asg)

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

        codedeploy.ServerDeploymentGroup(
            self,
            "DeploymentGroup",
            application=app,
            auto_scaling_groups=[asg],
            deployment_config=codedeploy.ServerDeploymentConfig.ONE_AT_A_TIME,
            load_balancers=[
                codedeploy.LoadBalancer.application(blue_tg),
                codedeploy.LoadBalancer.application(green_tg),
            ],
            install_agent=False,  # already installed via UserData
            role=codedeploy_role,
            deployment_group_name="MyIISDeploymentGroup",
            ec2_instance_tags=codedeploy.InstanceTagSet(
                {
                    "Name": ["BlueGreenASG"],  # ASG 中实例的 Tag
                }
            ),
            # ✅ 启用 GitHub 源
            deployment_style=codedeploy.DeploymentStyle.with_traffic_control(),
        )

        # CloudWatch alarm
        cloudwatch.Alarm(
            self,
            "UnhealthyHostsAlarm",
            metric=blue_tg.metrics.unhealthy_host_count(),
            threshold=1,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        )


class BlueGreenCanaryDemoStage(Stage):
    """Wrap the workload stack in a stage so it can be added to the pipeline."""

    def __init__(self, scope: Construct, construct_id: str, *, env: Environment) -> None:
        super().__init__(scope, construct_id, env=env)

        BlueGreenCanaryDemoStack(self, "BlueGreenStack", env=env)


class PipelineStack(cdk.Stack):
    """Self‑mutating CDK Pipeline."""

    def __init__(self, scope: Construct, construct_id: str, *, env: Environment) -> None:
        super().__init__(scope, construct_id, env=env)

        # --- Source configuration ------------------------------------------------
        # Replace <OWNER>/<REPO> and secret name to match your GitHub settings.
        source = pipelines.CodePipelineSource.git_hub(
            "czmng/test-cloudfomation",  # e.g. "my‑org/blue‑green‑demo"
            "main",
            authentication=cdk.SecretValue.secrets_manager("github-token"),
        )

        artifact_bucket_name = "app-pipeline-2025-23"
        s3_key = "app.zip"
        # --- Synth step ----------------------------------------------------------
        synth = pipelines.ShellStep(
            "Synth",
            input=source,
            commands=[
                "npm install -g aws-cdk",  # CDK CLI
                "python -m pip install -r requirements.txt",  # project deps
                "cdk synth",  # produces CloudAssembly in cdk.out
                "powershell Compress-Archive -Path my-webapp/* -DestinationPath app.zip",
                # 上传 app.zip 到 S3
                f"aws s3 cp app.zip s3://{artifact_bucket_name}/app.zip",
            ],
        )

        # --- Pipeline ------------------------------------------------------------
        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            synth=synth,
            cross_account_keys=False,  # simplify demo
        )

        # --- Deploy Stage --------------------------------------------------------
        deploy_env = Environment(
            account=os.getenv("CDK_DEFAULT_ACCOUNT"),
            region=os.getenv("CDK_DEFAULT_REGION"),
        )
        deploy_stage = BlueGreenCanaryDemoStage(
            self, "Prod", env=deploy_env
        )
        pipeline.add_stage(deploy_stage)
        deploy_step = pipelines.ShellStep(
            "TriggerCodeDeploy",
            commands=[
                f"aws deploy create-deployment "
                f"--application-name DemoApp "
                f"--deployment-group-name MyIISDeploymentGroup "
                f"--s3-location bucket={artifact_bucket_name},key={s3_key},bundleType=zip"
            ],
            # 这里的 input 选用你 Synth 阶段的输出，确保先上传 ZIP
            input=synth.output,
        )

        test_step = pipelines.ShellStep(
            "TestDeployment",
            commands=[
                # 等待一会儿，让 CodeDeploy 部署完成（根据你的情况调整时间）
                "echo Waiting 60 seconds for deployment to stabilize...",
                "sleep 60",
                # 访问 ALB 健康检查接口（换成你的 ALB DNS 或者用环境变量注入）
                "curl -f http://YOUR_ALB_DNS/health.html",
                "echo Deployment test succeeded!",
            ],
            # 这里的 input 可以用 deploy_step.output，但 deploy_step 没有输出，写空即可
        )

        # 把测试步骤放到 CodeDeploy 触发步骤后面
        pipeline.add_stage(deploy_stage).add_post(deploy_step).add_post(test_step)

app = cdk.App()

PipelineStack(
    app,
    "BlueGreenCanaryPipelineStack",
    env=Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
)

app.synth()