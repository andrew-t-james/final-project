import os
import torch
from PIL import Image
from torchvision import transforms
from progress_model import ProgressRegressor


def load_model(model_path, device):
    model = ProgressRegressor().to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()
    return model


def infer_sequence(image_folder, model, device, output_csv="predicted_progress.csv"):
    # Prepare transform
    transform = transforms.Compose(
        [
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    # Sort image files
    # Only include construction images (e.g. IMG_####.jpg)
    image_files = sorted(
        [
            f
            for f in os.listdir(image_folder)
            if f.upper().startswith("IMG_")
            and f.lower().endswith((".jpg", ".jpeg", ".png"))
        ]
    )

    prev_progress = torch.tensor([[0.0]], dtype=torch.float32).to(device)
    results = []

    with open(output_csv, "w") as f:
        f.write("image_path,pred_progress ")
        for img_name in image_files:
            img_path = os.path.join(image_folder, img_name)
            img = Image.open(img_path).convert("RGB")
            inp = transform(img).unsqueeze(0).to(device)

            with torch.no_grad():
                pred = model(inp, prev_progress).item()
            pred = max(0.0, min(pred, 100.0))

            results.append((img_name, pred))
            f.write(f"{img_name},{pred:.2f}\n")
            prev_progress = torch.tensor([[pred]], dtype=torch.float32).to(device)
            print(f"{img_name}: {pred:.2f}% complete")

    print(f"Predictions written to {output_csv}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--images", required=True, help="Folder of images to infer sequentially"
    )
    parser.add_argument("--model", required=True, help="Path to trained model .pth")
    parser.add_argument(
        "--output", default="predicted_progress.csv", help="Output CSV file"
    )
    args = parser.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    model = load_model(args.model, device)
    infer_sequence(args.images, model, device, args.output)
