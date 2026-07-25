"""Camera calibration and spatial mapping module (Roadmap Item 2).

Converts pixel coordinates and distances (distance_px) to real-world metric units (cm, m)
using homography matrices or reference object pixel-per-metric scaling factor.
"""
from __future__ import annotations

from typing import Tuple
import numpy as np


class PixelToMetricMapper:
    def __init__(
        self,
        pixels_per_cm: float | None = None,
        homography_matrix: list[list[float]] | np.ndarray | None = None,
    ) -> None:
        self.pixels_per_cm = pixels_per_cm
        if homography_matrix is not None:
            self.homography_matrix = np.array(homography_matrix, dtype=np.float64)
        else:
            self.homography_matrix = None

    @classmethod
    def from_reference_object(
        cls, pixel_length: float, real_length_cm: float
    ) -> PixelToMetricMapper:
        """Calibrate using a known reference object in the frame (e.g. ruler, fiducial marker)."""
        if real_length_cm <= 0:
            raise ValueError("real_length_cm must be positive")
        return cls(pixels_per_cm=pixel_length / real_length_cm)

    @classmethod
    def from_homography_points(
        cls, src_pts_px: list[Tuple[float, float]], dst_pts_cm: list[Tuple[float, float]]
    ) -> PixelToMetricMapper:
        """Calibrate using 4 non-collinear point correspondences (pixel vs metric plane)."""
        import cv2

        src = np.array(src_pts_px, dtype=np.float32)
        dst = np.array(dst_pts_cm, dtype=np.float32)
        H, _ = cv2.findHomography(src, dst)
        return cls(homography_matrix=H)

    def px_to_cm(self, distance_px: float) -> float | None:
        """Convert pixel displacement to centimeters if calibrated."""
        if self.pixels_per_cm and self.pixels_per_cm > 0:
            return round(distance_px / self.pixels_per_cm, 2)
        return None

    def px_to_m(self, distance_px: float) -> float | None:
        """Convert pixel displacement to meters if calibrated."""
        cm = self.px_to_cm(distance_px)
        return round(cm / 100.0, 3) if cm is not None else None

    def transform_point(self, x_px: float, y_px: float) -> Tuple[float, float] | None:
        """Transform (x, y) pixel coordinates to metric plane (cm) via homography."""
        if self.homography_matrix is None:
            return None
        pt = np.array([x_px, y_px, 1.0], dtype=np.float64).reshape(3, 1)
        res = np.dot(self.homography_matrix, pt)
        res /= res[2, 0]
        return float(res[0, 0]), float(res[1, 0])
