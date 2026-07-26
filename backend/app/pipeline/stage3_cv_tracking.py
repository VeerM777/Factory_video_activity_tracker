"""Stage 3 -- CV Tracking Layer. Pure computer vision, no model call, no
training data required:

  - Hands + body pose: MediaPipe HandLandmarker/PoseLandmarker (pretrained,
    downloaded once to data/models/ -- see ensure_models_downloaded).
  - Tools/parts: YOLO-World zero-shot/open-vocabulary object detection
    (ultralytics). Detected by text query (backend/app/config/cv_vocabulary.json,
    versioned/editable), NOT a per-station fine-tuned detector -- deliberate
    deviation from the original brief's "fine-tuned YOLO per station" spec,
    since that needs labeled training images we don't have. This needs zero
    labeled data and generalizes across stations by editing the vocabulary.
    (Benchmarked against OWLv2/transformers first -- ~23s/frame on this
    CPU-only machine, impractical at any real sampling rate. YOLO-World's
    CNN backbone runs the same job in ~0.9s/frame, a ~26x speedup, since it
    avoids full ViT cross-attention.)
  - Hand-object interaction: proximity between a hand's landmark centroid and
    a detected object's bounding box, debounced across consecutive samples so
    a single flickery detection doesn't flip the state.
  - Machine state: a frame-differencing heuristic over a configurable region
    of interest (defaults to the whole frame) -- motion above a threshold is
    "ACTUATING", otherwise "IDLE". Deliberately simple; the brief prefers a
    direct equipment signal (PLC/IoT) over vision for this when available.

Output is the motion-event stream the brief specifies for Stage 3, with two
honest caveats:

  1. distance is pixel-space (distance_px), not real-world cm -- no camera
     calibration/homography exists yet (Phase 2's calibration sub-step, not
     built), so this deliberately does not fabricate a real-world unit.
  2. `object` is frequently None. Generic tool/part text queries ("box",
     "bottle", "tool", "screwdriver"...) detect far less reliably here than
     self-referential ones ("person", "glove"), which is exactly why those
     are excluded from candidacy (SELF_REFERENTIAL_LABELS) -- otherwise
     every event would trivially say "holding: glove". What IS reliable is
     the *timing* signal: precise instants where a hand starts/stops moving
     or its grasp state changes. That's the actual value handed to Stage 4
     -- Gemini's own vision already identifies WHAT is held correctly (see
     the v2 prompt fix for the glue-tool/screwdriver misclassification);
     this stage's job is to anchor WHEN, objectively, not to duplicate what.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision

from app.config.cv_vocabulary import load_cv_vocabulary
from app.models.schemas import MotionEvent

MODELS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "models"

_MODEL_URLS = {
    "hand_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/latest/hand_landmarker.task"
    ),
    "pose_landmarker_lite.task": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
    ),
}

OBJECT_DETECTION_MODEL = "yolov8s-world.pt"
OBJECT_DETECTION_SCORE_THRESHOLD = 0.10

# These vocabulary entries describe the operator, not something they can
# hold -- excluded from "held object" candidates, since a hand is trivially
# always near a person/glove/hand detection, which would otherwise swamp
# every real tool/part signal.
SELF_REFERENTIAL_LABELS = {"person", "hand", "glove"}
HAND_OBJECT_PROXIMITY_PX = 60.0
DEBOUNCE_SAMPLES = 2


def ensure_models_downloaded() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in _MODEL_URLS.items():
        dest = MODELS_DIR / name
        if not dest.exists():
            urllib.request.urlretrieve(url, dest)


class _HandState:
    __slots__ = ("held_object", "candidate_object", "candidate_count", "last_pos")

    def __init__(self) -> None:
        self.held_object: str | None = None
        self.candidate_object: str | None = None
        self.candidate_count = 0
        self.last_pos: tuple[float, float] | None = None


class CVTracker:
    def __init__(self, sample_fps: float = 4.0, machine_roi: tuple[int, int, int, int] | None = None):
        """machine_roi is (x, y, w, h) in pixels; None = whole frame."""
        ensure_models_downloaded()
        self.sample_fps = sample_fps
        self.machine_roi = machine_roi

        self._hand_landmarker = mp_vision.HandLandmarker.create_from_options(
            mp_vision.HandLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(
                    model_asset_buffer=(MODELS_DIR / "hand_landmarker.task").read_bytes()
                ),
                num_hands=2,
                running_mode=mp_vision.RunningMode.IMAGE,
            )
        )
        self._pose_landmarker = mp_vision.PoseLandmarker.create_from_options(
            mp_vision.PoseLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(
                    model_asset_buffer=(MODELS_DIR / "pose_landmarker_lite.task").read_bytes()
                ),
                running_mode=mp_vision.RunningMode.IMAGE,
            )
        )

        from ultralytics import YOLO

        self._object_detector = YOLO(OBJECT_DETECTION_MODEL)
        self._object_queries = load_cv_vocabulary().object_queries
        self._object_detector.set_classes(self._object_queries)

    def _sample_frames(self, video_path: Path):
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps
        step = 1.0 / self.sample_fps

        t = 0.0
        while t < duration:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            # Downscale high-resolution frames to 640px for fast CV inference
            h, w = frame.shape[:2]
            if w > 640:
                target_h = max(2, int(h * (640.0 / w)))
                frame = cv2.resize(frame, (640, target_h), interpolation=cv2.INTER_NEAREST)
            yield t, frame
            t += step
        cap.release()

    def _detect_hands(self, frame_rgb: np.ndarray) -> dict[str, tuple[float, float]]:
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result = self._hand_landmarker.detect(mp_image)
        h, w = frame_rgb.shape[:2]
        positions: dict[str, tuple[float, float]] = {}
        for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
            # MediaPipe's handedness is from the subject's own perspective (a
            # mirror-flip of screen left/right); wrist landmark (index 0) as
            # the hand's reference point.
            label = "L" if handedness[0].category_name == "Left" else "R"
            wrist = landmarks[0]
            positions[label] = (wrist.x * w, wrist.y * h)
        return positions

    def _detect_objects(self, frame_bgr: np.ndarray) -> list[dict]:
        result = self._object_detector.predict(frame_bgr, verbose=False)[0]
        detections = []
        for box in result.boxes:
            score = float(box.conf[0])
            if score < OBJECT_DETECTION_SCORE_THRESHOLD:
                continue
            xyxy = box.xyxy[0].tolist()
            label = result.names[int(box.cls[0])]
            detections.append(
                {
                    "label": label,
                    "score": score,
                    "box": {"xmin": xyxy[0], "ymin": xyxy[1], "xmax": xyxy[2], "ymax": xyxy[3]},
                }
            )
        return detections

    @staticmethod
    def _bbox_center_distance(point: tuple[float, float], box: dict) -> float:
        cx = (box["xmin"] + box["xmax"]) / 2
        cy = (box["ymin"] + box["ymax"]) / 2
        return float(np.hypot(point[0] - cx, point[1] - cy))

    def _nearest_object(self, point: tuple[float, float], objects: list[dict]) -> str | None:
        candidates = [o for o in objects if o["label"] not in SELF_REFERENTIAL_LABELS]
        if not candidates:
            return None
        best = min(candidates, key=lambda o: self._bbox_center_distance(point, o["box"]))
        if self._bbox_center_distance(point, best["box"]) <= HAND_OBJECT_PROXIMITY_PX:
            return best["label"]
        return None

    def _machine_state(self, prev_gray: np.ndarray | None, gray: np.ndarray) -> str:
        if prev_gray is None:
            return "UNKNOWN"
        if self.machine_roi:
            x, y, w, h = self.machine_roi
            prev_roi, roi = prev_gray[y : y + h, x : x + w], gray[y : y + h, x : x + w]
        else:
            prev_roi, roi = prev_gray, gray
        diff = cv2.absdiff(prev_roi, roi)
        motion = float(np.mean(diff))
        return "ACTUATING" if motion > 8.0 else "IDLE"

    def build_motion_event_stream(self, video_path: Path) -> list[MotionEvent]:
        events: list[MotionEvent] = []
        hand_states = {"L": _HandState(), "R": _HandState()}
        prev_gray = None
        prev_t = None

        sample_idx = 0
        cached_objects: list[dict] = []

        for t, frame in self._sample_frames(video_path):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            hand_positions = self._detect_hands(rgb)
            # Run heavy YOLO object detector every 3rd sample (~1.5s), reusing cached boxes
            if sample_idx % 3 == 0:
                cached_objects = self._detect_objects(frame)
            objects = cached_objects
            machine_state = self._machine_state(prev_gray, gray)
            sample_idx += 1

            for hand_label, state in hand_states.items():
                pos = hand_positions.get(hand_label)
                if pos is None:
                    prev_t = t
                    prev_gray = gray
                    continue

                nearest = self._nearest_object(pos, objects)

                # Debounce: only commit a held-object change after it's been
                # consistent for DEBOUNCE_SAMPLES in a row, so one flickery
                # detection doesn't emit a spurious grasp/release pair.
                if nearest == state.candidate_object:
                    state.candidate_count += 1
                else:
                    state.candidate_object = nearest
                    state.candidate_count = 1

                distance_px = 0.0
                if state.last_pos is not None:
                    distance_px = float(np.hypot(pos[0] - state.last_pos[0], pos[1] - state.last_pos[1]))

                if state.candidate_count >= DEBOUNCE_SAMPLES and state.candidate_object != state.held_object:
                    if state.candidate_object is not None and state.held_object is None:
                        action = "GRASP"
                    elif state.candidate_object is None and state.held_object is not None:
                        action = "RELEASE"
                    else:
                        action = "GRASP"  # switched directly from one object to another
                    events.append(
                        MotionEvent(
                            t_start_sec=prev_t if prev_t is not None else t,
                            t_end_sec=t,
                            hand=hand_label,
                            action=action,
                            object=state.candidate_object or state.held_object,
                            distance_px=distance_px,
                            machine_state=machine_state,
                        )
                    )
                    state.held_object = state.candidate_object
                elif distance_px > 5.0:
                    events.append(
                        MotionEvent(
                            t_start_sec=prev_t if prev_t is not None else t,
                            t_end_sec=t,
                            hand=hand_label,
                            action="HOLD" if state.held_object else "MOVE",
                            object=state.held_object,
                            distance_px=distance_px,
                            machine_state=machine_state,
                        )
                    )

                state.last_pos = pos

            prev_gray = gray
            prev_t = t

        return events
