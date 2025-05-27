#!/usr/bin/env python3
import os
from aws_cdk import App, Environment
from BlueGreenCanaryPipelineStack import BlueGreenCanaryDemoStack  # 这里确认你的 Stack 类在哪个文件，类名

app = App()

BlueGreenCanaryDemoStack(
    app,
    "BlueGreenCanaryPipelineStack",  # 这里是 stack 名字，可自定义
    env=Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
)

app.synth()

