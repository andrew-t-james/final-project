import torch
import torch.nn as nn
from torchvision import models, transforms


class ProgressRegressor(nn.Module):
    def __init__(self, backbone_name="resnet50", pretrained=True, hidden_dim=256):
        super().__init__()
        # Load pretrained backbone
        backbone = getattr(models, backbone_name)(pretrained=pretrained)
        # Remove classification head
        modules = list(backbone.children())[:-1]  # remove FC
        self.feature_extractor = nn.Sequential(*modules)
        # Regression head: takes features + previous progress
        feat_dim = backbone.fc.in_features
        self.regressor = nn.Sequential(
            nn.Linear(feat_dim + 1, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid(),  # outputs between 0 and 1
        )

    def forward(self, image, prev_progress):
        # image: [B,3,H,W], prev_progress: [B,1]
        f = self.feature_extractor(image)  # [B, feat_dim, 1,1]
        f = f.view(f.size(0), -1)  # [B, feat_dim]
        x = torch.cat([f, prev_progress], dim=1)  # [B, feat_dim+1]
        out = self.regressor(x) * 100.0  # scale to 0-100%
        return out.squeeze(1)  # [B]
