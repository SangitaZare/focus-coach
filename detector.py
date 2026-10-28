"""Detector: the only file that talks to the AI models.

We use two small, pre-trained YOLO models from Ultralytics. Neither needs any
training from us; both download automatically (a few MB) on first run.

    yolo11n-pose.pt   finds people and 17 body keypoints each
                      (nose, eyes, ears, shoulders, elbows, ...)
    yolo11n.pt        finds 80 everyday objects (the COCO dataset),
                      one of which is "cell phone"

The "n" means nano - the smallest, fastest version, so it runs on a normal
laptop CPU without a graphics card.

Everything else in the project works with the plain Observation this file
returns, so swapping YOLO for a different model would only change this file.
"""
from dataclasses import dataclass, field

import numpy as np
from ultralytics import YOLO

from posture import Point

PHONE_CLASS = 67            # "cell phone" in the COCO class list
KEYPOINT_MIN_CONF = 0.5     # below this, treat a keypoint as hidden


@dataclass
class Observation:
    """What the models saw in one frame."""
    person_found: bool = False
    keypoints: list[Point] = field(default_factory=list)
    person_box: tuple[int, int, int, int] | None = None
    phone_boxes: list[tuple[int, int, int, int]] = field(default_factory=list)


class Detector:
    def __init__(self, pose_model: str = "yolo11n-pose.pt",
                 object_model: str = "yolo11n.pt",
                 phone_conf: float = 0.35, image_size: int = 480) -> None:
        self.pose = YOLO(pose_model)
        self.objects = YOLO(object_model)
        self.phone_conf = phone_conf
        self.image_size = image_size

    def observe(self, frame: np.ndarray) -> Observation:
        obs = Observation()
        self._find_person(frame, obs)
        self._find_phones(frame, obs)
        return obs

    def _find_person(self, frame: np.ndarray, obs: Observation) -> None:
        result = self.pose(frame, imgsz=self.image_size, verbose=False)[0]
        if result.boxes is None or len(result.boxes) == 0:
            return

        # If several people are in view, coach the biggest one: the person
        # sitting at the desk is closest to the camera.
        boxes = result.boxes.xyxy.cpu().numpy()
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        i = int(areas.argmax())

        obs.person_found = True
        obs.person_box = tuple(int(v) for v in boxes[i])
        points = result.keypoints.data[i].cpu().numpy()   # 17 rows of (x, y, conf)
        obs.keypoints = [
            (float(x), float(y)) if conf >= KEYPOINT_MIN_CONF else (0.0, 0.0)
            for x, y, conf in points
        ]

    def _find_phones(self, frame: np.ndarray, obs: Observation) -> None:
        result = self.objects(frame, imgsz=self.image_size, classes=[PHONE_CLASS],
                              conf=self.phone_conf, verbose=False)[0]
        obs.phone_boxes = [tuple(int(v) for v in box)
                           for box in result.boxes.xyxy.cpu().numpy()]
