import os
import torch
import torch.nn.functional as F
from torchvision import transforms as T
from PIL import Image
import matplotlib.pyplot as plt
import numpy as np


class ConstructionProgressTracker:
    def __init__(self):
        os.makedirs("image_diffs", exist_ok=True)
        self.image_paths = []
        self.feature_history = []
        self.progress_history = []
        self.current_image_path = None

        self.model = torch.hub.load(
            "pytorch/vision:v0.10.0", "resnet50", pretrained=True
        )
        self.model.eval()

        self.layers = {
            "early": self.model.layer1[-1],
            "mid1": self.model.layer2[-1],
            "mid2": self.model.layer3[-1],
            "late": self.model.layer4[-1],
        }

        self.preprocess = T.Compose(
            [
                T.Resize(256),
                T.CenterCrop(224),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )

    def analyze_image(self, image_path):
        self.current_image_path = image_path
        self.image_paths.append(image_path)

        try:
            image = Image.open(image_path).convert("RGB")
            input_tensor = self.preprocess(image).unsqueeze(0)

            with torch.no_grad():
                features = []

                def hook(module, input, output):
                    spatial_mean = torch.mean(output, dim=[2, 3]).squeeze()
                    spatial_max = torch.amax(output, dim=[2, 3]).squeeze()
                    spatial_std = torch.std(output, dim=[2, 3]).squeeze()
                    channel_stats = torch.cat(
                        [
                            torch.mean(output, dim=1).flatten(),
                            torch.std(output, dim=1).flatten(),
                        ]
                    )
                    features.append(
                        torch.cat(
                            [spatial_mean, spatial_max, spatial_std, channel_stats]
                        )
                    )

                hooks = [
                    layer.register_forward_hook(hook) for layer in self.layers.values()
                ]
                _ = self.model(input_tensor)
                for h in hooks:
                    h.remove()

                combined_features = torch.cat(features)
                feature_importance = F.softmax(torch.abs(combined_features), dim=0)
                weighted_features = combined_features * feature_importance

                prev_features = (
                    self.feature_history[-1] if self.feature_history else None
                )
                baseline_features = (
                    self.feature_history[0] if self.feature_history else None
                )
                self.visualize_differences(
                    image_path, weighted_features, prev_features, baseline_features
                )

                return weighted_features.detach()

        except Exception as e:
            print(f"Error processing image {image_path}: {e}")
            return None

    def calculate_progress(self, features):
        if features is None:
            return None, None

        try:
            self.feature_history.append(features)

            if len(self.feature_history) == 1:
                self.progress_history.append(0.0)
                return 0.0, 0.0

            prev_features = self.feature_history[-2]
            frame_diff = torch.norm(features - prev_features, p=2).item()

            if not hasattr(self, "max_frame_diff"):
                self.max_frame_diff = frame_diff * 1.5

            self.max_frame_diff = max(self.max_frame_diff, frame_diff)
            relative_change = frame_diff / (self.max_frame_diff + 1e-6)

            # Dynamic scaling
            raw_delta = (relative_change**0.6) * 20
            raw_delta = max(0.2, raw_delta)

            # Slowdown as you approach completion
            prev_progress = self.progress_history[-1]
            slowdown_factor = 1.5
            slowdown_multiplier = (1 - (prev_progress / 100)) ** slowdown_factor
            adjusted_delta = raw_delta * slowdown_multiplier

            next_progress = prev_progress + adjusted_delta
            next_progress = min(next_progress, 100.0)
            next_progress = max(prev_progress, next_progress)  # ensure non-regressive

            self.progress_history.append(next_progress)

            print(
                f"Frame diff: {frame_diff:.4f} | Raw Delta: {raw_delta:.2f}% | Adjusted: {adjusted_delta:.2f}% | Progress: {next_progress:.2f}%"
            )

            return next_progress, adjusted_delta

        except Exception as e:
            print(f"Error in progress calculation: {e}")
            return None, None

    def visualize_differences(
        self, current_image_path, features, prev_features=None, baseline_features=None
    ):
        try:
            current_img = Image.open(current_image_path).convert("RGB")
            current_tensor = self.preprocess(current_img)

            # Changed figure size to be wider rather than square
            fig = plt.figure(figsize=(12, 6))

            # Create GridSpec for more control over subplot sizes
            gs = plt.GridSpec(2, 2, width_ratios=[1, 1], height_ratios=[1, 1])

            fig.suptitle(
                f"Analysis of {os.path.basename(current_image_path)}",
                fontsize=16,
                y=0.95,  # Adjust title position
            )

            # Current image
            ax1 = fig.add_subplot(gs[0, 0])
            ax1.imshow(current_img)
            ax1.set_title("Current Image")
            ax1.axis("off")

            # Activation map
            with torch.no_grad():
                activation = None

                def hook(module, input, output):
                    nonlocal activation
                    activation = output.squeeze().mean(dim=0).cpu().numpy()

                handle = self.model.layer4[-1].register_forward_hook(hook)
                _ = self.model(current_tensor.unsqueeze(0))
                handle.remove()

            if activation is not None:
                ax2 = fig.add_subplot(gs[0, 1])
                ax2.imshow(activation, cmap="hot")
                ax2.set_title("Model Attention Heatmap")
                ax2.axis("off")

            # Baseline image and difference
            if self.image_paths:
                baseline_img = Image.open(self.image_paths[0]).convert("RGB")
                ax3 = fig.add_subplot(gs[1, 0])
                ax3.imshow(baseline_img)
                ax3.set_title("Baseline Image")
                ax3.axis("off")

                current_array = np.array(current_img)
                baseline_array = np.array(baseline_img)
                diff = np.abs(current_array - baseline_array)
                ax4 = fig.add_subplot(gs[1, 1])
                ax4.imshow(diff)
                ax4.set_title("Difference from Baseline")
                ax4.axis("off")

            plt.tight_layout()

            # Adjust spacing
            plt.subplots_adjust(
                top=0.9,  # Add space for title
                wspace=0.3,  # Add space between columns
                hspace=0.3,  # Add space between rows
            )

            save_path = os.path.join(
                "image_diffs", f"diff_{os.path.basename(current_image_path)}.png"
            )
            plt.savefig(save_path, bbox_inches="tight", dpi=300)
            plt.close()

        except Exception as e:
            print(f"Error creating difference visualization: {e}")
