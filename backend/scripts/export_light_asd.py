"""Export Light-ASD (github.com/Junhua-Liao/Light-ASD, MIT) to ONNX.

Runs only in the ``asd-export`` stage of Dockerfile.worker, the one place torch is
installed. Usage: ``python export_light_asd.py <light-asd checkout> <out.onnx>``.

The exported graph is ``scores = model(audio[1, 4T, 13], video[1, T, 112, 112])``:
MFCC frames at 100/s and grayscale face crops at 25 fps in, one logit per video frame
out (> 0 = speaking), i.e. the repo's ``forward_audio_frontend →
forward_visual_frontend → forward_audio_visual_backend → lossAV`` chain.
"""

import hashlib
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from torch import nn

WEIGHTS = "weight/pretrain_AVA_CVPR.model"
WEIGHTS_SHA256 = "d44bc3ea7baa8e0946fa3921311714a630ed8b90a1928fab0dbe30d918909317"


class Scorer(nn.Module):
    def __init__(self, model: nn.Module, fc: nn.Linear) -> None:
        super().__init__()
        self.model = model
        self.fc = fc

    def forward(self, audio: torch.Tensor, video: torch.Tensor) -> torch.Tensor:
        embed_a = self.model.forward_audio_frontend(audio)
        embed_v = self.model.forward_visual_frontend(video)
        out = self.model.forward_audio_visual_backend(embed_a, embed_v)
        return self.fc(out)[:, 1]


def main(repo: Path, output: Path) -> None:
    weights = repo / WEIGHTS
    digest = hashlib.sha256(weights.read_bytes()).hexdigest()
    if digest != WEIGHTS_SHA256:
        raise SystemExit(f"{WEIGHTS} checksum mismatch: {digest}")

    sys.path.insert(0, str(repo))
    from loss import lossAV
    from model.Model import ASD_Model

    model, loss = ASD_Model(), lossAV()
    state = torch.load(weights, map_location="cpu")
    model.load_state_dict(
        {k[len("model.") :]: v for k, v in state.items() if k.startswith("model.")}
    )
    loss.load_state_dict(
        {k[len("lossAV.") :]: v for k, v in state.items() if k.startswith("lossAV.")}
    )
    # The audio encoder applies MaxPool3d to 4-D tensors (torch treats them as unbatched
    # 3-D), which ONNX can't express. Its kernel is 1 on all but the time axis, so the
    # equivalent MaxPool2d exports cleanly; the check below compares against the original.
    reference = Scorer(model, loss.FC).eval()
    patched = ASD_Model()
    patched.load_state_dict(model.state_dict())
    for name in ("pool1", "pool2"):
        pool = nn.MaxPool2d(kernel_size=(1, 3), stride=(1, 2), padding=(0, 1))
        setattr(patched.audioEncoder, name, pool)
    scorer = Scorer(patched, loss.FC).eval()

    frames = 50
    audio = torch.randn(1, 4 * frames, 13)
    video = torch.randint(0, 255, (1, frames, 112, 112)).float()
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        scorer,
        (audio, video),
        str(output),
        input_names=["audio", "video"],
        output_names=["scores"],
        dynamic_axes={
            "audio": {1: "audio_frames"},
            "video": {1: "frames"},
            "scores": {0: "frames"},
        },
        opset_version=17,
        dynamo=False,
    )

    # The time axis must really be dynamic, and the graph must match torch.
    session = ort.InferenceSession(str(output), providers=["CPUExecutionProvider"])
    for check_frames in (25, 150):
        a = torch.randn(1, 4 * check_frames, 13)
        v = torch.randint(0, 255, (1, check_frames, 112, 112)).float()
        with torch.no_grad():
            expected = reference(a, v).numpy()
        actual = session.run(None, {"audio": a.numpy(), "video": v.numpy()})[0]
        if actual.shape != (check_frames,) or not np.allclose(actual, expected, atol=1e-3):
            raise SystemExit(f"ONNX output differs from torch at T={check_frames}")
    print(f"wrote {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
