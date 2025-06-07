#!/usr/bin/env python3
import os
from aws_cdk import App, Environment
from BlueGreenCanaryPipelineStack_custom2 import PipelineStack


app = App()

PipelineStack(
    app,
    "BlueGreenCanaryPipelineStack",
    env=Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
)

app.synth()
