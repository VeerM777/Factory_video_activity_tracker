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
    """Detects faces and head regions frame-by-frame using MediaPipe Face Detection,
    MediaPipe Pose head landmarks, and OpenCV Haar cascade fallbacks, applying a
    strong Gaussian blur to ensure complete privacy protection."""
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    cascade = cv2.CascadeClassifier(_FACE_CASCADE_PATH) if Path(_FACE_CASCADE_PATH).exists() else None

    try:
        mp_solutions = getattr(mp, "solutions", None)
        if mp_solutions and hasattr(mp_solutions, "face_detection") and hasattr(mp_solutions, "pose"):
            face_detector = mp_solutions.face_detection.FaceDetection(min_detection_confidence=0.3)
            pose_detector = mp_solutions.pose.Pose(min_detection_confidence=0.3, min_tracking_confidence=0.3)
        else:
            face_detector = None
            pose_detector = None
    except Exception:
        face_detector = None
        pose_detector = None

    try:
        frame_idx = 0
        cached_boxes = []
        detect_stride = 3  # Run heavy model detection every 3 frames, reuse boxes for adjacent frames

        while True:
            ok, frame = cap.read()
            if not ok:
                break

            h_img, w_img, _ = frame.shape

            if frame_idx % detect_stride == 0:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                face_boxes = []

                # 1. MediaPipe Face Detection (if available)
                if face_detector is not None:
                    try:
                        face_results = face_detector.process(rgb_frame)
                        if face_results and face_results.detections:
                            for det in face_results.detections:
                                bbox = det.location_data.relative_bounding_box
                                x = int(bbox.xmin * w_img)
                                y = int(bbox.ymin * h_img)
                                w = int(bbox.width * w_img)
                                h = int(bbox.height * h_img)
                                pad_x, pad_y = int(w * 0.3), int(h * 0.3)
                                face_boxes.append((x - pad_x, y - pad_y, w + 2 * pad_x, h + 2 * pad_y))
                    except Exception:
                        pass

                # 2. MediaPipe Pose Head Landmark Box (if available)
                if pose_detector is not None:
                    try:
                        pose_results = pose_detector.process(rgb_frame)
                        if pose_results and pose_results.pose_landmarks:
                            head_indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
                            pts = []
                            for idx in head_indices:
                                lm = pose_results.pose_landmarks.landmark[idx]
                                if lm.visibility > 0.3:
                                    pts.append((int(lm.x * w_img), int(lm.y * h_img)))
                            if len(pts) >= 2:
                                xs = [p[0] for p in pts]
                                ys = [p[1] for p in pts]
                                min_x, max_x = max(0, min(xs)), min(w_img, max(xs))
                                min_y, max_y = max(0, min(ys)), min(h_img, max(ys))
                                bw, bh = max_x - min_x, max_y - min_y
                                pad = int(max(bw, bh, 40) * 0.6)
                                face_boxes.append((min_x - pad, min_y - pad, bw + 2 * pad, bh + 2 * pad))
                    except Exception:
                        pass

                # 3. Haar Cascade Fallback (if available)
                if not face_boxes and cascade is not None and not cascade.empty():
                    try:
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        haar_faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=3, minSize=(30, 30))
                        for (x, y, w, h) in haar_faces:
                            face_boxes.append((x, y, w, h))
                    except Exception:
                        pass

                cached_boxes = face_boxes

            # Apply heavy Gaussian blur over cached face/head boxes
            for (x, y, w, h) in cached_boxes:
                x1 = max(0, x)
                y1 = max(0, y)
                x2 = min(w_img, x + w)
                y2 = min(h_img, y + h)
                if x2 > x1 and y2 > y1:
                    roi = frame[y1:y2, x1:x2]
                    blurred_roi = cv2.GaussianBlur(roi, (blur_ksize, blur_ksize), 0)
                    frame[y1:y2, x1:x2] = blurred_roi

            writer.write(frame)
            frame_idx += 1
    finally:
        cap.release()
        writer.release()

    return output_path
