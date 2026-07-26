"""Stage 2 -- Preprocessing.

Runs the mandatory face-blurring pass before any video frame is retained or
sent to an external API -- this is a privacy requirement from the brief, not
optional, so it applies even in the Phase 0 proof of concept. Camera
calibration (pixel-to-real-world homography) is deferred to Phase 2, when
Stage 3 (CV tracking) needs real-world distances; Phase 0 does not compute
distance-dependent parameters from CV, so calibration is not built yet.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

_FACE_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"


def blur_faces(input_path: Path, output_path: Path, blur_ksize: int = 65) -> Path:
    """Fast, production-optimized face blurring pass using MediaPipe Face Detection
    with frame downscaling, stride caching, and fast pixelation blurring."""
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    mp_face = mp.solutions.face_detection
    detect_stride = 5  # Run detector every 5 frames (~6 times/sec)

    try:
        with mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.25) as face_detector:
            frame_idx = 0
            cached_boxes: list[tuple[int, int, int, int]] = []

            while True:
                ok, frame = cap.read()
                if not ok:
                    break

                h_img, w_img, _ = frame.shape

                if frame_idx % detect_stride == 0:
                    face_boxes: list[tuple[int, int, int, int]] = []
                    # Downscale 50% for fast neural detection pass
                    small_frame = cv2.resize(frame, (w_img // 2, h_img // 2), interpolation=cv2.INTER_NEAREST)
                    rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

                    face_results = face_detector.process(rgb_small)
                    if face_results.detections:
                        for det in face_results.detections:
                            bbox = det.location_data.relative_bounding_box
                            # Scale back coordinates to original frame dimensions
                            x = int(bbox.xmin * w_img)
                            y = int(bbox.ymin * h_img)
                            w = int(bbox.width * w_img)
                            h = int(bbox.height * h_img)
                            # Generous padding to cover full head/hair
                            pad_x, pad_y = int(w * 0.4), int(h * 0.4)
                            face_boxes.append((x - pad_x, y - pad_y, w + 2 * pad_x, h + 2 * pad_y))

                    cached_boxes = face_boxes

                # Apply fast pixelation blur over cached face boxes
                for (x, y, w, h) in cached_boxes:
                    x1 = max(0, x)
                    y1 = max(0, y)
                    x2 = min(w_img, x + w)
                    y2 = min(h_img, y + h)
                    box_w = x2 - x1
                    box_h = y2 - y1
                    if box_w > 10 and box_h > 10:
                        roi = frame[y1:y2, x1:x2]
                        # 10x downscale + upscale pixelation (instantaneous vs 65x65 GaussianBlur)
                        small_roi = cv2.resize(roi, (max(2, box_w // 10), max(2, box_h // 10)), interpolation=cv2.INTER_NEAREST)
                        frame[y1:y2, x1:x2] = cv2.resize(small_roi, (box_w, box_h), interpolation=cv2.INTER_NEAREST)

                writer.write(frame)
                frame_idx += 1
    finally:
        cap.release()
        writer.release()

    return output_path

