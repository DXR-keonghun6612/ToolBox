from . import dino, convnext, resnet


BACKBONES = (
    dino.DINO | convnext.ConvNeXt | resnet.ResNet
)

BACKBONE_CFGS = (
    dino.DINO_Config | convnext.ConvNeXt_Config | resnet.ResNet_Config
)
